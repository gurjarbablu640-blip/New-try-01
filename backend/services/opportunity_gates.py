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

# ── Oorja Certified Scope Constants ─────────────────────────────────────
OORJA_CONFIRMED_SCOPE = {
    "dimensional": {
        "cmm", "coordinate measuring machine", "vernier caliper", "caliper",
        "depth gauge", "micrometer", "internal micrometer", "external micrometer",
        "dial indicator", "dial gauge", "plunger gauge", "height master",
        "height gauge", "gauge block", "surface plate", "optical flat",
        "pin gauge", "snap gauge", "plug gauge", "thread gauge"
    },
    "pressure_torque": {
        "pressure gauge", "pressure transmitter", "pressure transducer",
        "digital pressure gauge", "vacuum gauge", "dead weight tester",
        "torque wrench", "torque transducer", "digital torque tester",
        "analytical balance", "precision balance", "standard weights"
    },
    "thermal": {
        "rtd", "rtd pt100", "pt100", "temperature sensor", "thermocouple",
        "thermocouple j", "thermocouple k", "temperature calibrator bath",
        "dry block calibrator", "environmental chamber", "test chamber",
        "muffle furnace", "hot air oven", "incubator", "digital thermometer",
        "glass thermometer", "hygrometer", "temperature datalogger"
    },
    "electro_technical": {
        "digital multimeter", "multimeter", "voltmeter", "ammeter",
        "process calibrator", "loop calibrator", "insulation tester",
        "megohmmeter", "decade resistance box", "power meter", "clamp meter"
    }
}

OORJA_OUT_OF_SCOPE = {
    "metallurgical testing", "metallurgical", "spectrometer", "optical emission spectrometer",
    "xrf", "x-ray fluorescence", "ultrasonic flaw detector", "flaw detector",
    "tensile destruction testing", "destructive testing", "chemical assay",
    "chromatography", "hplc testing", "gc testing", "radiation meter"
}


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


