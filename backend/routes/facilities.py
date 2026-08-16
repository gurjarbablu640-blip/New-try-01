"""Facility / Plant management routes."""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.company import Company
from models.facility import Facility
from models.customer_asset import CustomerAsset

router = APIRouter(prefix="/api/facilities", tags=["Facilities"])


class FacilityCreate(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=300)
    plant_code: Optional[str] = None
    industrial_estate: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None


class FacilityUpdate(BaseModel):
    name: Optional[str] = None
    plant_code: Optional[str] = None
    industrial_estate: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    address: Optional[str] = None


def _serialize_facility(f: Facility, db: Session) -> dict:
    asset_count = db.query(CustomerAsset).filter(CustomerAsset.facility_id == f.id).count()
    return {
        "id": f.id,
        "company_id": f.company_id,
        "name": f.name,
        "plant_code": f.plant_code,
        "industrial_estate": f.industrial_estate,
        "city": f.city,
        "state": f.state,
        "address": f.address,
        "asset_count": asset_count,
        "created_at": f.created_at,
        "updated_at": f.updated_at,
    }


@router.post("")
def create_facility(payload: FacilityCreate, db: Session = Depends(get_db)):
    """Create a new facility / manufacturing plant under a company."""
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    facility = Facility(**payload.model_dump())
    db.add(facility)
    db.commit()
    db.refresh(facility)
    return _serialize_facility(facility, db)


@router.get("/{facility_id}")
def get_facility(facility_id: int, db: Session = Depends(get_db)):
    """Get facility details by ID."""
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return _serialize_facility(facility, db)


@router.get("/company/{company_id}")
def list_facilities_for_company(company_id: int, db: Session = Depends(get_db)):
    """List all facilities belonging to a company."""
    facilities = db.query(Facility).filter(Facility.company_id == company_id).order_by(Facility.name.asc()).all()
    return {
        "company_id": company_id,
        "total": len(facilities),
        "results": [_serialize_facility(f, db) for f in facilities],
    }


@router.put("/{facility_id}")
def update_facility(facility_id: int, payload: FacilityUpdate, db: Session = Depends(get_db)):
    """Update facility attributes."""
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(facility, k, v)

    db.commit()
    db.refresh(facility)
    return _serialize_facility(facility, db)


@router.delete("/{facility_id}")
def delete_facility(facility_id: int, db: Session = Depends(get_db)):
    """Delete a facility."""
    facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")

    db.delete(facility)
    db.commit()
    return {"message": "Facility deleted successfully", "id": facility_id}
