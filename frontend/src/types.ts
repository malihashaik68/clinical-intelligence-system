// Shapes of the backend responses used by the dashboard.

export type SeverityLevel = "high" | "medium" | "low";

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: string;
  hospital_id: number;
  hospital_name: string;
}

export interface Severity {
  level: SeverityLevel;
  reasons: string[];
}

export interface MedicationDetail {
  name: string;
  dosage: string | null;
}

export interface Allergy {
  substance: string;
  reaction: string | null;
}

export interface RawEntity {
  text: string;
  entity_group: string;
  source: "bert" | "dictionary";
  score?: number | null;
}

export interface ExtractedEntities {
  medications: string[];
  medication_details: MedicationDetail[];
  symptoms: string[];
  diagnoses: string[];
  allergies: Allergy[];
  no_known_allergies?: boolean;
  raw_entities: RawEntity[];
  severity?: Severity;
}

export interface OpenFdaLabel {
  indications_and_usage: string[];
  warnings: string[];
}

export interface MedicationContext {
  input_name: string;
  rxnorm: { rxcui: string | null };
  openfda: { count: number; results: OpenFdaLabel[] };
}

export interface Literature {
  query: string;
  results: { pmid: string; title: string; source: string; pubdate: string }[];
}

export interface Analysis {
  extracted_entities: ExtractedEntities;
  severity: Severity;
  api_results: { structured_context?: { medications: MedicationContext[]; literature: Literature[] } };
}

export interface PatientCard {
  id: number;
  health_id: string;
  full_name: string;
  date_of_birth: string;
  age: number;
  sex: string;
  blood_type: string;
  emergency_contact: string;
  records_at: Record<string, number>;
  match?: string;
  registered_here?: boolean;
}

export interface Alert {
  severity: SeverityLevel;
  type: string;
  message: string;
  sources: string[];
}

export interface Medication {
  name: string;
  dosage: string | null;
  last_seen: string;
  hospital: string;
}

export interface Summary {
  allergies: (Allergy & { hospital: string; date: string })[];
  no_known_allergies: boolean;
  current_medications: Medication[];
  older_medications: Medication[];
  conditions: { name: string; first_seen: string; hospitals: string[] }[];
  timeline: {
    record_id: number;
    date: string;
    hospital: string;
    author: string;
    severity: SeverityLevel;
    note: string;
    diagnoses: string[];
    medications: string[];
  }[];
  alerts: Alert[];
  latest_severity: SeverityLevel | null;
}

export interface AccessStatus {
  registered_here: boolean;
  own_hospital_records: boolean;
  other_hospital_records: boolean;
  grant_kind: "consent" | "emergency" | null;
  grant_expires: string | null;
}

export interface PatientView {
  patient: PatientCard;
  access: AccessStatus;
  hidden_records_at_other_hospitals: number;
  summary: Summary;
}

export interface Answer {
  answer: string;
  method: string;
  evidence: { record_id: number; text: string; source: string }[];
  llm_note?: string;
}

export interface LogEntry {
  time: string;
  practitioner: string;
  hospital: string;
  action: string;
  detail: string;
}
