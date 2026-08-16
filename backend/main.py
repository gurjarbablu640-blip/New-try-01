"""Oorja Sales OS FastAPI application."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings

logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Oorja Sales OS starting up...")
    yield
    logger.info("Oorja Sales OS shutting down...")


app = FastAPI(
    title="Oorja Sales OS",
    version="2.4.0",
    description="AI-powered sales operating system for Oorja Technical Services",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

from routes.api import router as api_router  # noqa: E402
from routes.pipeline import router as pipeline_router  # noqa: E402
from routes.leads import router as leads_router  # noqa: E402
from routes.scraper import router as scraper_router  # noqa: E402
from routes.outreach import router as outreach_router  # noqa: E402
from routes.activities import router as activities_router  # noqa: E402
from routes.export import router as export_router  # noqa: E402
from routes.orders import router as orders_router  # noqa: E402
from routes.sales_os import router as sales_os_router  # noqa: E402
from routes.knowledge import router as knowledge_router  # noqa: E402
from routes.web_research import router as research_router  # noqa: E402
from routes.campaigns import router as campaigns_router  # noqa: E402
from routes.competitors import router as competitors_router  # noqa: E402
from routes.learning_analytics import router as learning_analytics_router  # noqa: E402
from routes.assistant import router as assistant_router  # noqa: E402
from routes.company_360 import router as company_360_router  # noqa: E402
from routes.facilities import router as facilities_router  # noqa: E402
from routes.customer_assets import router as customer_assets_router  # noqa: E402
from routes.territory import router as territory_router  # noqa: E402

app.include_router(api_router)
app.include_router(pipeline_router)
app.include_router(leads_router)
app.include_router(scraper_router)
app.include_router(outreach_router)
app.include_router(activities_router)
app.include_router(export_router)
app.include_router(orders_router)
app.include_router(sales_os_router)
app.include_router(knowledge_router)
app.include_router(research_router)
app.include_router(campaigns_router)
app.include_router(competitors_router)
app.include_router(learning_analytics_router)
app.include_router(assistant_router)
app.include_router(company_360_router)
app.include_router(facilities_router)
app.include_router(customer_assets_router)
app.include_router(territory_router)


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
            "Lead Generation", "CRM", "AI Sales Intelligence", "Web Research",
            "Campaign Engine", "Quotation Intelligence", "Competitor Intelligence",
            "Oorja Knowledge Base", "Learning Engine", "Sales Analytics", "Company 360",
        ],
    }
