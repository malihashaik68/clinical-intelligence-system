// Shapes of the backend responses used by the dashboard.

export type SeverityLevel = "high" | "medium" | "low";

export interface Severity {
  level: SeverityLevel;
  reasons: string[];
}

export interface MedicationDetail {
  name: string;
  dosage: string | null;
}

export interface RawEntity {
  text: string;
  entity_group: string;
  source: "bert" | "dictionary";
  score?: number | null;
}

export interface ExtractedEntities {
  clinical_note: string;
  medications: string[];
  medication_details: MedicationDetail[];
  symptoms: string[];
  diagnoses: string[];
  raw_entities: RawEntity[];
  severity?: Severity;
}

export interface OpenFdaLabel {
  brand_name: string[];
  generic_name: string[];
  indications_and_usage: string[];
  warnings: string[];
}

export interface MedicationContext {
  input_name: string;
  rxnorm: { matched: boolean; rxcui: string | null; properties?: { name?: string } | null };
  openfda: { count: number; results: OpenFdaLabel[]; error?: string };
}

export interface Article {
  pmid: string;
  title: string;
  pubdate: string;
  source: string;
}

export interface Literature {
  query: string;
  results: Article[];
  error?: string;
}

export interface AnalyzeResponse {
  extracted_entities: ExtractedEntities;
  severity: Severity;
  api_results: {
    structured_context: {
      medications: MedicationContext[];
      literature: Literature[];
    };
  };
  database: { record_id: number };
}

export interface Match {
  record_id: string;
  clinical_note: string;
  diagnoses: string;
  symptoms: string;
  medications: string;
  severity?: string;
  distance: number | null;
}

export interface RagResponse {
  query: string;
  matches: Match[];
  generated_answer: string;
  summary_source?: "llm" | "template";
}

export interface StoredRecord {
  id: number;
  clinical_note: string;
  extracted_entities: ExtractedEntities;
  created_at: string | null;
}

export interface RecordsResponse {
  total: number;
  records: StoredRecord[];
}

export interface Analytics {
  total_records: number;
  top_diagnoses: [string, number][];
  top_symptoms: [string, number][];
  top_medications: [string, number][];
  severity_counts?: Record<string, number>;
}
