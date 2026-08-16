"""Calibration Domain Intelligence Service.

Provides:
- Deterministic calibration due-date evaluation (OVERDUE, ACTIVE, UPCOMING, FUTURE)
- Asset-driven buying window calculation
- Reusable NABL scope and service-fit matching
- Company asset summary aggregator
"""
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models.customer_asset import CustomerAsset
from models.facility import Facility


def calculate_asset_due_status(
    due_date: Optional[date],
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Evaluate calibration due status and active buying window for an individual asset.
    Deterministic bands:
    - OVERDUE: due_date < today
    - ACTIVE (Active Buying Window): 0 <= days <= 60
    - UPCOMING: 60 < days <= 120
    - FUTURE: days > 120
    - UNKNOWN: due_date is None
    """
    if not due_date:
        return {
            "due_status": "UNKNOWN",
            "days_until_due": None,
            "urgency_level": "LOW",
            "is_buying_window_active": False,
            "reason": "No calibration due date recorded on asset.",
        }

    ref = reference_date or date.today()
    days_until = (due_date - ref).days

    if days_until < 0:
        return {
            "due_status": "OVERDUE",
            "days_until_due": days_until,
            "urgency_level": "CRITICAL",
            "is_buying_window_active": True,
            "reason": f"Calibration is overdue by {abs(days_until)} days.",
        }
    elif days_until <= 30:
        return {
            "due_status": "ACTIVE",
            "days_until_due": days_until,
            "urgency_level": "HIGH",
            "is_buying_window_active": True,
            "reason": f"Calibration due within {days_until} days (immediate 30-day window).",
        }
    elif days_until <= 60:
        return {
            "due_status": "ACTIVE",
            "days_until_due": days_until,
            "urgency_level": "MEDIUM",
            "is_buying_window_active": True,
            "reason": f"Calibration due within {days_until} days (active 60-day window).",
        }
    elif days_until <= 120:
        return {
            "due_status": "UPCOMING",
            "days_until_due": days_until,
            "urgency_level": "LOW",
            "is_buying_window_active": False,
            "reason": f"Calibration due in {days_until} days (upcoming pipeline).",
        }
    else:
        return {
            "due_status": "FUTURE",
            "days_until_due": days_until,
            "urgency_level": "LOW",
            "is_buying_window_active": False,
            "reason": f"Calibration valid for {days_until} days.",
        }


def match_nabl_service_fit(
    instrument_name: str,
    parameter: Optional[str] = None,
    range_value: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministic NABL service fit evaluator for Oorja Technical Services scope.
    Returns:
    - FULL_SCOPE: Direct in-house NABL accredited parameter
    - SUBCONTRACT_REQUIRED: Recognized industrial instrument requiring authorized subcontracting lab
    - OUT_OF_SCOPE: Non-calibration / non-standard equipment
    """
    name = (instrument_name or "").lower().strip()
    param = (parameter or "").lower().strip()
    combined = f"{name} {param} {(range_value or '').lower()}"

    # 1. Pressure & Vacuum (Core In-House NABL Scope)
    pressure_keywords = [
        "pressure gauge", "vacuum gauge", "transmitter", "dp transmitter",
        "pressure switch", "manometer", "barometer", "dead weight", "hydrostatic",
        "pressure calibrator", "compound gauge", "magnehelic",
    ]
    if any(k in combined for k in pressure_keywords) or "pressure" in param or "bar" in combined or "psi" in combined:
        return {
            "fit_status": "FULL_SCOPE",
            "discipline": "Pressure & Vacuum",
            "nabl_accredited": True,
            "reason": "Direct in-house NABL scope (-0.95 bar to 700 bar).",
        }

    # 2. Thermal & Temperature (Core In-House NABL Scope)
    thermal_keywords = [
        "temperature", "rtd", "pt100", "thermocouple", "thermometer",
        "pyrometer", "temperature controller", "temperature indicator",
        "oven", "furnace", "freezer", "incubator", "bath", "data logger",
    ]
    if any(k in combined for k in thermal_keywords) or "temperature" in param or "thermal" in param or "°c" in combined:
        return {
            "fit_status": "FULL_SCOPE",
            "discipline": "Thermal",
            "nabl_accredited": True,
            "reason": "Direct in-house NABL scope (-40°C to 1200°C).",
        }

    # 3. Electro-Technical (Core In-House NABL Scope)
    electro_keywords = [
        "multimeter", "clamp meter", "insulation tester", "megger", "earth tester",
        "voltmeter", "ammeter", "wattmeter", "power analyzer", "oscilloscope",
        "frequency counter", "timer", "decade box", "high voltage", "hipot",
    ]
    if any(k in combined for k in electro_keywords) or "electrical" in param or "voltage" in param or "current" in param:
        return {
            "fit_status": "FULL_SCOPE",
            "discipline": "Electro-Technical",
            "nabl_accredited": True,
            "reason": "Direct in-house NABL scope (Voltage, Current, Resistance, Frequency, Time).",
        }

    # 4. Mechanical & Dimensional (Core In-House NABL Scope)
    mech_keywords = [
        "caliper", "vernier", "micrometer", "dial gauge", "height gauge",
        "feeler gauge", "pin gauge", "torque wrench", "bore gauge", "bevel protractor",
        "pressure relief valve", "prv", "safety valve", "test bench",
    ]
    if any(k in combined for k in mech_keywords) or "dimensional" in param or "mechanical" in param:
        return {
            "fit_status": "FULL_SCOPE",
            "discipline": "Mechanical & Dimensional",
            "nabl_accredited": True,
            "reason": "Direct in-house NABL scope for dimensional & mechanical instruments.",
        }

    # 5. Mass & Volume (Core In-House NABL Scope)
    mass_keywords = [
        "weighing balance", "scale", "standard weight", "pipette", "micropipette",
        "burette", "measuring cylinder", "flask",
    ]
    if any(k in combined for k in mass_keywords) or "mass" in param or "volume" in param:
        return {
            "fit_status": "FULL_SCOPE",
            "discipline": "Mass & Volume",
            "nabl_accredited": True,
            "reason": "Direct in-house NABL scope for weighing balances and volumetric apparatus.",
        }

    # 6. Specialized Analytical (Subcontract Required)
    subcontract_keywords = [
        "gas chromatograph", "gc-ms", "hplc", "spectrophotometer", "mass spectrometer",
        "radiation", "survey meter", "sound level meter", "acoustic", "particle counter",
        "turbidity", "viscometer", "refractometer", "toc analyzer",
    ]
    if any(k in combined for k in subcontract_keywords) or "analytical" in param:
        return {
            "fit_status": "SUBCONTRACT_REQUIRED",
            "discipline": "Specialized Analytical",
            "nabl_accredited": False,
            "reason": "Specialized instrument requiring authorized NABL partner lab subcontracting.",
        }

    # Default Out of Scope / Unknown
    return {
        "fit_status": "OUT_OF_SCOPE",
        "discipline": "Other",
        "nabl_accredited": False,
        "reason": "Non-standard parameter or non-calibratable plant asset.",
    }


def calculate_company_asset_calibration_summary(
    company_id: int,
    db: Session,
    reference_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Aggregate all physical CustomerAsset records for a company to calculate:
    - Asset counts by due status (Overdue, Active 60-day, Due in 30-day, Upcoming)
    - Overall company calibration buying window
    - NABL fit distribution
    - Facility breakdown
    """
    ref = reference_date or date.today()
    assets = (
        db.query(CustomerAsset)
        .filter(CustomerAsset.company_id == company_id, CustomerAsset.status == "Active")
        .all()
    )

    total_assets = len(assets)
    overdue_count = 0
    due_30_count = 0
    due_60_count = 0
    upcoming_count = 0
    future_count = 0
    unknown_count = 0

    full_scope_count = 0
    subcontract_count = 0
    out_of_scope_count = 0

    earliest_due: Optional[date] = None
    disciplines = set()

    for a in assets:
        status_info = calculate_asset_due_status(a.calibration_due_date, reference_date=ref)
        due_status = status_info["due_status"]

        if due_status == "OVERDUE":
            overdue_count += 1
        elif due_status == "ACTIVE":
            if (status_info.get("days_until_due") or 0) <= 30:
                due_30_count += 1
            due_60_count += 1
        elif due_status == "UPCOMING":
            upcoming_count += 1
        elif due_status == "FUTURE":
            future_count += 1
        else:
            unknown_count += 1

        if a.calibration_due_date:
            if earliest_due is None or a.calibration_due_date < earliest_due:
                earliest_due = a.calibration_due_date

        # NABL Fit
        nabl_fit = match_nabl_service_fit(a.instrument_name, a.parameter, a.range_value)
        if nabl_fit["fit_status"] == "FULL_SCOPE":
            full_scope_count += 1
        elif nabl_fit["fit_status"] == "SUBCONTRACT_REQUIRED":
            subcontract_count += 1
        else:
            out_of_scope_count += 1

        disciplines.add(nabl_fit["discipline"])

    # Determine asset-driven buying window category
    if overdue_count > 0 or due_30_count > 0:
        buying_window = "next_30_days"
        urgency_summary = f"{overdue_count + due_30_count} instruments due/overdue for calibration (High NABL Urgency)"
    elif due_60_count > 0:
        buying_window = "next_60_days"
        urgency_summary = f"{due_60_count} instruments due for calibration within 60 days"
    elif upcoming_count > 0:
        buying_window = "next_90_days"
        urgency_summary = f"{upcoming_count} instruments due for calibration in next 90-120 days"
    else:
        buying_window = "unknown"
        urgency_summary = "No immediate calibration due dates detected."

    # Facility breakdown
    facilities = db.query(Facility).filter(Facility.company_id == company_id).all()

    return {
        "company_id": company_id,
        "total_assets": total_assets,
        "facilities_count": len(facilities),
        "due_metrics": {
            "overdue": overdue_count,
            "due_next_30_days": due_30_count,
            "due_next_60_days": due_60_count,
            "upcoming_90_to_120_days": upcoming_count,
            "future": future_count,
            "unknown": unknown_count,
            "earliest_due_date": earliest_due.isoformat() if earliest_due else None,
        },
        "buying_window": buying_window,
        "is_active_buying_window": (overdue_count > 0 or due_60_count > 0),
        "urgency_summary": urgency_summary,
        "nabl_fit_summary": {
            "full_scope_count": full_scope_count,
            "subcontract_count": subcontract_count,
            "out_of_scope_count": out_of_scope_count,
            "full_scope_ratio": round(full_scope_count / total_assets, 2) if total_assets > 0 else 0.0,
            "disciplines": list(disciplines),
        },
    }
