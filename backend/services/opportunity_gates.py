"""Evidence gates for production outreach readiness.

This module is deliberately side-effect free.  It evaluates an evidence
snapshot and never performs enrichment, DNS/MX checks, or sends mail.
"""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    reason: str


def _truth(value: Any) -> bool:
    return value is True or (isinstance(value, (int, float)) and value > 0) or (
        isinstance(value, str) and value.strip().lower() in {"true", "yes", "verified", "current", "active"}
    )


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


def _person_passes(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return _truth(value)
    # All three facts are mandatory. A title or a name alone is not proof.
    return all(_truth(value.get(k)) for k in ("employment_verified", "facility_verified", "duties_verified"))


def _email_passes(value: Any) -> bool:
    if isinstance(value, Mapping):
        status = str(value.get("status") or value.get("verification_status") or "").lower()
        if status in {"mx_only", "mx", "unverified", "risky", "unknown", "not_found"}:
            return False
        # A structural/legacy ``valid`` label is insufficient. Require the
        # explicit mailbox/contact assessment produced by the validator.
        trusted = _truth(value.get("mailbox_verified")) or _truth(value.get("trusted_verification"))
        assessment = str(value.get("contact_confidence") or "").upper()
        address = value.get("address") or value.get("email")
        return (status in {"verified", "email_verified", "deliverable"} and trusted and assessment in {"VERIFIED", "HIGH", "DIRECT"}
                and bool(str(address or "").strip()))
    return False


PROVENANCE_REAL = "REAL"
PROVENANCE_TEST = "TEST"
PROVENANCE_MOCK = "MOCK"
PROVENANCE_SYNTHETIC = "SYNTHETIC"


def evaluate_opportunity_gates(evidence: Mapping[str, Any], *, production: bool = True) -> dict[str, Any]:
    """Evaluate all seven gates against explicit evidence.

    ``production=False`` is intended for unit tests and synthetic fixtures.
    Synthetic/demo/mock/test evidence is always blocked from production qualification.
    """
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
    for name in GATE_NAMES:
        value = _evidence_value(evidence, name)
        passed = _person_passes(value) if name == "correct_person" else _email_passes(value) if name == "reachable_email" else _truth(value)
        results.append(GateResult(name, passed, "evidence present" if passed else "missing or insufficient evidence"))
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
        "gates": {g.name: {"passed": g.passed, "reason": g.reason} for g in results},
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
