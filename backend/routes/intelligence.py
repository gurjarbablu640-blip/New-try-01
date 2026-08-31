"""Salesoorja Intelligence API Routes.

Exposes unified endpoints for:
- Company Brain & Timeline
- Calibration Need Inference & Cost of Inaction
- Multi-Dimensional Lead Scoring & Explainability
- Regulatory Radar & 5-Question Impact Engine
- AI Lead Research Briefs & Role-Specific Campaigns
- Next Best Revenue Action & Deal Rescue
- Call Intelligence & Pre-Call Briefs
- Master Sales ML Dataset Pipeline
"""
from datetime import date
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models.company import Company
from services.company_brain import get_company_brain_dossier, record_intelligence_fact, record_timeline_event
from services.calibration_inference_engine import infer_calibration_need, estimate_instrument_population, calculate_cost_of_inaction
from services.lead_intelligence_scorer import evaluate_lead_intelligence
from services.regulatory_radar import scan_regulatory_radar_for_company, match_companies_for_regulation, seed_default_regulatory_intelligence
from services.lead_research_brief import generate_lead_research_brief, generate_role_specific_pitch
from services.revenue_autopilot import compute_next_best_revenue_action, generate_account_whitespace_map
from services.call_intelligence import generate_pre_call_brief, analyze_call_transcript
from services.sales_dataset_pipeline import extract_sales_ml_dataset

