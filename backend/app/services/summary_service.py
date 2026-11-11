"""Patient summary (built from all visible notes) and medication-safety alerts."""
from __future__ import annotations

from datetime import date
from functools import lru_cache

import requests

from backend.app.utils.drug_knowledge import (DUPLICATE_CLASSES, INTERACTIONS, allergy_classes, base_name,
                                              classes_of)

STALE_AFTER_DAYS = 365
OPENFDA_LABEL_URL = "https://api.fda.gov/drug/label.json"


def build_summary(records: list[dict]) -> dict:
    """Combine a patient's records (newest first) into one history."""
    meds: dict[str, dict] = {}
    conditions: dict[str, dict] = {}
    allergies: dict[str, dict] = {}
    nkda_sources = []
    timeline = []

    for r in sorted(records, key=lambda r: (r["visit_date"], r["id"])):  # oldest -> newest
        e, src = r["entities"], {"record_id": r["id"], "date": r["visit_date"], "hospital": r["hospital"]}
        for m in e.get("medication_details") or [{"name": n, "dosage": None} for n in e.get("medications", [])]:
            key = base_name(m["name"])
            prev = meds.get(key, {"history": []})
            entry = {"name": key, "dosage": m.get("dosage") or prev.get("dosage"),
                     "last_seen": r["visit_date"], "hospital": r["hospital"], "record_id": r["id"],
                     "history": prev["history"] + [{**src, "dosage": m.get("dosage")}]}
            meds[key] = entry
        for d in e.get("diagnoses", []):
            key = d.lower()
            c = conditions.setdefault(key, {"name": d, "first_seen": r["visit_date"], "hospitals": set()})
            c["last_seen"] = r["visit_date"]
            c["hospitals"].add(r["hospital"])
        for a in e.get("allergies", []):
            key = a["substance"].lower()
            allergies.setdefault(key, {"substance": a["substance"], "reaction": a.get("reaction"), **src})
            if a.get("reaction"):
                allergies[key]["reaction"] = a["reaction"]
        if e.get("no_known_allergies"):
            nkda_sources.append(src)
        sev = (e.get("severity") or {}).get("level", "low")
        timeline.append({**src, "author": r.get("author", ""), "severity": sev,
                         "diagnoses": e.get("diagnoses", []), "symptoms": e.get("symptoms", []),
                         "medications": [base_name(m) for m in e.get("medications", [])],
                         "note": r["clinical_note"]})

    # 'diabetes' is covered by 'type 2 diabetes': merge shorter condition names into longer ones
    for short in list(conditions):
        longer = next((k for k in conditions if k != short and short in k), None)
        if longer:
            c, s_ = conditions[longer], conditions.pop(short)
            c["first_seen"] = min(c["first_seen"], s_["first_seen"])
            c["last_seen"] = max(c["last_seen"], s_["last_seen"])
            c["hospitals"] |= s_["hospitals"]

    today = date.today()
    current, older = [], []
    for m in meds.values():
        age_days = (today - date.fromisoformat(m["last_seen"])).days
        m["stale"] = age_days > STALE_AFTER_DAYS
        (older if m["stale"] else current).append(m)

    summary = {
        "allergies": list(allergies.values()),
        "no_known_allergies": bool(nkda_sources) and not allergies,
        "current_medications": sorted(current, key=lambda m: m["last_seen"], reverse=True),
        "older_medications": sorted(older, key=lambda m: m["last_seen"], reverse=True),
        "conditions": sorted(({**c, "hospitals": sorted(c["hospitals"])} for c in conditions.values()),
                             key=lambda c: c["last_seen"], reverse=True),
        "timeline": list(reversed(timeline)),  # newest first
        "hospitals": sorted({r["hospital"] for r in records}),
        "latest_severity": timeline[-1]["severity"] if timeline else None,
    }
    summary["alerts"] = safety_alerts(summary)
    return summary


