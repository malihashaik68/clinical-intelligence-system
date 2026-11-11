from fastapi import APIRouter, Query
from backend.app.utils.data_extractors import search_openfda_drug

router = APIRouter(prefix="/openfda", tags=["OpenFDA"])


@router.get("/drug")
def openfda_drug_search(drug_name: str = Query(..., description="Drug name")):
    return search_openfda_drug(drug_name)