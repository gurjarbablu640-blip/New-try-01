"""Settings & Customer Onboarding API Routes.

Provides endpoints for:
- Masked settings status retrieval
- Secure credential updating
- Connection testing for OpenAI, Gemini, Apollo, SMTP, and IMAP
- Customer/Prospect manual onboarding into CRM & Intelligence loop
"""
from datetime import date
from typing import Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from services.settings_manager import (
    get_masked_settings_status,
    update_settings,
    test_ai_provider_connection,
    test_apollo_connection,
    test_smtp_connection,
    test_imap_connection,
)
from services.customer_onboarding import onboard_manual_prospect

router = APIRouter(prefix="/api", tags=["Settings & Onboarding"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic Schemas
class SettingsUpdateRequest(BaseModel):
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    ORCHESTRATOR_GEMINI_MODEL: Optional[str] = None
    ORCHESTRATOR_PRIMARY_PROVIDER: Optional[str] = None
    ORCHESTRATOR_FALLBACK_PROVIDER: Optional[str] = None
    APOLLO_API_KEY: Optional[str] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: Optional[str] = None
    SMTP_USE_TLS: Optional[bool] = None
    OUTBOUND_TEST_MODE: Optional[bool] = None
    IMAP_HOST: Optional[str] = None
    IMAP_PORT: Optional[int] = None
    IMAP_USER: Optional[str] = None
    IMAP_PASSWORD: Optional[str] = None
    IMAP_USE_SSL: Optional[bool] = None
    SERPER_API_KEY: Optional[str] = None
    APIFY_API_TOKEN: Optional[str] = None
    PILOT_PHONE_NUMBER: Optional[str] = None


class TestAIRequest(BaseModel):
    provider: str = "gemini"  # openai or gemini


class ManualProspectRequest(BaseModel):
    company_name: str
    industry: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    facility: Optional[str] = None
    website: Optional[str] = None
    contact_name: Optional[str] = None
    contact_role: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    existing_vendor: Optional[str] = None
    calibration_requirement: Optional[str] = None
    instrument_categories: Optional[List[str]] = None
    last_calibration_date: Optional[date] = None
    next_calibration_due: Optional[date] = None
    notes: Optional[str] = None


# Settings Endpoints
@router.get("/settings/status")
def get_settings_status_endpoint():
    """Returns safe masked configuration status without exposing raw secrets."""
    return get_masked_settings_status()


@router.post("/settings/update")
def update_settings_endpoint(payload: SettingsUpdateRequest):
    """Securely updates settings and persists overrides."""
    return update_settings(payload.model_dump(exclude_unset=True))


@router.post("/settings/test-ai")
def test_ai_endpoint(payload: TestAIRequest):
    """Tests connection to OpenAI or Google Gemini."""
    return test_ai_provider_connection(payload.provider)


@router.post("/settings/test-apollo")
def test_apollo_endpoint():
    """Tests connection to Apollo API."""
    return test_apollo_connection()


@router.post("/settings/test-smtp")
def test_smtp_endpoint():
    """Tests connection to Outbound SMTP server."""
    return test_smtp_connection()


@router.post("/settings/test-imap")
def test_imap_endpoint():
    """Tests connection to Inbound IMAP server."""
    return test_imap_connection()


# Manual Prospect Onboarding Endpoint
@router.post("/companies/manual-onboarding")
def manual_prospect_onboarding_endpoint(payload: ManualProspectRequest, db: Session = Depends(get_db)):
    """Manually onboards a customer/prospect into CRM and seeds the intelligence loop."""
    try:
        res = onboard_manual_prospect(
            db=db,
            company_name=payload.company_name,
            industry=payload.industry,
            city=payload.city,
            state=payload.state,
            country=payload.country,
            facility=payload.facility,
            website=payload.website,
            contact_name=payload.contact_name,
            contact_role=payload.contact_role,
            contact_email=payload.contact_email,
            contact_phone=payload.contact_phone,
            existing_vendor=payload.existing_vendor,
            calibration_requirement=payload.calibration_requirement,
            instrument_categories=payload.instrument_categories,
            last_calibration_date=payload.last_calibration_date,
            next_calibration_due=payload.next_calibration_due,
            notes=payload.notes,
        )
        return res
    except ValueError as err:
        raise HTTPException(400, str(err))
    except Exception as err:
        raise HTTPException(500, f"Onboarding failed: {err}")
