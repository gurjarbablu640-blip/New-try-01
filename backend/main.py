"""
Salesoorja AI Sales Intelligence - FastAPI Application
=======================================================
Main application entry point with lifespan management.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    logger.info("Salesoorja AI Sales Intelligence starting up...")
    yield
    logger.info("Salesoorja AI Sales Intelligence shutting down...")


app = FastAPI(
    title="Salesoorja AI Sales Intelligence",
    version="2.0.0",
    description="Full AI Sales Intelligence system with trigger-based outreach",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from backend.routes.api import router as api_router  # noqa: E402
from backend.routes.pipeline import router as pipeline_router  # noqa: E402

app.include_router(api_router)
app.include_router(pipeline_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "salesoorja-ai"}


@app.get("/")
async def root():
    return {
        "service": "Salesoorja AI Sales Intelligence",
        "version": "2.0.0",
        "docs": "/docs",
        "modules": [
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
