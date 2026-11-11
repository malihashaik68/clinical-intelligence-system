"""Allergy extraction from clinical notes.

The biomedical NER model has no allergy label, so allergies are found with
patterns clinicians actually write: "allergic to X", "allergy to X",
"allergies: X, Y", "X allergy", plus "no known drug allergies" (NKDA).
"""
import re

_STOP = r"(?:\.|;|\n|$| and (?:is|was|has|had|reports|presents|takes|on)\b| but\b| with\b)"
_LIST_SPLIT = re.compile(r",|/| and | or ", re.I)
_REACTION = re.compile(r"\(([^)]+)\)")

PATTERNS = [
    re.compile(rf"\ballergic to (?P<items>.+?){_STOP}", re.I),
    re.compile(rf"\ballerg(?:y|ies) to (?P<items>.+?){_STOP}", re.I),
    re.compile(rf"\ballerg(?:y|ies)\s*[:\-]\s*(?P<items>.+?){_STOP}", re.I),
    re.compile(r"\b(?P<items>[a-z][a-z\-]+) allergy\b", re.I),
]
NKDA = re.compile(r"\b(nkda|no known (?:drug )?allergies)\b", re.I)
_NOT_AN_ALLERGEN = {"known", "no", "drug", "food", "seasonal", "an", "the", "a", "documented", "reported",
                    "reports", "patient", "has", "any", "severe", "mild", "with", "of"}


def extract_allergies(note: str) -> dict:
    """Return {"allergies": [{"substance", "reaction"}], "no_known_allergies": bool}."""
    found: dict[str, str | None] = {}
    for pattern in PATTERNS:
        for m in pattern.finditer(note):
            chunk = m.group("items")
            reaction = None
            r = _REACTION.search(chunk)
            if r:
                reaction = r.group(1).strip()
                chunk = _REACTION.sub("", chunk)
            for part in _LIST_SPLIT.split(chunk):
                name = " ".join(part.lower().split()).strip(" .:-")
                if not name or name in _NOT_AN_ALLERGEN or len(name) < 3 or len(name.split()) > 3:
                    continue
                if name not in found or (reaction and not found[name]):
                    found[name] = reaction
    return {
        "allergies": [{"substance": s, "reaction": r} for s, r in found.items()],
        "no_known_allergies": bool(NKDA.search(note)) and not found,
    }
