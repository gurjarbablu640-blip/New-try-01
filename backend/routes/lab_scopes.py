"""NABL Lab Scope Intelligence API routes.

Provides endpoints for importing, reviewing, searching, and comparing NABL accredited
calibration laboratory scopes across Pan-India.
"""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.lab_scope import NABLLabScope, NABLScopeParameter
from services.lab_scope_parser import (
    parse_nabl_scope_text,
    ingest_lab_scope_record,
    search_labs_by_parameter,
    compare_lab_scopes,
)

router = APIRouter(prefix="/api/lab-scopes", tags=["NABL Scope Intelligence"])


class LabScopeManualCreate(BaseModel):
    lab_name: str
    certificate_no: str
    accreditation_standard: str = "ISO/IEC 17025:2017"
    validity_date: Optional[str] = None
    state: str = "Pan-India"
    city: Optional[str] = None
    source_file: Optional[str] = "Manual Input"
    source_reference: Optional[str] = "User Entry"
    raw_scope_text: Optional[str] = None
    parameters: Optional[List[Dict[str, Any]]] = None


@router.get("")
def list_lab_scopes(
    state: Optional[str] = None,
    discipline: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Lists all accredited NABL laboratories in the database."""
    q = db.query(NABLLabScope).filter(NABLLabScope.active == True)
    if state and state != "All" and state != "PAN INDIA":
        q = q.filter(NABLLabScope.state.ilike(f"%{state}%"))
    if discipline and discipline != "All":
        q = q.filter(NABLLabScope.discipline_summary.ilike(f"%{discipline}%"))

    labs = q.order_by(NABLLabScope.lab_name.asc()).limit(limit).all()
    return {
        "status": "SUCCESS",
        "data_source": "VERIFIED_NABL_LAB_SCOPES",
        "total": len(labs),
        "results": [
            {
                "id": lab.id,
                "lab_name": lab.lab_name,
                "certificate_no": lab.certificate_no,
                "accreditation_standard": lab.accreditation_standard,
                "discipline_summary": lab.discipline_summary,
                "validity_date": lab.validity_date,
                "state": lab.state,
                "city": lab.city,
                "parameters_count": len(lab.parameters),
                "source_file": lab.source_file,
                "source_reference": lab.source_reference,
            }
            for lab in labs
        ],
    }


@router.get("/{lab_id}")
def get_lab_scope_details(lab_id: int, db: Session = Depends(get_db)):
    """Retrieves full parameter-level calibration schedule for a specific lab."""
    lab = db.query(NABLLabScope).filter(NABLLabScope.id == lab_id).first()
    if not lab:
        raise HTTPException(404, "Laboratory scope record not found.")

    return {
        "id": lab.id,
        "lab_name": lab.lab_name,
        "certificate_no": lab.certificate_no,
        "accreditation_standard": lab.accreditation_standard,
        "discipline_summary": lab.discipline_summary,
        "validity_date": lab.validity_date,
        "state": lab.state,
        "city": lab.city,
        "source_file": lab.source_file,
        "source_reference": lab.source_reference,
        "parameters": [
            {
                "id": p.id,
                "discipline": p.discipline,
                "parameter_name": p.parameter_name,
                "instrument_or_gage": p.instrument_or_gage,
                "range_description": p.range_description,
                "cmc_uncertainty": p.cmc_uncertainty,
                "is_onsite": p.is_onsite,
                "service_capability": p.service_capability,
                "source_page": p.source_page,
            }
            for p in lab.parameters
        ],
    }


@router.post("/import")
def import_lab_scope(payload: LabScopeManualCreate, db: Session = Depends(get_db)):
    """Imports or parses a new NABL Lab Scope record with verified parameters."""
    if payload.raw_scope_text:
        parsed = parse_nabl_scope_text(
            payload.raw_scope_text,
            source_file=payload.source_file or "raw_text_input",
            source_reference=payload.source_reference or "Manual Entry",
        )
        parsed["lab_name"] = payload.lab_name or parsed["lab_name"]
        parsed["certificate_no"] = payload.certificate_no or parsed["certificate_no"]
        parsed["state"] = payload.state or parsed["state"]
        parsed["city"] = payload.city or parsed["city"]
    else:
        parsed = {
            "lab_name": payload.lab_name,
            "certificate_no": payload.certificate_no,
            "accreditation_standard": payload.accreditation_standard,
            "validity_date": payload.validity_date or "Active",
            "state": payload.state,
            "city": payload.city,
            "source_file": payload.source_file,
            "source_reference": payload.source_reference,
            "parameters": payload.parameters or [],
        }

    lab = ingest_lab_scope_record(db, parsed)
    return {
        "status": "IMPORTED",
        "lab_id": lab.id,
        "lab_name": lab.lab_name,
        "certificate_no": lab.certificate_no,
        "parameters_indexed": len(lab.parameters),
    }


@router.post("/upload-document")
async def upload_scope_document(
    file: UploadFile = File(...),
    lab_name: Optional[str] = None,
    state: Optional[str] = "Pan-India",
    db: Session = Depends(get_db),
):
    """Accepts uploaded PDF/CSV/Text NABL scope document, parses parameters, and returns review preview."""
    content = await file.read()
    text_content = content.decode("utf-8", errors="ignore")

    parsed = parse_nabl_scope_text(
        text_content,
        source_file=file.filename,
        source_reference=f"Upload: {file.filename}",
    )
    if lab_name:
        parsed["lab_name"] = lab_name
    if state:
        parsed["state"] = state

    return {
        "status": "PARSED_FOR_REVIEW",
        "preview": parsed,
        "total_parameters_detected": len(parsed.get("parameters", [])),
        "message": "Review extracted parameters and submit to /api/lab-scopes/import to persist into intelligence database.",
    }


@router.get("/search/parameters")
def search_parameters(
    q: str = Query(..., min_length=1, description="Instrument or parameter name (e.g. micrometer, temperature, cmm)"),
    discipline: Optional[str] = "All",
    state: Optional[str] = "PAN INDIA",
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Searches accredited laboratories across India for specific parameter capabilities."""
    results = search_labs_by_parameter(db, query=q, discipline=discipline, state=state, limit=limit)
    return {
        "query": q,
        "discipline": discipline,
        "state_filter": state,
        "total_matches": len(results),
        "results": results,
    }


@router.get("/analytics/compare")
def compare_two_labs(
    lab1_id: int = Query(..., description="First laboratory ID"),
    lab2_id: int = Query(..., description="Second laboratory ID"),
    db: Session = Depends(get_db),
):
    """Factual parameter-level scope comparison between two accredited laboratories."""
    return compare_lab_scopes(db, lab1_id, lab2_id)