def safety_alerts(summary: dict) -> list[dict]:
    """Rule-based medication safety checks over the combined history (all visible hospitals)."""
    alerts = []
    current = summary["current_medications"]

    # 1. Allergy vs. current medication
    for a in summary["allergies"]:
        hard, caution = allergy_classes(a["substance"])
        for m in current:
            cls = classes_of(m["name"])
            if base_name(m["name"]) == base_name(a["substance"]) or cls & hard:
                alerts.append({"severity": "high", "type": "allergy",
                               "message": f"{m['name']} conflicts with documented allergy to {a['substance']}"
                                          + (f" ({a['reaction']})" if a.get("reaction") else ""),
                               "sources": [f"allergy: {a['hospital']} {a['date']}",
                                           f"{m['name']}: {m['hospital']} {m['last_seen']}"]})
            elif cls & caution:
                alerts.append({"severity": "medium", "type": "allergy",
                               "message": f"{m['name']}: possible cross-reactivity with {a['substance']} allergy",
                               "sources": [f"allergy: {a['hospital']} {a['date']}",
                                           f"{m['name']}: {m['hospital']} {m['last_seen']}"]})

    # 2. Interactions between current medications
    for i, m1 in enumerate(current):
        for m2 in current[i + 1:]:
            c1, c2 = classes_of(m1["name"]), classes_of(m2["name"])
            for a, b, why, sev in INTERACTIONS:
                if (a in c1 and b in c2) or (a in c2 and b in c1):
                    alerts.append({"severity": sev, "type": "interaction",
                                   "message": f"{m1['name']} + {m2['name']}: {why}",
                                   "sources": [f"{m1['name']}: {m1['hospital']} {m1['last_seen']}",
                                               f"{m2['name']}: {m2['hospital']} {m2['last_seen']}"]})
                    break

    # 3. Therapeutic duplication (two different drugs from the same class)
    seen_pairs = set()
    for cls in DUPLICATE_CLASSES:
        members = [m for m in current if cls in classes_of(m["name"])]
        if len(members) > 1 and cls not in seen_pairs:
            seen_pairs.add(cls)
            alerts.append({"severity": "medium", "type": "duplication",
                           "message": f"Two {cls.replace('_', ' ')} drugs at once: "
                                      + ", ".join(m["name"] for m in members),
                           "sources": [f"{m['name']}: {m['hospital']} {m['last_seen']}" for m in members]})

    # 4. Same drug, different doses at different hospitals (medication reconciliation)
    for m in current:
        by_hospital = {}
        for h in m["history"]:
            if h.get("dosage"):
                by_hospital[h["hospital"]] = h
        doses = {h["dosage"].lower() for h in by_hospital.values()}
        if len(by_hospital) > 1 and len(doses) > 1:
            alerts.append({"severity": "medium", "type": "reconciliation",
                           "message": f"{m['name']} recorded with different doses: "
                                      + "; ".join(f"{h['dosage']} at {hosp} ({h['date']})"
                                                  for hosp, h in by_hospital.items()),
                           "sources": [f"{hosp} {h['date']}" for hosp, h in by_hospital.items()]})

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(alerts, key=lambda a: order[a["severity"]])


@lru_cache(maxsize=256)
def fda_label_check(drug: str, allergens: tuple[str, ...]) -> dict:
    """Search the drug's official FDA label (contraindications / warnings) for the patient's allergies.
    Returns the matching sentence so the clinician sees the source text."""
    try:
        r = requests.get(OPENFDA_LABEL_URL, timeout=20, params={
            "search": f'openfda.generic_name:"{drug}"', "limit": 5})
        if r.status_code == 404:
            return {"drug": drug, "found": False, "matches": []}
        r.raise_for_status()
        labels = r.json().get("results", [])
    except Exception as exc:
        return {"drug": drug, "found": False, "matches": [], "error": str(exc)}

    def single(lbl):
        names = (lbl.get("openfda") or {}).get("generic_name", [""])
        return " and " in names[0].lower()

    labels.sort(key=single)  # prefer single-ingredient labels
    if not labels:
        return {"drug": drug, "found": False, "matches": []}
    label = labels[0]
    text = " ".join(label.get("contraindications", []) + label.get("warnings", [])
                    + label.get("warnings_and_cautions", []))
    matches = []
    for allergen in allergens:
        hard, _ = allergy_classes(allergen)
        terms = {allergen.lower()} | {c.replace("_", " ") for c in hard}
        for sentence in text.replace("\n", " ").split(". "):
            if any(t in sentence.lower() for t in terms):
                matches.append({"allergen": allergen, "text": sentence.strip()[:300]})
                break
    return {"drug": drug, "found": True, "matches": matches,
            "warning": (label.get("boxed_warning") or label.get("warnings") or [""])[0][:300]}
