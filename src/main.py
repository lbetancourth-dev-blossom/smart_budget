"""src/main.py — FastAPI application entry point (DATA-1140)."""
from fastapi import FastAPI

from .api.router import router  # relative import — required for `uvicorn src.main:app`

app = FastAPI(
    title="Smart Budget API",
    description="Fase 0 — Sugerencias de presupuesto on-demand (DS-ML dev endpoint)",
    version="0.1.0",
)

app.include_router(router)
