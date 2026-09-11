"""Evidence gates for production outreach readiness.

This module is deliberately side-effect free.  It evaluates an evidence
snapshot and never performs enrichment, DNS/MX checks, or sends mail.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

GATE_NAMES = (
    "trigger_current",
    "exact_facility",
    "calibration_demand",
    "technical_capability",
    "timing",
    "correct_person",
    "reachable_email",
)
READY_FOR_EMAIL = "READY_FOR_EMAIL"
HOT = "HOT"
BLOCKED = "BLOCKED"

from services.oorja_capability_service import (
    CONFIRMED_NABL_SCOPE,
    KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED,
    OORJA_OFFICIAL_CERTIFICATE_NO,
    OUT_OF_SCOPE,
    POSSIBLE,
    UNKNOWN,
    classify_capability,
    classify_technical_scope_batch,
)


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str


def _truth(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _truth(value.get(k))
            for k in ("verified", "passed", "active", "valid", "confirmed", "status")
            if k in value
        )
    return value is True or (isinstance(value, (int, float)) and value > 0) or (
        isinstance(value, str) and value.strip().lower() in {"true", "yes", "verified", "current", "active", "confirmed"}
    )


def classify_technical_scope(
    scope_items: list[str],
    certificate_no: str | None = OORJA_OFFICIAL_CERTIFICATE_NO,
) -> dict[str, Any]:
    """Strictly classify requested instruments against Oorja NABL schedule CC-3963."""
    res = classify_technical_scope_batch(scope_items, certificate_no=certificate_no)
    confirmed_items = [c["item"] for c in res["CONFIRMED_NABL_SCOPE"]]
    return {
        "certificate_no": res["certificate_no"],
        "CONFIRMED_NABL_SCOPE": res["CONFIRMED_NABL_SCOPE"],
        "CONFIRMED_OORJA_SCOPE": confirmed_items,  # compatibility alias
        "KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED": res["KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED"],
        "POSSIBLE": res["POSSIBLE"],
        "POSSIBLE_OORJA_SCOPE": res["POSSIBLE"],  # compatibility alias
        "UNKNOWN": res["UNKNOWN"],
        "OUT_OF_SCOPE": res["OUT_OF_SCOPE"],
    }


def _trigger_passes(value: Any, now_dt: datetime | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Enforce trigger recency and trigger-to-facility alignment policies."""
    if not isinstance(value, Mapping):
        passed = _truth(value)
        return passed, ("evidence present" if passed else "missing or insufficient trigger evidence"), {}

    now_dt = now_dt or datetime(2026, 9, 10, tzinfo=timezone.utc)
    trigger_date_str = str(value.get("trigger_date") or value.get("source_date") or value.get("date") or "").strip()
    ongoing_evidence = str(value.get("ongoing_activity_evidence") or value.get("continued_activity") or "").strip()
    future_commissioning = bool(value.get("future_commissioning") or value.get("completion_in_future"))
    current_milestone = bool(value.get("current_milestone_verified") or value.get("active_hiring_verified"))

    recency_days = None
    if trigger_date_str:
        try:
            dt = datetime.strptime(trigger_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            recency_days = (now_dt - dt).days
        except ValueError:
            try:
                dt = datetime.strptime(trigger_date_str, "%Y").replace(tzinfo=timezone.utc)
                recency_days = (now_dt - dt).days
            except ValueError:
                pass

    if recency_days is None:
        recency_days = int(value.get("recency_days") or 0)

    # 1. Recency Policy:
    # 0 - 180 days: CURRENT
    # 181 - 365 days: RECENT (Requires ongoing activity evidence)
    # > 365 days: STALE (Requires future commissioning or current milestone to pass)
    if recency_days <= 180:
        recency_status = "CURRENT"
        passed = True
        reason = f"Trigger is CURRENT ({recency_days} days old)"
    elif 181 <= recency_days <= 365:
        recency_status = "RECENT"
        if ongoing_evidence or current_milestone or future_commissioning:
            passed = True
            reason = f"Trigger is RECENT ({recency_days} days old) with verified ongoing activity"
        else:
            passed = False
            reason = f"Trigger is RECENT ({recency_days} days old) but lacks required evidence of ongoing activity"
    else:
        recency_status = "STALE"
        if future_commissioning or ongoing_evidence or current_milestone:
            passed = True
            reason = f"Trigger is >365 days old ({recency_days} days) but multi-year execution is confirmed active"
        else:
            passed = False
            reason = f"Trigger is STALE (>365 days old, {recency_days} days) with no newer source or ongoing milestone proving activity"

    # 2. Trigger-to-Facility linkage
    tf_conf = str(value.get("trigger_facility_confidence") or "").upper()
    if tf_conf == "WEAK":
        passed = False
        reason = "Trigger-to-facility linkage is WEAK; corporate trigger is not proven to affect this specific facility"

    metadata = {
        "trigger_date": trigger_date_str,
        "source_date": str(value.get("source_date") or trigger_date_str),
        "recency_days": recency_days,
        "recency_status": recency_status,
        "ongoing_activity_evidence": ongoing_evidence,
        "recency_reason": reason,
        "trigger_facility_confidence": tf_conf or "NOT_EVALUATED",
    }
    return passed, reason, metadata


def _facility_passes(value: Any, evidence: Mapping[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Enforce exact facility verification and trigger-facility alignment.

    Address Precision Requirements:
    - EXACT_STREET: always sufficient with DIRECT or STRONG linkage.
    - INDUSTRIAL_AREA: sufficient with DIRECT or STRONG linkage when uniquely identified.
    - CITY_ONLY: satisfies facility qualification ONLY when:
      A. The trigger explicitly identifies the facility unambiguously (DIRECT linkage), AND
      B. Independent evidence shows there is only one relevant company manufacturing facility
         matching that location/context (single_manufacturing_site_in_city / unique_facility).
      If company has multiple plants in the city, or if only generic presence exists, it FAILS.
    - REGION_ONLY or UNKNOWN: always fails.
    """
    basic_passed = _truth(value) if not isinstance(value, Mapping) else (
        _truth(value.get("verified")) or _truth(value.get("facility_verified")) or bool(str(value.get("address") or "").strip())
    )
    if not basic_passed:
        return False, "Facility address is missing or unverified", {}

    tf_conf = "DIRECT"
    tf_evidence = ""
    address_precision = "UNKNOWN"
    generic_presence = False
    multi_plant = False
    single_facility = False
    unambiguous_facility = True

    if isinstance(value, Mapping):
        tf_conf = str(value.get("trigger_facility_confidence") or value.get("linkage_confidence") or "DIRECT").upper()
        tf_evidence = str(value.get("trigger_facility_evidence") or value.get("linkage_evidence") or "")
        raw_prec = value.get("address_precision")
        if raw_prec:
            address_precision = str(raw_prec).upper()
        else:
            addr_lower = str(value.get("address") or "").lower()
            if any(k in addr_lower for k in ["plot", "sector", "gate", "street", "road", "survey no"]):
                address_precision = "EXACT_STREET"
            elif any(k in addr_lower for k in ["midc", "gidc", "riico", "sipcot", "imt", "sez", "industrial"]):
                address_precision = "INDUSTRIAL_AREA"
            elif addr_lower:
                address_precision = "CITY_ONLY"
            else:
                address_precision = "UNKNOWN"
        generic_presence = bool(value.get("generic_presence") or value.get("is_generic_presence"))
        multi_plant = bool(value.get("multi_plant_in_city") or value.get("is_multi_plant") or value.get("multiple_plants"))
        single_facility = bool(
            value.get("single_manufacturing_site_in_city")
            or value.get("is_unique_facility_in_city")
            or value.get("unique_facility")
            or value.get("is_unique_facility")
            or value.get("single_plant_in_city")
        )
        unambiguous_facility = bool(value.get("trigger_unambiguous_facility", True) and value.get("unambiguous_facility", True))
    else:
        trig = evidence.get("trigger_current") or evidence.get("trigger")
        if isinstance(trig, Mapping):
            tf_conf = str(trig.get("trigger_facility_confidence") or "DIRECT").upper()
            tf_evidence = str(trig.get("trigger_facility_evidence") or "")

    # Generic company presence in same city is never an exact manufacturing facility
    if generic_presence:
        return False, "Generic company presence in city is insufficient; physical manufacturing plant required", {
            "trigger_facility_confidence": tf_conf,
            "address_precision": address_precision,
            "trigger_facility_evidence": tf_evidence,
            "generic_presence": True,
        }

    if tf_conf in ("WEAK", "UNKNOWN"):
        return False, "Trigger-to-facility linkage is WEAK; corporate trigger is not proven to affect this specific facility", {
            "trigger_facility_confidence": tf_conf,
            "address_precision": address_precision,
            "trigger_facility_evidence": tf_evidence or "Corporate announcement does not name this plant location",
        }

    # Region-only and Unknown precision always fail
    if address_precision in ("REGION_ONLY", "UNKNOWN"):
        return False, f"Address precision {address_precision} is insufficient for exact facility verification", {
            "trigger_facility_confidence": tf_conf,
            "address_precision": address_precision,
            "trigger_facility_evidence": tf_evidence,
        }

    # City-only precision requirements:
    # A. trigger explicitly identifies the facility unambiguously (tf_conf == "DIRECT" and unambiguous_facility)
    # AND
    # B. independent evidence shows only one relevant company manufacturing facility in that city/context
    if address_precision == "CITY_ONLY":
        if tf_conf != "DIRECT":
            return False, (
                f"Address precision is CITY_ONLY and trigger-facility confidence is {tf_conf}. "
                "City-only facility evidence requires DIRECT trigger linkage."
            ), {
                "trigger_facility_confidence": tf_conf,
                "address_precision": address_precision,
                "trigger_facility_evidence": tf_evidence,
            }

        if multi_plant:
            return False, (
                "City-only precision is insufficient for multi-plant company in this city. "
                "Exact plant/street or industrial area must be specified."
            ), {
                "trigger_facility_confidence": tf_conf,
                "address_precision": address_precision,
                "multi_plant_in_city": True,
            }

        if not single_facility or not unambiguous_facility:
            return False, (
                "City-only precision satisfies facility qualification only when the trigger explicitly "
                "identifies the facility unambiguously AND independent evidence shows only one relevant "
                "company manufacturing facility matching that location."
            ), {
                "trigger_facility_confidence": tf_conf,
                "address_precision": address_precision,
                "single_manufacturing_site_in_city": single_facility,
                "trigger_unambiguous_facility": unambiguous_facility,
            }

    # Industrial area with unique plant and STRONG/DIRECT corroboration passes
    return True, f"Facility verified with {tf_conf} trigger linkage (address precision: {address_precision})", {
        "trigger_facility_confidence": tf_conf,
        "address_precision": address_precision,
        "trigger_facility_evidence": tf_evidence,
        "single_manufacturing_site_in_city": single_facility,
    }


def _person_passes(value: Any) -> tuple[bool, str, dict[str, Any]]:
    """Enforce human name validity, employment, duties, and strict person-facility linkage."""
    if not isinstance(value, Mapping):
        passed = _truth(value)
        return passed, ("evidence present" if passed else "missing or insufficient person evidence"), {}

    # Person name validation
    name = str(value.get("name") or value.get("full_name") or value.get("candidate_name") or "").strip()
    val_status = str(value.get("person_name_validation") or value.get("name_validation_status") or "").upper()
    if not val_status and name:
        from services.contact_confidence import validate_person_name
        val_res = validate_person_name(name)
        val_status = val_res["person_name_validation"]

    if val_status == "INVALID_ROLE_TEXT":
        return False, f"Person candidate name '{name}' is invalid role or functional text (INVALID_ROLE_TEXT)", {
            "person_name_validation": "INVALID_ROLE_TEXT",
            "candidate_name": name,
        }

    emp = _truth(value.get("employment_verified"))
    duties = _truth(value.get("duties_verified"))
    if not (emp and duties):
        missing = []
        if not emp:
            missing.append("employment_verified")
        if not duties:
            missing.append("duties_verified")
        return False, f"Person verification missing: {', '.join(missing)}", {
            "person_name_validation": val_status or "UNKNOWN",
        }

    # Person-to-facility linkage classification:
    # FACILITY_OWNER, GROUP_FUNCTION_OWNER, FUNCTIONALLY_RELEVANT, COMPANY_ONLY, UNKNOWN
    classification = str(
        value.get("facility_classification")
        or value.get("classification")
        or value.get("person_facility_classification")
        or ""
    ).upper()

    if not classification:
        if _truth(value.get("facility_verified")):
            classification = "FACILITY_OWNER"
        elif _truth(value.get("group_ownership_verified")):
            classification = "GROUP_FUNCTION_OWNER"
        else:
            classification = "COMPANY_ONLY"

    if classification == "COMPANY_ONLY":
        return False, "Person has company-level title only; plant facility ownership is not proven", {
            "classification": classification,
            "person_name_validation": val_status or "VALID",
        }
    elif classification == "UNKNOWN":
        return False, "Person-to-facility linkage is UNKNOWN", {
            "classification": classification,
            "person_name_validation": val_status or "VALID",
        }
    elif classification == "FUNCTIONALLY_RELEVANT":
        if _truth(value.get("facility_verified")):
            return True, "Person is functionally relevant with verified plant responsibilities", {
                "classification": classification,
                "person_name_validation": val_status or "VALID",
            }
        return False, "Person has functional relevance but lacks verified facility or group-wide plant ownership", {
            "classification": classification,
            "person_name_validation": val_status or "VALID",
        }
    elif classification in (
        "FACILITY_OWNER",
        "GROUP_FUNCTION_OWNER",
        "DIRECT_CALIBRATION_OWNER",
        "METROLOGY_OWNER",
        "STRONG_PLANT_QUALITY_OWNER",
    ):
        return True, f"Person verified as {classification}", {
            "classification": classification,
            "person_name_validation": val_status or "VALID",
        }
    elif classification == "GENERAL_QUALITY":
        return False, "Generic Quality Engineer at unknown site (GENERAL_QUALITY / HOLD)", {
            "classification": classification,
            "person_name_validation": val_status or "VALID",
        }
    else:
        return False, f"Invalid person facility classification: {classification}", {
            "classification": classification,
            "person_name_validation": val_status or "VALID",
        }


def _technical_capability_passes(value: Any) -> tuple[bool, str, dict[str, Any]]:
    """Enforce technical capability verification against confirmed Oorja CC-3963 NABL scope."""
    if not isinstance(value, Mapping):
        passed = _truth(value)
        return passed, ("Technical capability confirmed" if passed else "Technical capability missing"), {}

    scope_items = value.get("scope_items") or value.get("instruments") or value.get("calibration_scope") or []
    if isinstance(scope_items, str):
        scope_items = [s.strip() for s in scope_items.split(",") if s.strip()]

    cert_no = str(value.get("certificate_no") or OORJA_OFFICIAL_CERTIFICATE_NO).strip()

    if not scope_items:
        passed = _truth(value.get("verified")) or _truth(value.get("capability_confirmed"))
        return passed, ("evidence present" if passed else "no instruments or calibration scope specified"), {}

    analysis = classify_technical_scope(scope_items, certificate_no=cert_no)
    confirmed = analysis["CONFIRMED_NABL_SCOPE"]
    out_of_scope = analysis["OUT_OF_SCOPE"]

    if out_of_scope and not confirmed:
        return (
            False,
            f"Requested scope contains out-of-scope services ({', '.join(out_of_scope)}) not accredited under Oorja CC-3963",
            analysis,
        )

    if not confirmed:
        return (
            False,
            f"None of the requested instruments match Oorja's verified NABL scope ({cert_no})",
            analysis,
        )

    if out_of_scope and confirmed:
        return (
            True,
            f"Technical capability confirmed for {len(confirmed)} instruments; {len(out_of_scope)} items are out-of-scope",
            analysis,
        )

    return (
        True,
        f"All {len(confirmed)} instruments verified under Oorja NABL certificate {cert_no}",
        analysis,
    )


def _calibration_demand_passes(value: Any) -> tuple[bool, str, dict[str, Any]]:
    """Enforce baseline calibration demand verification.

    Baseline calibration demand can be established by:
    - IATF 16949 / ISO 9001 / ISO 17025 compliance
    - Precision manufacturing operations requiring periodic recalibration
    - Documented customer assets requiring calibration
    - Calibration management demand / annual budgeting / periodic calibration statements
    """
    if not isinstance(value, Mapping):
        passed = _truth(value)
        return (
            passed,
            ("Baseline calibration demand established" if passed else "Missing baseline calibration demand evidence"),
            {"baseline_demand": passed},
        )

    basis = str(
        value.get("demand_basis")
        or value.get("reason")
        or value.get("evidence")
        or value.get("description")
        or ""
    ).strip()
    verified = _truth(value.get("verified")) or _truth(value.get("demand_verified")) or bool(basis)

    if verified:
        return (
            True,
            f"Baseline calibration demand confirmed ({basis or 'compliance/periodic standard'})",
            {"baseline_demand": True, "demand_basis": basis or "periodic recalibration requirement"},
        )
    return (
        False,
        "Missing or unverified baseline calibration demand",
        {"baseline_demand": False, "demand_basis": ""},
    )


def _timing_passes(value: Any, evidence: Mapping[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    """Enforce current buying intent / timing window policy.

    SEPARATE BASELINE_CALIBRATION_DEMAND from CURRENT_BUYING_INTENT / TIMING.

    Generic recurring statements:
      - 'annual calibration', 'periodic calibration', 'ISO requirement',
      - 'regular budgeting', 'calendar cycle', 'recurring need'
      establish baseline demand but MUST NOT automatically pass the timing gate!

    Evidence that MAY pass timing:
      - current expansion / plant startup / capacity addition
      - commissioning / equipment installation
      - QA/metrology hiring tied to active work
      - specific audit/qualification window (dated/upcoming)
      - active procurement / RFQ / tender
      - scheduled plant shutdown / maintenance activity
      - contract/vendor renewal evidence
      - recent production ramp / new production line
      - dated current activity
    """
    if value is None or value is False:
        return False, "No current buying timing or procurement window evidence exists", {"current_timing_verified": False}

    timing_text = ""
    event_type = ""
    is_active_window = False

    if isinstance(value, Mapping):
        timing_text = str(
            value.get("buying_window")
            or value.get("timing_evidence")
            or value.get("event")
            or value.get("reason")
            or ""
        ).strip().lower()
        event_type = str(value.get("event_type") or value.get("type") or "").strip().lower()
        is_active_window = bool(
            value.get("active_buying_window")
            or value.get("is_buying_window_active")
            or value.get("current_timing_verified")
            or value.get("active_rfq")
            or value.get("upcoming_audit")
            or value.get("current_expansion")
            or value.get("active_commissioning")
        )
    elif isinstance(value, str):
        timing_text = value.strip().lower()

    generic_patterns = [
        "annual calibration",
        "periodic calibration",
        "iso requirement",
        "regular budgeting",
        "budgeting cycle",
        "calendar cycle",
        "recurring need",
        "standard requirement",
        "periodic recalibration",
        "annual cycle",
        "general timing",
        "recurring requirement",
        "recurring calibration",
        "standard recurring",
        "regular calibration",
    ]

    # If only generic statement without active event flag:
    if timing_text and any(gp in timing_text for gp in generic_patterns):
        if not is_active_window and not any(
            act in timing_text
            for act in [
                "rfq", "tender", "procurement", "audit scheduled", "audit due",
                "commissioning", "installation", "expansion", "shutdown", "renewal", "ramp"
            ]
        ):
            return (
                False,
                f"Generic recurring requirement ('{timing_text}') establishes baseline demand but does not prove a current buying window or active timing trigger",
                {"current_timing_verified": False, "timing_evidence": timing_text, "is_generic_baseline_only": True},
            )

    active_triggers = [
        "expansion", "commissioning", "installation", "startup", "plant startup",
        "hiring", "qa hiring", "metrology hiring", "audit window", "audit due",
        "rfq", "procurement", "tender", "shutdown", "maintenance shutdown",
        "vendor renewal", "contract renewal", "production ramp", "active buying window",
        "immediate_to_30_days", "immediate_to_60_days", "active", "urgent"
    ]

    has_active_signal = (
        is_active_window
        or any(at in timing_text for at in active_triggers)
        or any(at in event_type for at in active_triggers)
    )

    if has_active_signal:
        return (
            True,
            f"Current buying timing confirmed: {timing_text or event_type or 'active procurement window'}",
            {"current_timing_verified": True, "timing_evidence": timing_text or event_type},
        )

    # NOTE: Plain boolean True is NOT accepted here. Timing evidence must be a Mapping
    # with actual keywords derived from the source (event_type, timing_evidence, etc.).
    # Fabricated generic strings like "expansion capex plant commissioning" cannot pass.
    return (
        False,
        f"Missing dated buying-window evidence for timing (provided: '{timing_text}')",
        {"current_timing_verified": False, "timing_evidence": timing_text},
    )


def _email_passes(value: Any) -> bool:
    if isinstance(value, Mapping):
        status = str(value.get("status") or value.get("verification_status") or "").lower()
        if status in {"mx_only", "mx", "unverified", "risky", "unknown", "not_found"}:
            return False
        address = str(value.get("address") or value.get("email") or "").strip()
        if not address:
            return False

        # Generic corporate, investor relations, careers, support, and procurement emails cannot satisfy reachable-person gate
        email_class = str(value.get("email_classification") or value.get("classification") or "").upper()
        if not email_class:
            from services.contact_confidence import classify_email_address
            email_class = classify_email_address(address)["classification"]

        if email_class in {"GENERIC_CORPORATE", "INVESTOR_RELATIONS", "CAREERS", "SUPPORT", "PROCUREMENT_GENERIC"}:
            return False

        trusted = _truth(value.get("mailbox_verified")) or _truth(value.get("trusted_verification"))
        assessment = str(value.get("contact_confidence") or "").upper()
        return (status in {"verified", "email_verified", "deliverable"} and trusted and assessment in {"VERIFIED", "HIGH", "DIRECT"})
    return False


def _evidence_value(evidence: Mapping[str, Any], name: str) -> Any:
    aliases = {
        "trigger_current": ("trigger_current", "current_trigger", "trigger"),
        "exact_facility": ("exact_facility", "facility", "facility_verified"),
        "calibration_demand": ("calibration_demand", "demand", "calibration_need"),
        "technical_capability": ("technical_capability", "capability", "technical_fit"),
        "timing": ("timing", "buying_window", "timing_current"),
        "correct_person": ("correct_person", "person_verified", "decision_maker", "person"),
        "reachable_email": ("reachable_email", "email_reachable", "email"),
    }
    for key in aliases[name]:
        if key in evidence:
            return evidence[key]
    return None


PROVENANCE_REAL = "REAL"
PROVENANCE_TEST = "TEST"
PROVENANCE_MOCK = "MOCK"
PROVENANCE_SYNTHETIC = "SYNTHETIC"


def evaluate_opportunity_gates(evidence: Mapping[str, Any], *, production: bool = True) -> dict[str, Any]:
    """Evaluate all seven gates against explicit evidence with tightened rules."""
    evidence = evidence or {}
    source = str(evidence.get("evidence_mode") or evidence.get("source") or "").lower()
    synthetic = bool(evidence.get("synthetic") or evidence.get("mock_mode") or evidence.get("demo_mode"))

    if synthetic or "synthetic" in source:
        provenance = PROVENANCE_SYNTHETIC
    elif source in {"mock", "demo"} or "mock" in source or "demo" in source:
        provenance = PROVENANCE_MOCK
    elif source in {"test", "fixture"}:
        provenance = PROVENANCE_TEST
    else:
        provenance = PROVENANCE_REAL

    blocked = production and provenance != PROVENANCE_REAL
    results: list[GateResult] = []
    gate_details: dict[str, Any] = {}

    for name in GATE_NAMES:
        value = _evidence_value(evidence, name)
        if name == "trigger_current":
            passed, reason, meta = _trigger_passes(value)
        elif name == "exact_facility":
            passed, reason, meta = _facility_passes(value, evidence)
        elif name == "calibration_demand":
            passed, reason, meta = _calibration_demand_passes(value)
        elif name == "technical_capability":
            passed, reason, meta = _technical_capability_passes(value)
        elif name == "timing":
            passed, reason, meta = _timing_passes(value, evidence)
        elif name == "correct_person":
            passed, reason, meta = _person_passes(value)
        elif name == "reachable_email":
            passed = _email_passes(value)
            reason = "evidence present" if passed else "missing or insufficient email verification"
            meta = {}
        else:
            passed = _truth(value)
            reason = "evidence present" if passed else f"missing or insufficient {name} evidence"
            meta = {}

        results.append(GateResult(name, passed, reason))
        gate_details[name] = {"passed": passed, "reason": reason, **meta}

    score = float(evidence.get("score") or evidence.get("icp_score") or 0)
    all_passed = all(g.passed for g in results)
    ready = all_passed and score >= 90 and not blocked
    status = HOT if ready and score >= 95 else READY_FOR_EMAIL if ready else BLOCKED
    if blocked:
        reason = f"Synthetic, mock, demo, or test evidence (provenance: {provenance}) cannot qualify a production opportunity"
    elif not all_passed:
        reason = "Required opportunity gate(s) failed: " + ", ".join(g.name for g in results if not g.passed)
    elif score < 90:
        reason = f"Score ({score:g}) is below production readiness threshold (90)"
    else:
        reason = "All seven evidence gates passed"

    return {
        "status": status,
        "ready_for_email": ready,
        "hot": status == HOT,
        "score": score,
        "provenance": provenance,
        "reason": reason,
        "gates": gate_details,
    }


def evaluate_company_opportunity(db: Any, company_id: int, *, production: bool = True) -> dict[str, Any]:
    """Build an evidence snapshot from existing records and evaluate it."""
    from models.company import Company
    from models.customer_asset import CustomerAsset
    from models.decision_maker_candidate import DecisionMakerCandidate
    from models.facility import Facility
    from models.intent_signal import CompanyIntentSignal
    from models.person import Person
    from models.website_intel import CompanyWebsiteIntel
    from datetime import datetime

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}
    signals = db.query(CompanyIntentSignal).filter(CompanyIntentSignal.company_id == company_id, CompanyIntentSignal.is_active == 1).all()
    facilities = db.query(Facility).filter(Facility.company_id == company_id).all()
    assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == company_id).all()
    intel = db.query(CompanyWebsiteIntel).filter(CompanyWebsiteIntel.company_id == company_id).first()
    persons = db.query(Person).filter(Person.company_id == company_id).all()
    candidates = db.query(DecisionMakerCandidate).filter(DecisionMakerCandidate.company_id == company_id).all()
    current_trigger = any(s.source_url and s.source_snippet and (not s.expires_at or s.expires_at >= datetime.utcnow()) for s in signals)
    exact_facility = any(f.city or f.address or f.plant_code for f in facilities)
    demand = bool(assets) or any(s.signal_type in {"NABL_RENEWAL_DUE", "ISO_AUDIT_WINDOW", "COMPETITOR_PAIN"} for s in signals)
    capability = bool(assets) or bool(intel and (intel.instruments_found or intel.services_offered))
    timing = bool(company.buying_window and str(company.buying_window).lower() not in {"unknown", "none"}) or any(s.expires_at for s in signals)
    verified_candidate = any(c.candidate_company_match and c.candidate_facility and c.score_role_relevance >= 0.5 and c.verification_status in {"PERSON_PUBLICLY_VERIFIED", "EMAIL_VERIFIED", "APOLLO_ENRICHED"} for c in candidates)
    verified_person = any(p.full_name and p.designation and p.is_decision_maker == 1 and (verified_candidate or p.discovery_status in {"PERSON_PUBLICLY_VERIFIED", "EMAIL_VERIFIED"}) for p in persons)
    co_source = str(company.source or "").lower()
    co_name = str(company.name or "").lower()
    is_synthetic = bool(
        "synthetic" in co_source or "demo" in co_source or "mock" in co_source
        or "[mock]" in co_name or "demo " in co_name
        or any(getattr(s, "is_mock", False) for s in signals)
        or any(getattr(p, "discovery_source", "") in {"mock", "synthetic", "demo"} for p in persons)
    )
    result = evaluate_opportunity_gates(
        {
            "trigger_current": current_trigger,
            "exact_facility": exact_facility,
            "calibration_demand": demand,
            "technical_capability": capability,
            "timing": timing,
            "correct_person": person,
            "reachable_email": email,
            "score": company.icp_score or 0,
            "source": "SYNTHETIC" if is_synthetic else company.source,
            "synthetic": is_synthetic,
        },
        production=production,
    )
    result.update({"company_id": company.id, "company_name": company.name})
    return result


def evaluate_apollo_credit_gate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Strictly evaluate whether a lead qualifies for paid Apollo contact enrichment.

    All of the following MUST be satisfied:
    A. Current/valid trigger passes (recency CURRENT or RECENT with ongoing activity)
    B. Trigger-facility linkage is DIRECT or STRONG
    C. Exact facility verified
    D. Calibration consequence matches Oorja scope (CONFIRMED_NABL_SCOPE or verified service)
    E. Buying timing is sufficiently current (active expansion, commissioning, hiring, etc.)
    F. A REAL HUMAN decision-maker is confidently identified (person_name_validation in {"VALID", "PROBABLE"})
    G. Person classification is FACILITY_OWNER, GROUP_FUNCTION_OWNER, or strong FUNCTIONALLY_RELEVANT
       (COMPANY_ONLY, UNKNOWN, INVALID_ROLE_TEXT must NEVER qualify!)
    H. Missing person-specific email or direct mobile is the main remaining blocker.
    """
    from services.contact_confidence import classify_email_address, validate_person_name

    evidence = evidence or {}
    criteria = {}

    # A. Trigger current
    trig_val = _evidence_value(evidence, "trigger_current")
    trig_pass, trig_reason, _ = _trigger_passes(trig_val)
    criteria["trigger_current"] = {"passed": trig_pass, "reason": trig_reason}

    # B. Trigger-facility linkage
    tf_conf = "DIRECT"
    if isinstance(trig_val, Mapping):
        tf_conf = str(trig_val.get("trigger_facility_confidence") or trig_val.get("linkage_confidence") or "DIRECT").upper()
    tf_pass = tf_conf in {"DIRECT", "STRONG"}
    criteria["trigger_facility_linkage"] = {
        "passed": tf_pass,
        "confidence": tf_conf,
        "reason": f"Linkage is {tf_conf}" if tf_pass else "Trigger-to-facility linkage is WEAK",
    }

    # C. Exact facility verified
    fac_val = _evidence_value(evidence, "exact_facility")
    fac_pass, fac_reason, _ = _facility_passes(fac_val, evidence)
    criteria["exact_facility"] = {"passed": fac_pass, "reason": fac_reason}

    # D. Calibration consequence / Oorja scope
    cap_val = _evidence_value(evidence, "technical_capability")
    cap_pass, cap_reason, _ = _technical_capability_passes(cap_val)
    criteria["technical_capability"] = {"passed": cap_pass, "reason": cap_reason}

    # E. Buying timing
    timing_val = _evidence_value(evidence, "timing")
    timing_pass, timing_reason, _ = _timing_passes(timing_val, evidence)
    criteria["timing"] = {"passed": timing_pass, "reason": timing_reason}

    # F. Real human decision maker (NOT invalid role text)
    person_val = _evidence_value(evidence, "correct_person")
    person_dict = person_val if isinstance(person_val, Mapping) else {}
    candidate_name = str(person_dict.get("name") or person_dict.get("full_name") or person_dict.get("candidate_name") or "").strip()
    val_res = validate_person_name(candidate_name)
    name_val_status = val_res["person_name_validation"]
    human_pass = (name_val_status in {"VALID", "PROBABLE"} and bool(candidate_name))
    criteria["real_human_person"] = {
        "passed": human_pass,
        "name": candidate_name,
        "person_name_validation": name_val_status,
        "reason": f"Candidate '{candidate_name}' is {name_val_status}" if human_pass else f"Candidate name '{candidate_name}' is {name_val_status} (not a real human name)",
    }

    # G. Person facility classification
    person_class = str(
        person_dict.get("facility_classification")
        or person_dict.get("classification")
        or person_dict.get("person_facility_classification")
        or ""
    ).upper()
    if not person_class:
        if _truth(person_dict.get("facility_verified")):
            person_class = "FACILITY_OWNER"
        else:
            person_class = "COMPANY_ONLY"

    if person_class in {"COMPANY_ONLY", "UNKNOWN", "INVALID_ROLE_TEXT"}:
        class_pass = False
        class_reason = f"Person classification '{person_class}' cannot trigger Apollo (requires plant or group authority)"
    elif person_class in {"FACILITY_OWNER", "GROUP_FUNCTION_OWNER"}:
        class_pass = True
        class_reason = f"Person is verified as {person_class}"
    elif person_class == "FUNCTIONALLY_RELEVANT":
        # Allowed only if facility verified or strong supporting role evidence
        is_strong = _truth(person_dict.get("facility_verified")) or _truth(person_dict.get("current_employment_verified"))
        class_pass = bool(is_strong)
        class_reason = "Functionally relevant person with verified plant role" if class_pass else "Functionally relevant person lacks sufficient plant-level evidence"
    else:
        class_pass = False
        class_reason = f"Unrecognized person classification: {person_class}"

    criteria["person_authority"] = {
        "passed": class_pass,
        "classification": person_class,
        "reason": class_reason,
    }

    # H. Missing direct contact info
    email_val = _evidence_value(evidence, "reachable_email")
    email_dict = email_val if isinstance(email_val, Mapping) else {}
    curr_addr = str(email_dict.get("address") or email_dict.get("email") or "").strip()
    email_class = classify_email_address(curr_addr)["classification"]
    email_status = str(email_dict.get("status") or email_dict.get("verification_status") or "").upper()

    # If email is already VERIFIED and PERSON_SPECIFIC, direct contact is already present
    has_verified_direct_email = (email_status in {"VERIFIED", "EMAIL_VERIFIED"} and email_class == "PERSON_SPECIFIC")
    phone_val = evidence.get("phone") or person_dict.get("phone")
    phone_dict = phone_val if isinstance(phone_val, Mapping) else {}
    has_direct_mobile = bool(phone_dict.get("is_direct_mobile"))

    needs_contact = not (has_verified_direct_email and has_direct_mobile)
    criteria["missing_direct_contact"] = {
        "passed": needs_contact,
        "has_verified_direct_email": has_verified_direct_email,
        "has_direct_mobile": has_direct_mobile,
        "reason": "Direct person email or mobile is missing (Apollo can provide direct contact)" if needs_contact else "Direct verified email and mobile already exist",
    }

    all_passed = (
        trig_pass and tf_pass and fac_pass and cap_pass and timing_pass
        and human_pass and class_pass and needs_contact
    )

    if all_passed:
        status = "QUALIFIED_FOR_APOLLO"
        reason = f"All 8 Apollo criteria met: Real human decision-maker '{candidate_name}' ({person_class}) at verified facility with active trigger; missing direct contact data."
    else:
        status = "NOT_QUALIFIED"
        failed = [k for k, v in criteria.items() if not v["passed"]]
        failed_reasons = [criteria[k]["reason"] for k in failed[:2]]
        reason = f"Apollo gate blocked ({', '.join(failed)}): {'; '.join(failed_reasons)}"

    return {
        "passed": all_passed,
        "apollo_recommended": all_passed,
        "status": status,
        "reason": reason,
        "criteria": criteria,
    }
