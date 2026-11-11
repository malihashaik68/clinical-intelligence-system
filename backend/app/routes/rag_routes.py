from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.services.rag_service import generate_rag_response

router = APIRouter(prefix="/rag", tags=["RAG"])


class RagRequest(BaseModel):
    query: str


@router.post("/")
def run_rag(payload: RagRequest):
    return generate_rag_response(payload.query)