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

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Oorja Sales OS starting up...")
    yield
    logger.info("Oorja Sales OS shutting down...")


app = FastAPI(
    title="Oorja Sales OS",
    version="2.1.0",
    description="AI-powered sales operating system for Oorja Technical Services",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes.api import router as api_router  # noqa: E402
from routes.pipeline import router as pipeline_router  # noqa: E402
from routes.leads import router as leads_router  # noqa: E402
from routes.scraper import router as scraper_router  # noqa: E402
from routes.outreach import router as outreach_router  # noqa: E402
from routes.activities import router as activities_router  # noqa: E402
from routes.export import router as export_router  # noqa: E402
from routes.orders import router as orders_router  # noqa: E402
from routes.sales_os import router as sales_os_router  # noqa: E402

app.include_router(api_router)
app.include_router(pipeline_router)
app.include_router(leads_router)
app.include_router(scraper_router)
app.include_router(outreach_router)
app.include_router(activities_router)
app.include_router(export_router)
app.include_router(orders_router)
app.include_router(sales_os_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "oorja-sales-os", "version": app.version}


@app.get("/")
async def root():
    return {
        "service": "Oorja Sales OS",
        "version": app.version,
        "docs": "/docs",
        "status": "running",
        "core_modules": [
            "Lead Generation",
            "CRM",
            "AI Sales Intelligence",
            "Web Research",
            "Campaign Engine",
            "Quotation Intelligence",
            "Competitor Intelligence",
            "Oorja Knowledge Base",
            "Learning Engine",
            "Sales Analytics",
        ],
    }
