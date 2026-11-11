import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.db.database import init_db
from backend.app.routes.deps import current_user
from backend.app.routes import (
    analytics_routes,
    auth_routes,
    extraction_routes,
    from_note_routes,
    health_routes,
    openfda_routes,
    patient_routes,
    pubmed_routes,
    rag_routes,
    records_routes,
    rxnorm_routes,
    search_routes,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.getenv("SEED_DEMO_DATA", "1") == "1":
        from backend.app.seed import seed_demo_data
        seed_demo_data()
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
# Public: reference lookups and stateless analysis (no patient data stored or returned)
app.include_router(extraction_routes.router)
app.include_router(health_routes.router)
app.include_router(auth_routes.router)

# Login required: everything that stores or returns clinical records
login_required = [Depends(current_user)]
app.include_router(patient_routes.router)
app.include_router(from_note_routes.router, dependencies=login_required)
app.include_router(records_routes.router, dependencies=login_required)
app.include_router(search_routes.router, dependencies=login_required)
app.include_router(rag_routes.router, dependencies=login_required)
app.include_router(analytics_routes.router, dependencies=login_required)


@app.get("/")
def home():
    return {"message": "Backend running"}
