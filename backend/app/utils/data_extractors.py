import requests
import time

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
OPENFDA_DRUG_LABEL_URL = "https://api.fda.gov/drug/label.json"
RXNORM_APPROX_URL = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
RXNORM_PROPERTIES_URL = "https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"


def search_pubmed(query: str, retmax: int = 5):
    try:
        time.sleep(1)

        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": retmax,
        }

        response = requests.get(PUBMED_ESEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        return {"error": f"PubMed search failed: {str(e)}"}


def fetch_pubmed_summaries(pmids):
    try:
        if not pmids or isinstance(pmids, dict):
            return []

        time.sleep(1)

        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
        }

        response = requests.get(PUBMED_ESUMMARY_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        result = data.get("result", {})
        articles = []

        for pmid in pmids:
            item = result.get(pmid, {})
            if item:
                authors = []
                for a in item.get("authors", []):
                    if isinstance(a, dict) and a.get("name"):
                        authors.append(a.get("name"))

                articles.append({
                    "pmid": pmid,
                    "title": item.get("title"),
                    "pubdate": item.get("pubdate"),
                    "source": item.get("source"),
                    "authors": authors,
                })

        return articles
    except Exception as e:
        return [{"error": f"PubMed summary failed: {str(e)}"}]


def pubmed_lookup(query: str, retmax: int = 5):
    pmids = search_pubmed(query, retmax=retmax)

    if isinstance(pmids, dict) and "error" in pmids:
        return {
            "query": query,
            "count": 0,
            "results": [],
            "error": pmids["error"],
        }

    summaries = fetch_pubmed_summaries(pmids)

    return {
        "query": query,
        "count": len(summaries) if isinstance(summaries, list) else 0,
        "results": summaries if isinstance(summaries, list) else [],
    }


def search_openfda_drug(drug_name: str, limit: int = 3):
    try:
        params = {
            "search": f'openfda.generic_name:"{drug_name}" OR openfda.brand_name:"{drug_name}"',
            "limit": limit,
        }

        response = requests.get(OPENFDA_DRUG_LABEL_URL, params=params, timeout=30)

        if response.status_code == 404:
            return {
                "drug_name": drug_name,
                "count": 0,
                "results": []
            }

        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("results", []):
            openfda = item.get("openfda", {}) or {}

            results.append({
                "brand_name": openfda.get("brand_name", []),
                "generic_name": openfda.get("generic_name", []),
                "manufacturer_name": openfda.get("manufacturer_name", []),
                "purpose": item.get("purpose", []),
                "indications_and_usage": item.get("indications_and_usage", []),
                "warnings": item.get("warnings", []),
            })

        return {
            "drug_name": drug_name,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        return {
            "drug_name": drug_name,
            "count": 0,
            "results": [],
            "error": f"OpenFDA failed: {str(e)}"
        }


def normalize_drug_rxnorm(drug_name: str):
    try:
        response = requests.get(
            RXNORM_APPROX_URL,
            params={"term": drug_name, "maxEntries": 1},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("approximateGroup", {}).get("candidate", [])
        if not candidates:
            return {
                "input_name": drug_name,
                "matched": False,
                "rxcui": None,
                "properties": None,
            }

        best = candidates[0]
        rxcui = best.get("rxcui")

        if not rxcui:
            return {
                "input_name": drug_name,
                "matched": False,
                "rxcui": None,
                "properties": None,
            }

        prop_response = requests.get(
            RXNORM_PROPERTIES_URL.format(rxcui=rxcui),
            timeout=30
        )
        prop_response.raise_for_status()
        prop_data = prop_response.json()

        props = prop_data.get("properties", {}) or {}

        return {
            "input_name": drug_name,
            "matched": True,
            "match_score": best.get("score"),
            "rxcui": rxcui,
            "properties": {
                "name": props.get("name"),
                "synonym": props.get("synonym"),
                "tty": props.get("tty"),
                "umlscui": props.get("umlscui"),
            },
        }
    except Exception as e:
        return {
            "input_name": drug_name,
            "matched": False,
            "rxcui": None,
            "properties": None,
            "error": f"RxNorm failed: {str(e)}"
        }


def extract_clinical_context(payload: dict):
    medications = payload.get("medications", []) or []
    symptoms = payload.get("symptoms", []) or []
    diagnoses = payload.get("diagnoses", []) or []
    clinical_note = payload.get("clinical_note", "") or ""

    medication_results = []
    for med in medications:
        try:
            medication_results.append({
                "input_name": med,
                "rxnorm": normalize_drug_rxnorm(med),
                "openfda": search_openfda_drug(med),
            })
        except Exception as e:
            medication_results.append({
                "input_name": med,
                "error": str(e)
            })

    pubmed_queries = []
    for d in diagnoses:
        pubmed_queries.append(f"{d} treatment")
    for s in symptoms:
        pubmed_queries.append(f"{s} diagnosis")
    for med in medications:
        pubmed_queries.append(f"{med} adverse effects")

    literature = []
    seen = set()

    for query in pubmed_queries:
        if query not in seen:
            seen.add(query)
            try:
                literature.append(pubmed_lookup(query, retmax=1))
            except Exception as e:
                literature.append({
                    "query": query,
                    "count": 0,
                    "results": [],
                    "error": str(e)
                })

    return {
        "clinical_note": clinical_note,
        "structured_context": {
            "medications": medication_results,
            "symptoms": symptoms,
            "diagnoses": diagnoses,
            "literature": literature,
        }
    }