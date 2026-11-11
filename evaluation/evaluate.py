"""Evaluate entity extraction with precision, recall and F1.

Compares the BERT pipeline (model + post-processing + dictionary safety net)
against the simple keyword baseline on a hand-labelled set of 30 notes
(evaluation/gold_notes.json, 133 labelled entities).

Matching is per note and per category (medications / symptoms / diagnoses):
  - strict:  normalised text must be identical ("type 2 diabetes" == "type 2 diabetes")
  - relaxed: one contains the other ("diabetes" matches "type 2 diabetes")

Run from the project root:  python -m evaluation.evaluate
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.app.utils.bert_entity_extractor import extract_entities_with_bert, normalize_text
from backend.app.utils.note_entity_extractor import extract_entities_from_note

CATEGORIES = ["medications", "symptoms", "diagnoses"]
HERE = Path(__file__).parent


def _match(pred: list[str], gold: list[str], relaxed: bool) -> tuple[int, int, int]:
    """Return (true positives, false positives, false negatives) for one note/category."""
    pred = [normalize_text(p) for p in pred]
    gold = [normalize_text(g) for g in gold]
    unmatched_gold = list(gold)
    tp = 0
    for p in pred:
        hit = next((g for g in unmatched_gold
                    if p == g or (relaxed and (p in g or g in p))), None)
        if hit is not None:
            tp += 1
            unmatched_gold.remove(hit)
    return tp, len(pred) - tp, len(unmatched_gold)


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
            "tp": tp, "fp": fp, "fn": fn}


def evaluate(extractor, notes: list[dict], relaxed: bool) -> dict:
    totals = {c: [0, 0, 0] for c in CATEGORIES}
    for item in notes:
        pred = extractor(item["note"])
        for c in CATEGORIES:
            for i, v in enumerate(_match(pred.get(c, []), item[c], relaxed)):
                totals[c][i] += v
    scores = {c: _prf(*totals[c]) for c in CATEGORIES}
    scores["micro_avg"] = _prf(*[sum(totals[c][i] for c in CATEGORIES) for i in range(3)])
    return scores


def main() -> int:
    notes = json.loads((HERE / "gold_notes.json").read_text())
    systems = {"BERT pipeline": extract_entities_with_bert, "Keyword baseline": extract_entities_from_note}
    results = {name: {mode: evaluate(fn, notes, relaxed=(mode == "relaxed"))
                      for mode in ("strict", "relaxed")} for name, fn in systems.items()}

    lines = [f"# Entity extraction evaluation\n",
             f"{len(notes)} hand-labelled notes, "
             f"{sum(len(n[c]) for n in notes for c in CATEGORIES)} entities. "
             "Strict = exact match after normalisation; relaxed = one contains the other.\n"]
    for mode in ("strict", "relaxed"):
        lines += [f"\n## {mode.capitalize()} matching\n",
                  "| System | Category | Precision | Recall | F1 |", "|---|---|---|---|---|"]
        for name in systems:
            for c in CATEGORIES + ["micro_avg"]:
                s = results[name][mode][c]
                label = "**overall (micro)**" if c == "micro_avg" else c
                lines.append(f"| {name} | {label} | {s['precision']:.2f} | {s['recall']:.2f} | {s['f1']:.2f} |")
    report = "\n".join(lines) + "\n"
    (HERE / "results.md").write_text(report, encoding="utf-8")
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
