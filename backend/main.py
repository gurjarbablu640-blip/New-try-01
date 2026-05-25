"""
Salesoorja AI Sales Intelligence - FastAPI Application
=======================================================
Main application entry point with lifespan management.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings

# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# APPLICATION LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup/shutdown lifecycle.
    """

    logger.info("Salesoorja AI Sales Intelligence starting up...")

    yield

    logger.info("Salesoorja AI Sales Intelligence shutting down...")


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Salesoorja AI Sales Intelligence",
    version="2.0.0",
    description="AI-powered calibration sales intelligence platform",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

origins = [
    o.strip()
    for o in settings.CORS_ORIGINS.split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# IMPORT ROUTERS
# ============================================================

from routes.api import router as api_router  # noqa: E402
from routes.pipeline import router as pipeline_router  # noqa: E402
from routes.leads import router as leads_router  # noqa: E402


# ============================================================
# REGISTER ROUTERS
# ============================================================

app.include_router(api_router)
app.include_router(pipeline_router)
app.include_router(leads_router)


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "salesoorja-ai",
    }


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
async def root():
    return {
        "service": "Salesoorja AI Sales Intelligence",
        "version": "2.0.0",
        "docs": "/docs",
        "modules": [
            "Lead Ingestion Engine",
            "Buying Trigger Engine",
            "Hyper-Personalization Engine",
            "AI Outreach Synthesis",
            "Pipeline CRM",
            "Next Best Action Engine",
            "Semantic Search",
            "Lookalike Expansion",
            "ICP Learning Engine",
            "Buying Window Dashboard",
            "A/B Optimizer",
        ],
    }