import os
from functools import lru_cache

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Persistent Chroma folder (project root by default)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("CHROMA_PATH") or os.path.abspath(os.path.join(BASE_DIR, "../../../chroma_db"))


@lru_cache(maxsize=1)
def get_embedding_model():
    """Sentence-transformer used to embed notes (loaded on first use)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def get_collection():
    """Persistent ChromaDB collection holding one vector per clinical note."""
    import chromadb

    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_or_create_collection(name="clinical_records")


def create_embedding(text: str):
    return get_embedding_model().encode(text).tolist()


def store_record_embedding(record_id: int, clinical_note: str, extracted_entities: dict):
    embedding = create_embedding(clinical_note)

    diagnoses = ", ".join(extracted_entities.get("diagnoses", []))
    symptoms = ", ".join(extracted_entities.get("symptoms", []))
    medications = ", ".join(extracted_entities.get("medications", []))

    metadata = {
        "diagnoses": diagnoses,
        "symptoms": symptoms,
        "medications": medications,
        "severity": (extracted_entities.get("severity") or {}).get("level", "unknown"),
    }

    # Prevent duplicate-id errors after DB resets / reruns
    try:
        get_collection().delete(ids=[str(record_id)])
    except Exception:
        pass

    get_collection().add(
        documents=[clinical_note],
        embeddings=[embedding],
        ids=[str(record_id)],
        metadatas=[metadata]
    )


def search_similar_records(query: str, top_k=3):
    query_embedding = create_embedding(query)

    results = get_collection().query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )

    formatted_results = []

    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i in range(len(ids)):
        metadata = metadatas[i] if i < len(metadatas) and metadatas[i] else {}

        formatted_results.append({
            "record_id": ids[i],
            "clinical_note": documents[i] if i < len(documents) else "",
            "diagnoses": metadata.get("diagnoses", ""),
            "symptoms": metadata.get("symptoms", ""),
            "medications": metadata.get("medications", ""),
            "severity": metadata.get("severity", "unknown"),
            "distance": distances[i] if i < len(distances) else None
        })

    return {
        "query": query,
        "matches": formatted_results
    }