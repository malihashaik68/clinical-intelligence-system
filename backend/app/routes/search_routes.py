from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.vector_service import search_similar_records

router = APIRouter(prefix="/search", tags=["Search"])


class SearchRequest(BaseModel):
    query: str


@router.post("/")
def search_records(payload: SearchRequest):
    results = search_similar_records(payload.query)
    return results