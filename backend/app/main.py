import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db.database import init_db
from backend.app.routes import (
    extraction_routes,
    from_note_routes,
    openfda_routes,
    pubmed_routes,
    records_routes,
    rxnorm_routes,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Clinical Intelligence Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pubmed_routes.router)
app.include_router(openfda_routes.router)
app.include_router(rxnorm_routes.router)
app.include_router(extraction_routes.router)
app.include_router(from_note_routes.router)
app.include_router(records_routes.router)


@app.get("/")
def home():
    return {"message": "Backend running"}
