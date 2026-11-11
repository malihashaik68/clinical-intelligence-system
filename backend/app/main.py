from fastapi import FastAPI
from backend.app.routes import (
    pubmed_routes,
    openfda_routes,
    rxnorm_routes,
    extraction_routes,
    from_note_routes,
    records_routes,
)

app = FastAPI(title="Clinical Intelligence Backend")

app.include_router(pubmed_routes.router)
app.include_router(openfda_routes.router)
app.include_router(rxnorm_routes.router)
app.include_router(extraction_routes.router)
app.include_router(from_note_routes.router)
app.include_router(records_routes.router)


@app.get("/")
def home():
    return {"message": "Backend running"}