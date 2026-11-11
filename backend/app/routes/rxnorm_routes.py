from fastapi import APIRouter, Query
from backend.app.utils.data_extractors import normalize_drug_rxnorm

router = APIRouter(prefix="/rxnorm", tags=["RxNorm"])


@router.get("/normalize")
def rxnorm_normalize(drug_name: str = Query(..., description="Drug name")):
    return normalize_drug_rxnorm(drug_name)