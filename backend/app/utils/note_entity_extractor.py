def extract_entities_from_note(clinical_note: str):
    note = clinical_note.lower()

    medication_list = ["metformin", "ibuprofen", "aspirin", "paracetamol"]
    symptom_list = ["fatigue", "fever", "cough", "headache"]
    diagnosis_list = ["hypertension", "diabetes", "asthma"]

    medications = [med for med in medication_list if med in note]
    symptoms = [sym for sym in symptom_list if sym in note]
    diagnoses = [diag for diag in diagnosis_list if diag in note]

    return {
        "clinical_note": clinical_note,
        "medications": medications,
        "symptoms": symptoms,
        "diagnoses": diagnoses,
    }