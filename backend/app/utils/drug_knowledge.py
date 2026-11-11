"""Small, curated drug-safety knowledge used for alerts.

Deliberately limited and transparent (every alert says which rule fired). It covers
common, well-established cases only: it is a demo of medication safety checks, not
a complete interaction database.
"""

# Drug classes (lower-case generic names)
DRUG_CLASSES = {
    "penicillin": {"penicillin", "amoxicillin", "ampicillin", "piperacillin", "dicloxacillin",
                   "amoxicillin-clavulanate", "nafcillin", "oxacillin"},
    "cephalosporin": {"cephalexin", "cefuroxime", "ceftriaxone", "cefazolin", "cefdinir"},
    "sulfonamide": {"sulfamethoxazole", "trimethoprim-sulfamethoxazole", "sulfasalazine"},
    "nsaid": {"ibuprofen", "naproxen", "diclofenac", "celecoxib", "ketorolac", "indomethacin", "meloxicam"},
    "aspirin": {"aspirin"},
    "anticoagulant": {"warfarin", "apixaban", "rivaroxaban", "dabigatran", "heparin", "enoxaparin", "edoxaban"},
    "antiplatelet": {"aspirin", "clopidogrel", "ticagrelor", "prasugrel"},
    "ace_inhibitor": {"lisinopril", "enalapril", "ramipril", "captopril", "benazepril"},
    "arb": {"losartan", "valsartan", "irbesartan", "candesartan"},
    "potassium_sparing": {"spironolactone", "eplerenone", "amiloride", "triamterene"},
    "ssri": {"sertraline", "fluoxetine", "escitalopram", "citalopram", "paroxetine"},
    "opioid": {"morphine", "oxycodone", "hydrocodone", "codeine", "tramadol", "fentanyl"},
    "benzodiazepine": {"lorazepam", "diazepam", "alprazolam", "clonazepam"},
    "statin": {"atorvastatin", "simvastatin", "rosuvastatin", "pravastatin"},
    "macrolide": {"clarithromycin", "erythromycin", "azithromycin"},
}

# Allergy written in a note -> drug classes it rules out
ALLERGY_TO_CLASSES = {
    "penicillin": ["penicillin"],
    "penicillins": ["penicillin"],
    "amoxicillin": ["penicillin"],
    "sulfa": ["sulfonamide"],
    "sulfa drugs": ["sulfonamide"],
    "sulfonamides": ["sulfonamide"],
    "nsaids": ["nsaid", "aspirin"],
    "nsaid": ["nsaid", "aspirin"],
    "aspirin": ["aspirin", "nsaid"],
    "ibuprofen": ["nsaid"],
    "codeine": ["opioid"],
    "morphine": ["opioid"],
    "statins": ["statin"],
    "cephalosporins": ["cephalosporin"],
}
# Partial cross-reactivity worth a caution (not a hard stop)
CROSS_REACTIVE = {"penicillin": ["cephalosporin"]}

# Well-known interactions between classes: (class_a, class_b, why, severity)
INTERACTIONS = [
    ("anticoagulant", "nsaid", "bleeding risk: anticoagulant combined with an NSAID", "high"),
    ("anticoagulant", "antiplatelet", "bleeding risk: anticoagulant combined with an antiplatelet", "high"),
    ("ssri", "nsaid", "increased gastrointestinal bleeding risk with SSRI + NSAID", "medium"),
    ("ace_inhibitor", "potassium_sparing", "risk of high potassium (hyperkalaemia)", "medium"),
    ("arb", "potassium_sparing", "risk of high potassium (hyperkalaemia)", "medium"),
    ("ace_inhibitor", "arb", "dual RAAS blockade: kidney injury and high potassium risk", "high"),
    ("opioid", "benzodiazepine", "respiratory depression: opioid combined with a benzodiazepine", "high"),
    ("statin", "macrolide", "statin levels raised by some macrolides (muscle damage risk)", "medium"),
]

# Classes where taking two different drugs at once is usually a duplication
DUPLICATE_CLASSES = {"nsaid", "anticoagulant", "ace_inhibitor", "arb", "ssri", "statin", "benzodiazepine"}

BLOOD_THINNER_CLASSES = ("anticoagulant", "antiplatelet")


def base_name(drug: str) -> str:
    """'Metformin HCl 500' -> 'metformin' (first word, lower-case), keeping known combos."""
    d = " ".join(drug.lower().split())
    for cls in DRUG_CLASSES.values():
        for name in cls:
            if d == name or d.startswith(name + " "):
                return name
    return d.split(" ")[0] if d else d


def classes_of(drug: str) -> set[str]:
    name = base_name(drug)
    return {cls for cls, members in DRUG_CLASSES.items() if name in members}


def allergy_classes(allergen: str) -> tuple[set[str], set[str]]:
    """Return (classes ruled out, classes needing caution) for an allergy string."""
    a = " ".join(allergen.lower().split())
    hard = set(ALLERGY_TO_CLASSES.get(a, []))
    if not hard:
        hard = {cls for cls, members in DRUG_CLASSES.items() if a in members}
    caution = {c for h in hard for c in CROSS_REACTIVE.get(h, [])}
    return hard, caution - hard
