from fastapi import APIRouter, Query
from backend.app.utils.data_extractors import pubmed_lookup

router = APIRouter(prefix="/pubmed", tags=["PubMed"])


@router.get("/search")
def pubmed_search(query: str = Query(..., description="Search term for PubMed")):
    return pubmed_lookup(query)