def classify_technical_scope(scope_items: list[str]) -> dict[str, Any]:
    """Split requested instruments into Oorja certified scope vs out-of-scope."""
    confirmed = []
    out_of_scope = []
    possible = []
    unknown = []

    for item in scope_items:
        clean = str(item).lower().strip()
        # Check out of scope first
        if any(oos in clean for oos in OORJA_OUT_OF_SCOPE):
            out_of_scope.append(item)
            continue

        # Check confirmed scope disciplines
        is_confirmed = False
        for disc, keywords in OORJA_CONFIRMED_SCOPE.items():
            if any(kw in clean for kw in keywords):
                confirmed.append(item)
                is_confirmed = True
                break
        if is_confirmed:
            continue

        # Check possible general measurement words
        if any(w in clean for w in ["gauge", "meter", "sensor", "transmitter", "calibrat"]):
            possible.append(item)
        else:
            unknown.append(item)

    return {
        "CONFIRMED_OORJA_SCOPE": confirmed,
        "OUT_OF_SCOPE": out_of_scope,
        "POSSIBLE_OORJA_SCOPE": possible,
        "UNKNOWN": unknown,
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
    """Enforce exact facility verification and trigger-facility alignment."""
    basic_passed = _truth(value) if not isinstance(value, Mapping) else (
        _truth(value.get("verified")) or _truth(value.get("facility_verified")) or bool(str(value.get("address") or "").strip())
    )
    if not basic_passed:
        return False, "Facility address is missing or unverified", {}

    tf_conf = "DIRECT"
    tf_evidence = ""
    if isinstance(value, Mapping):
        tf_conf = str(value.get("trigger_facility_confidence") or value.get("linkage_confidence") or "DIRECT").upper()
        tf_evidence = str(value.get("trigger_facility_evidence") or value.get("linkage_evidence") or "")
    else:
        trig = evidence.get("trigger_current") or evidence.get("trigger")
        if isinstance(trig, Mapping):
            tf_conf = str(trig.get("trigger_facility_confidence") or "DIRECT").upper()
            tf_evidence = str(trig.get("trigger_facility_evidence") or "")

    if tf_conf == "WEAK":
        return False, "Trigger-to-facility linkage is WEAK; corporate trigger is not proven to affect this specific facility", {
            "trigger_facility_confidence": "WEAK",
            "trigger_facility_evidence": tf_evidence or "Corporate announcement does not name this plant location",
        }

    return True, f"Facility verified with {tf_conf} trigger linkage", {
        "trigger_facility_confidence": tf_conf,
        "trigger_facility_evidence": tf_evidence,
    }


def _person_passes(value: Any) -> tuple[bool, str, dict[str, Any]]:
    """Enforce employment, duties, and strict person-facility linkage."""
    if not isinstance(value, Mapping):
        passed = _truth(value)
        return passed, ("evidence present" if passed else "missing or insufficient person evidence"), {}

    emp = _truth(value.get("employment_verified"))
    duties = _truth(value.get("duties_verified"))
    if not (emp and duties):
        missing = []
        if not emp:
            missing.append("employment_verified")
        if not duties:
            missing.append("duties_verified")
        return False, f"Person verification missing: {', '.join(missing)}", {}

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
        return False, "Person has company-level title only; plant facility ownership is not proven", {"classification": classification}
    elif classification == "UNKNOWN":
        return False, "Person-to-facility linkage is UNKNOWN", {"classification": classification}
    elif classification == "FUNCTIONALLY_RELEVANT":
        if _truth(value.get("facility_verified")):
            return True, "Person is functionally relevant with verified plant responsibilities", {"classification": classification}
        return False, "Person has functional relevance but lacks verified facility or group-wide plant ownership", {"classification": classification}
    elif classification in ("FACILITY_OWNER", "GROUP_FUNCTION_OWNER"):
        return True, f"Person verified as {classification}", {"classification": classification}
    else:
        return False, f"Invalid person facility classification: {classification}", {"classification": classification}


def _technical_capability_passes(value: Any) -> tuple[bool, str, dict[str, Any]]:
    """Enforce technical capability verification against confirmed Oorja NABL scope."""
    if not isinstance(value, Mapping):
        passed = _truth(value)
        return passed, ("Technical capability confirmed" if passed else "Technical capability missing"), {}

    scope_items = value.get("scope_items") or value.get("instruments") or value.get("calibration_scope") or []
    if isinstance(scope_items, str):
        scope_items = [s.strip() for s in scope_items.split(",") if s.strip()]

    if not scope_items:
        passed = _truth(value.get("verified")) or _truth(value.get("capability_confirmed"))
        return passed, ("evidence present" if passed else "no instruments or calibration scope specified"), {}

    analysis = classify_technical_scope(scope_items)
    confirmed = analysis["CONFIRMED_OORJA_SCOPE"]
    out_of_scope = analysis["OUT_OF_SCOPE"]

    if out_of_scope and not confirmed:
        return False, f"Requested scope contains out-of-scope services ({', '.join(out_of_scope)}) not certified under Oorja NABL accreditation", analysis

    if not confirmed:
        return False, "None of the requested instruments match Oorja's certified NABL accreditation scope", analysis

    if out_of_scope and confirmed:
        return True, f"Technical capability confirmed for {len(confirmed)} instruments; {len(out_of_scope)} items are out-of-scope", analysis

    return True, f"All {len(confirmed)} instruments are within Oorja certified NABL scope", analysis


def _email_passes(value: Any) -> bool:
    if isinstance(value, Mapping):
        status = str(value.get("status") or value.get("verification_status") or "").lower()
        if status in {"mx_only", "mx", "unverified", "risky", "unknown", "not_found"}:
            return False
        trusted = _truth(value.get("mailbox_verified")) or _truth(value.get("trusted_verification"))
        assessment = str(value.get("contact_confidence") or "").upper()
        address = value.get("address") or value.get("email")
        return (status in {"verified", "email_verified", "deliverable"} and trusted and assessment in {"VERIFIED", "HIGH", "DIRECT"}
                and bool(str(address or "").strip()))
    return False


def _evidence_value(evidence: Mapping[str, Any], name: str) -> Any:
    aliases = {
        "trigger_current": ("trigger_current", "current_trigger", "trigger"),
        "exact_facility": ("exact_facility", "facility", "facility_verified"),
        "calibration_demand": ("calibration_demand", "demand", "calibration_need"),
        "technical_capability": ("technical_capability", "capability", "technical_fit"),
        "timing": ("timing", "buying_window", "timing_current"),
        "correct_person": ("correct_person", "person_verified", "decision_maker"),
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
        elif name == "correct_person":
            passed, reason, meta = _person_passes(value)
        elif name == "technical_capability":
            passed, reason, meta = _technical_capability_passes(value)
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
