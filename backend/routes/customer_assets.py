"""Customer Asset & Calibration Due Intelligence API routes."""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.company import Company
from models.customer_asset import CustomerAsset
from models.facility import Facility
from services.calibration_intelligence import (
    calculate_asset_due_status,
    calculate_company_asset_calibration_summary,
    match_nabl_service_fit,
)

router = APIRouter(prefix="/api/customer-assets", tags=["Customer Assets"])


class CustomerAssetCreate(BaseModel):
    company_id: int
    facility_id: Optional[int] = None
    instrument_id: Optional[int] = None
    asset_tag: Optional[str] = None
    serial_number: Optional[str] = None
    instrument_name: str = Field(min_length=1, max_length=500)
    make: Optional[str] = None
    model: Optional[str] = None
    parameter: Optional[str] = None
    range_value: Optional[str] = None
    location_in_plant: Optional[str] = None
    last_calibrated_date: Optional[date] = None
    calibration_due_date: Optional[date] = None
    calibration_interval_months: int = Field(default=12, ge=1, le=60)
    certificate_number: Optional[str] = None
    status: str = "Active"


class CustomerAssetUpdate(BaseModel):
    facility_id: Optional[int] = None
    instrument_id: Optional[int] = None
    asset_tag: Optional[str] = None
    serial_number: Optional[str] = None
    instrument_name: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    parameter: Optional[str] = None
    range_value: Optional[str] = None
    location_in_plant: Optional[str] = None
    last_calibrated_date: Optional[date] = None
    calibration_due_date: Optional[date] = None
    calibration_interval_months: Optional[int] = None
    certificate_number: Optional[str] = None
    status: Optional[str] = None


def _serialize_asset(a: CustomerAsset) -> dict:
    due_status = calculate_asset_due_status(a.calibration_due_date)
    nabl_fit = match_nabl_service_fit(a.instrument_name, a.parameter, a.range_value)

    return {
        "id": a.id,
        "company_id": a.company_id,
        "facility_id": a.facility_id,
        "instrument_id": a.instrument_id,
        "asset_tag": a.asset_tag,
        "serial_number": a.serial_number,
        "instrument_name": a.instrument_name,
        "make": a.make,
        "model": a.model,
        "parameter": a.parameter,
        "range_value": a.range_value,
        "location_in_plant": a.location_in_plant,
        "last_calibrated_date": a.last_calibrated_date.isoformat() if a.last_calibrated_date else None,
        "calibration_due_date": a.calibration_due_date.isoformat() if a.calibration_due_date else None,
        "calibration_interval_months": a.calibration_interval_months,
        "certificate_number": a.certificate_number,
        "status": a.status,
        "due_status": due_status["due_status"],
        "days_until_due": due_status["days_until_due"],
        "urgency_level": due_status["urgency_level"],
        "is_buying_window_active": due_status["is_buying_window_active"],
        "nabl_fit": nabl_fit,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


@router.post("")
def create_customer_asset(payload: CustomerAssetCreate, db: Session = Depends(get_db)):
    """Create a new physical customer asset / instrument."""
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    if payload.facility_id:
        facility = db.query(Facility).filter(Facility.id == payload.facility_id).first()
        if not facility:
            raise HTTPException(status_code=404, detail="Facility not found")

    asset = CustomerAsset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _serialize_asset(asset)


@router.get("/due-soon")
def list_assets_due_soon(days: int = Query(default=60, ge=1, le=365), db: Session = Depends(get_db)):
    """List all assets across all companies due for calibration within N days (Active Buying Window)."""
    today = date.today()
    assets = (
        db.query(CustomerAsset)
        .filter(
            CustomerAsset.status == "Active",
            CustomerAsset.calibration_due_date.isnot(None),
        )
        .all()
    )

    filtered = []
    for a in assets:
        status_info = calculate_asset_due_status(a.calibration_due_date, reference_date=today)
        days_until = status_info.get("days_until_due")
        if days_until is not None and 0 <= days_until <= days:
            filtered.append(_serialize_asset(a))

    filtered.sort(key=lambda x: x["days_until_due"] if x["days_until_due"] is not None else 999)
    return {"total": len(filtered), "filter_days": days, "results": filtered}


@router.get("/overdue")
def list_overdue_assets(db: Session = Depends(get_db)):
    """List all assets across all companies that are currently overdue for calibration."""
    today = date.today()
    assets = (
        db.query(CustomerAsset)
        .filter(
            CustomerAsset.status == "Active",
            CustomerAsset.calibration_due_date.isnot(None),
            CustomerAsset.calibration_due_date < today,
        )
        .order_by(CustomerAsset.calibration_due_date.asc())
        .all()
    )
    return {"total": len(assets), "results": [_serialize_asset(a) for a in assets]}


@router.get("/company/{company_id}")
def list_assets_for_company(company_id: int, db: Session = Depends(get_db)):
    """List all customer assets for a specific company with full calibration intelligence."""
    assets = (
        db.query(CustomerAsset)
        .filter(CustomerAsset.company_id == company_id)
        .order_by(CustomerAsset.calibration_due_date.asc().nullslast())
        .all()
    )
    summary = calculate_company_asset_calibration_summary(company_id, db)

    return {
        "company_id": company_id,
        "total": len(assets),
        "calibration_summary": summary,
        "results": [_serialize_asset(a) for a in assets],
    }


@router.get("/company/{company_id}/calibration-summary")
def get_company_calibration_summary(company_id: int, db: Session = Depends(get_db)):
    """Get the aggregate calibration due metrics, buying window, and NABL scope coverage for a company."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return calculate_company_asset_calibration_summary(company_id, db)


@router.get("/facility/{facility_id}")
def list_assets_for_facility(facility_id: int, db: Session = Depends(get_db)):
    """List all assets situated in a specific facility/plant."""
    assets = (
        db.query(CustomerAsset)
        .filter(CustomerAsset.facility_id == facility_id)
        .order_by(CustomerAsset.calibration_due_date.asc().nullslast())
        .all()
    )
    return {"facility_id": facility_id, "total": len(assets), "results": [_serialize_asset(a) for a in assets]}


@router.get("/{asset_id}")
def get_customer_asset(asset_id: int, db: Session = Depends(get_db)):
    """Get details of a single customer asset."""
    asset = db.query(CustomerAsset).filter(CustomerAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Customer asset not found")
    return _serialize_asset(asset)


@router.put("/{asset_id}")
def update_customer_asset(asset_id: int, payload: CustomerAssetUpdate, db: Session = Depends(get_db)):
    """Update customer asset details."""
    asset = db.query(CustomerAsset).filter(CustomerAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Customer asset not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(asset, k, v)

    db.commit()
    db.refresh(asset)
    return _serialize_asset(asset)


@router.delete("/{asset_id}")
def delete_customer_asset(asset_id: int, db: Session = Depends(get_db)):
    """Delete a customer asset."""
    asset = db.query(CustomerAsset).filter(CustomerAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Customer asset not found")

    db.delete(asset)
    db.commit()
    return {"message": "Customer asset deleted successfully", "id": asset_id}