router = APIRouter(prefix="/api/intelligence", tags=["Sales Intelligence"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic Schemas
class FactCreateRequest(BaseModel):
    category: str
    fact_key: str
    fact_value: Optional[dict[str, Any]] = None
    source: str
    source_url: Optional[str] = None
    confidence: float = 0.85
    evidence_text: Optional[str] = None


class TimelineEventCreateRequest(BaseModel):
    event_type: str
    title: str
    event_date: Optional[date] = None
    description: Optional[str] = None
    impact_level: str = "medium"
    buying_window_impact: Optional[str] = None
    source: str = "manual"
    source_ref: Optional[str] = None


class RolePitchRequest(BaseModel):
    company_id: int
    target_role: str = "Quality / Metrology"
    contact_name: Optional[str] = None


class CallAnalysisRequest(BaseModel):
    transcript_text: str
    company_id: Optional[int] = None


# 1. Company Brain & Timeline
@router.get("/company-brain/{company_id}")
def company_brain_endpoint(company_id: int, db: Session = Depends(get_db)):
    dossier = get_company_brain_dossier(db, company_id)
    if "error" in dossier:
        raise HTTPException(404, dossier["error"])
    return dossier


@router.post("/company-brain/{company_id}/facts")
def add_company_fact(company_id: int, payload: FactCreateRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    fact = record_intelligence_fact(
        db=db,
        company_id=company_id,
        category=payload.category,
        fact_key=payload.fact_key,
        fact_value=payload.fact_value,
        source=payload.source,
        source_url=payload.source_url,
        confidence=payload.confidence,
        evidence_text=payload.evidence_text,
    )
    return {"status": "recorded", "fact_id": fact.id, "fact_key": fact.fact_key}


@router.post("/company-brain/{company_id}/timeline")
def add_timeline_event(company_id: int, payload: TimelineEventCreateRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    event = record_timeline_event(
        db=db,
        company_id=company_id,
        event_type=payload.event_type,
        title=payload.title,
        event_date=payload.event_date,
        description=payload.description,
        impact_level=payload.impact_level,
        buying_window_impact=payload.buying_window_impact,
        source=payload.source,
        source_ref=payload.source_ref,
    )
    return {"status": "recorded", "event_id": event.id, "event_type": event.event_type}


# 2. Calibration Need Inference & Cost of Inaction
@router.get("/calibration-inference/{company_id}")
def calibration_inference_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    inference = infer_calibration_need(company, db)
    population = estimate_instrument_population(company, db)
    cost = calculate_cost_of_inaction(company, db)
    return {
        "company_id": company_id,
        "inference": inference,
        "instrument_population_estimate": population,
        "cost_of_inaction": cost,
    }


# 3. Multi-Dimensional Lead Scoring & Explainability
@router.get("/lead-score/{company_id}")
def lead_score_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    scorecard = evaluate_lead_intelligence(company, db)
    return scorecard


# 4. Regulatory Radar
@router.get("/regulatory-radar")
def regulatory_radar_endpoint(db: Session = Depends(get_db)):
    seed_default_regulatory_intelligence(db)
    from models.company_brain import RegulatoryIntelligence
    notices = db.query(RegulatoryIntelligence).filter(RegulatoryIntelligence.active == True).all()
    results = []
    for n in notices:
        matched = match_companies_for_regulation(n.id, db)
        results.append({
            "id": n.id,
            "authority": n.authority,
            "regulation_code": n.regulation_code,
            "title": n.title,
            "summary": n.summary,
            "compliance_deadline": n.compliance_deadline.isoformat() if n.compliance_deadline else None,
            "commercial_impact_analysis": n.commercial_impact_analysis,
            "matched_companies_count": len(matched),
            "matched_companies": matched[:5],
        })
    return {"total_active_regulations": len(results), "regulations": results}


# 5. Lead Research Brief & Role-Specific Pitch
@router.get("/research-brief/{company_id}")
def research_brief_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    brief = generate_lead_research_brief(company, db)
    return brief


@router.post("/role-pitch")
@router.post("/campaign-pitch")
def role_pitch_endpoint(payload: RolePitchRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    pitch = generate_role_specific_pitch(company, payload.target_role, db, contact_name=payload.contact_name)
    return pitch


@router.post("/research-brief/{company_id}/pitch")
def research_brief_pitch_alias(company_id: int, payload: RolePitchRequest, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    pitch = generate_role_specific_pitch(company, payload.target_role, db, contact_name=payload.contact_name)
    return pitch


# 6. Next Best Revenue Action & Account White-Space
@router.get("/next-best-action/{company_id}")
def next_best_action_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    action = compute_next_best_revenue_action(company, db)
    return action


@router.get("/whitespace-map/{company_id}")
def whitespace_map_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    ws = generate_account_whitespace_map(company, db)
    return ws


# 7. Call Intelligence
@router.get("/call-brief/{company_id}")
def call_brief_endpoint(company_id: int, person_id: Optional[int] = None, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    brief = generate_pre_call_brief(company, db, person_id=person_id)
    return brief


@router.post("/analyze-call")
def analyze_call_endpoint(payload: CallAnalysisRequest, db: Session = Depends(get_db)):
    company = None
    if payload.company_id:
        company = db.query(Company).filter(Company.id == payload.company_id).first()
    analysis = analyze_call_transcript(payload.transcript_text, company=company)
    return analysis


# 8. Master Sales ML Dataset
@router.get("/ml-dataset")
def ml_dataset_endpoint(db: Session = Depends(get_db)):
    dataset = extract_sales_ml_dataset(db)
    return dataset


# 9. Master Revenue Loop Coordinator Endpoints
class EmailReplyLoopRequest(BaseModel):
    company_id: int
    reply_classification: str
    reply_body: str
    recipient_email: str
    sender_name: Optional[str] = None


class DealOutcomeLoopRequest(BaseModel):
    company_id: int
    outcome: str  # Won, Lost
    quotation_id: Optional[int] = None
    loss_reason: Optional[str] = None
    instrument_category: str = "General"


class CallRecordCreateRequest(BaseModel):
    company_id: int
    transcript_text: str
    person_id: Optional[int] = None
    salesperson_name: str = "Sales Rep"
    duration_seconds: int = 240
    call_channel: str = "Phone"
    recording_file_url: Optional[str] = None
    call_objective: str = "discovery"


@router.post("/revenue-loop/reply")
def reply_loop_endpoint(payload: EmailReplyLoopRequest, db: Session = Depends(get_db)):
    from services.revenue_loop_coordinator import process_incoming_email_reply_loop
    res = process_incoming_email_reply_loop(
        db=db,
        company_id=payload.company_id,
        reply_classification=payload.reply_classification,
        reply_body=payload.reply_body,
        recipient_email=payload.recipient_email,
        sender_name=payload.sender_name,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.post("/revenue-loop/deal-outcome")
def deal_outcome_loop_endpoint(payload: DealOutcomeLoopRequest, db: Session = Depends(get_db)):
    from services.revenue_loop_coordinator import process_deal_outcome_loop
    res = process_deal_outcome_loop(
        db=db,
        company_id=payload.company_id,
        outcome=payload.outcome,
        quotation_id=payload.quotation_id,
        loss_reason=payload.loss_reason,
        instrument_category=payload.instrument_category,
    )
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.get("/revenue-loop/audit/{company_id}")
def revenue_loop_audit_endpoint(company_id: int, db: Session = Depends(get_db)):
    from services.revenue_loop_coordinator import execute_full_revenue_loop_audit
    res = execute_full_revenue_loop_audit(db, company_id)
    if "error" in res:
        raise HTTPException(404, res["error"])
    return res


@router.post("/calls/record")
def record_call_endpoint(payload: CallRecordCreateRequest, db: Session = Depends(get_db)):
    from services.call_recorder_service import log_completed_call
    rec = log_completed_call(
        db=db,
        company_id=payload.company_id,
        transcript_text=payload.transcript_text,
        person_id=payload.person_id,
        salesperson_name=payload.salesperson_name,
        duration_seconds=payload.duration_seconds,
        call_channel=payload.call_channel,
        recording_file_url=payload.recording_file_url,
        call_objective=payload.call_objective,
    )
    return {
        "status": "call_recorded",
        "call_id": rec.id,
        "call_score": rec.call_score,
        "buying_signals_detected": rec.buying_signals_detected,
        "objections_detected": rec.objections_detected,
    }


@router.get("/calls/coaching-overview")
def coaching_overview_endpoint(salesperson_name: Optional[str] = None, db: Session = Depends(get_db)):
    from services.call_recorder_service import get_sales_coaching_overview
    overview = get_sales_coaching_overview(db, salesperson_name=salesperson_name)
    return overview


# 10. Signal Discovery & Second-Order Causality Engine
class SignalDiscoveryRequest(BaseModel):
    company_name: str
    city: str = "Pune"
    state: str = "Maharashtra"
    industry: str = "Automotive"
    signal_type: str = "plant_expansion"
    event_title: str
    event_description: str
    evidence_url: Optional[str] = None


class SignalReasoningRequest(BaseModel):
    signal_type: str
    raw_event_title: str
    raw_event_description: str
    company_name: str
    industry: str = "Automotive"
    evidence_url: Optional[str] = None


@router.post("/signals/discover")
def discover_signal_endpoint(payload: SignalDiscoveryRequest, db: Session = Depends(get_db)):
    from services.signal_discovery_engine import ingest_discovered_signal_lead
    res = ingest_discovered_signal_lead(
        db=db,
        company_name=payload.company_name,
        city=payload.city,
        state=payload.state,
        industry=payload.industry,
        signal_type=payload.signal_type,
        event_title=payload.event_title,
        event_description=payload.event_description,
        evidence_url=payload.evidence_url,
    )
    return res


class AutonomousDiscoveryRequest(BaseModel):
    geography: str = "PAN INDIA"
    industry_filter: Optional[str] = None
    limit: int = 10


@router.post("/signals/autonomous-discovery")
def autonomous_discovery_endpoint(payload: AutonomousDiscoveryRequest, db: Session = Depends(get_db)):
    """Executes autonomous calibration demand discovery across Pan-India configured sources."""
    from services.signal_discovery_engine import discover_new_calibration_opportunities
    res = discover_new_calibration_opportunities(
        db=db,
        geography=payload.geography,
        industry_filter=payload.industry_filter,
        limit=payload.limit,
    )
    return res


@router.post("/signals/reason")
def reason_signal_endpoint(payload: SignalReasoningRequest):
    from services.signal_discovery_engine import reason_signal_causality
    res = reason_signal_causality(
        signal_type=payload.signal_type,
        raw_event_title=payload.raw_event_title,
        raw_event_description=payload.raw_event_description,
        company_name=payload.company_name,
        industry=payload.industry,
        evidence_url=payload.evidence_url,
    )
    return res


# 11. 15-Day Non-Response Cadence Strategy
class CadenceEvaluationRequest(BaseModel):
    company_id: int
    days_since_outbound: int = 15
    non_response_threshold_days: int = 15
    last_contacted_role: str = "Purchase"
    last_contact_id: Optional[int] = None


@router.post("/cadence/evaluate-non-response")
def evaluate_cadence_endpoint(payload: CadenceEvaluationRequest, db: Session = Depends(get_db)):
    from services.cadence_orchestrator import evaluate_non_response_cadence
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    res = evaluate_non_response_cadence(
        company=company,
        db=db,
        days_since_outbound=payload.days_since_outbound,
        non_response_threshold_days=payload.non_response_threshold_days,
        last_contacted_role=payload.last_contacted_role,
        last_contact_id=payload.last_contact_id,
    )
    return res


# 12. Dynamic HTML Email Composition
class EmailComposeRequest(BaseModel):
    company_name: str
    contact_name: str = "Sir/Madam"
    target_role: str = "Quality"
    likely_parameters: Optional[list[str]] = None
    cta_text: str = "Review Our Accredited Scope"
    cta_url: str = "https://oorja.local/contact"


@router.post("/email/compose-html")
def compose_html_email_endpoint(payload: EmailComposeRequest):
    from services.email_template_engine import render_html_email
    res = render_html_email(
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        target_role=payload.target_role,
        likely_parameters=payload.likely_parameters,
        cta_text=payload.cta_text,
        cta_url=payload.cta_url,
    )
    return res


# 13. Apollo Live Pilot Safety Guard (Strict 5-6 contacts limit)
class ApolloPilotRequest(BaseModel):
    company_name: str
    target_titles: Optional[list[str]] = None
    max_contacts: int = 5


@router.post("/apollo/pilot-validation")
def apollo_pilot_validation_endpoint(payload: ApolloPilotRequest):
    from services.apollo_adapter import execute_apollo_pilot_validation
    res = execute_apollo_pilot_validation(
        company_name=payload.company_name,
        target_titles=payload.target_titles,
        max_contacts=payload.max_contacts,
    )
    return res


# 14. Reasoning Foundation & Evidential Belief State
class BeliefUpdateRequest(BaseModel):
    company_id: int
    epistemic_type: str = "INFERENCE"  # FACT, INFERENCE, HYPOTHESIS, UNKNOWN
    signal_type: str = "plant_expansion"
    title: str
    description: str
    source: str = "Public Release"
    source_url: Optional[str] = None
    source_reliability: float = 0.85
    causal_template_key: Optional[str] = None
    contradicting_statement: Optional[str] = None


@router.get("/reasoning/belief-state/{company_id}")
def get_company_belief_state_endpoint(company_id: int, db: Session = Depends(get_db)):
    from services.reasoning_engine import get_or_create_belief_state
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    state = get_or_create_belief_state(company, db)
    return {
        "company_id": company.id,
        "company_name": company.name,
        "beliefs": state.beliefs,
        "contradictions": state.contradictions,
        "causal_traces": state.causal_traces,
        "active_research_tasks": state.active_research_tasks,
        "overall_confidence": state.overall_confidence,
        "last_reasoned_at": state.last_reasoned_at,
    }


@router.post("/reasoning/update-belief")
def update_company_belief_endpoint(payload: BeliefUpdateRequest, db: Session = Depends(get_db)):
    from services.reasoning_engine import update_belief_with_evidence, EpistemicType
    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    
    ep_type = EpistemicType.INFERENCE
    try:
        ep_type = EpistemicType(payload.epistemic_type.upper())
    except Exception:
        pass

    res = update_belief_with_evidence(
        company=company,
        db=db,
        epistemic_type=ep_type,
        signal_type=payload.signal_type,
        title=payload.title,
        description=payload.description,
        source=payload.source,
        source_url=payload.source_url,
        source_reliability=payload.source_reliability,
        causal_template_key=payload.causal_template_key,
        contradicting_statement=payload.contradicting_statement,
    )
    return res


@router.get("/reasoning/decision-policy/{company_id}")
def get_decision_policy_endpoint(company_id: int, db: Session = Depends(get_db)):
    from services.reasoning_engine import execute_decision_policy
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    res = execute_decision_policy(company, db)
    return res


@router.get("/reasoning/cbr-similar-cases/{company_id}")
def get_cbr_similar_cases_endpoint(company_id: int, db: Session = Depends(get_db)):
    from services.reasoning_engine import find_similar_customer_cases
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")
    res = find_similar_customer_cases(company)
    return {"company_id": company.id, "similar_archetypes": res}


@router.get("/reasoning/causal-templates")
def get_causal_templates_endpoint():
    from services.reasoning_engine import CAUSAL_TEMPLATES
    return {"templates": list(CAUSAL_TEMPLATES.values())}


# ═════════════════════════════════════════════════════════════════════════
# Decision-Maker Discovery & Person Verification Pipeline
# ═════════════════════════════════════════════════════════════════════════

class DiscoverDecisionMakersRequest(BaseModel):
    signal_type: Optional[str] = None
    max_apollo_enrichments: int = Field(default=3, le=6)


@router.post("/decision-makers/discover/{company_id}")
def discover_decision_makers(
    company_id: int,
    request: DiscoverDecisionMakersRequest = DiscoverDecisionMakersRequest(),
    db: Session = Depends(get_db),
):
    """Run the full decision-maker discovery pipeline for a company.

    Steps: Persona → Search → Candidates → Verification → Apollo → Brief
    Each stage reports its own status (REAL/MOCK/BLOCKED/NOT_CONFIGURED).
    """
    from services.decision_maker_discovery import run_full_discovery_pipeline
    result = run_full_discovery_pipeline(
        company_id=company_id,
        db=db,
        signal_type=request.signal_type,
        max_apollo_enrichments=request.max_apollo_enrichments,
    )
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.get("/decision-makers/{company_id}")
def get_decision_makers(company_id: int, db: Session = Depends(get_db)):
    """Get all decision-maker candidates for a company with full status."""
    from services.decision_maker_discovery import get_company_decision_makers
    return get_company_decision_makers(company_id, db)


class VerifyDecisionMakerRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None


@router.post("/decision-makers/verify/{candidate_id}")
def verify_decision_maker(
    candidate_id: int,
    request: VerifyDecisionMakerRequest,
    db: Session = Depends(get_db),
):
    """Manually confirm or reject a decision-maker candidate."""
    from models.decision_maker_candidate import DecisionMakerCandidate
    candidate = db.query(DecisionMakerCandidate).filter(DecisionMakerCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    if request.approved:
        candidate.verification_status = "PERSON_PUBLICLY_VERIFIED"
        candidate.verification_notes = request.notes or "Manually verified by operator"
        from datetime import datetime
        candidate.verified_at = datetime.utcnow()
    else:
        candidate.verification_status = "PERSON_REJECTED"
        candidate.rejection_reason = request.rejection_reason or "manual_rejection"
        candidate.rejection_details = request.notes or "Manually rejected by operator"

    db.commit()
    return {
        "id": candidate.id,
        "verification_status": candidate.verification_status,
        "message": "Candidate verified" if request.approved else "Candidate rejected",
    }


@router.post("/decision-makers/enrich/{candidate_id}")
def enrich_decision_maker(candidate_id: int, db: Session = Depends(get_db)):
    """Trigger Apollo enrichment for a specific verified candidate."""
    from models.decision_maker_candidate import DecisionMakerCandidate
    from services.decision_maker_discovery import enrich_candidate_via_apollo

    candidate = db.query(DecisionMakerCandidate).filter(DecisionMakerCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(404, "Candidate not found")

    company = db.query(Company).filter(Company.id == candidate.company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    result = enrich_candidate_via_apollo(candidate, company.name, db)
    return result


@router.get("/decision-makers/research-brief/{company_id}")
def get_decision_maker_research_brief(company_id: int, db: Session = Depends(get_db)):
    """Get the full research brief with person discovery chain."""
    from models.decision_maker_candidate import DecisionMakerCandidate
    from services.decision_maker_discovery import build_research_brief_with_persons

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    candidates = (
        db.query(DecisionMakerCandidate)
        .filter(
            DecisionMakerCandidate.company_id == company_id,
            DecisionMakerCandidate.candidate_name.isnot(None),
        )
        .all()
    )

    brief = build_research_brief_with_persons(company, candidates)
    return brief
