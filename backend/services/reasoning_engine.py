"""Salesoorja Reasoning Foundation & Evidential Intelligence Engine.

Provides:
1. Epistemic Classification (FACT / INFERENCE / HYPOTHESIS / UNKNOWN)
2. Temporal Decay & Staleness Reasoner
3. Domain-Validated Causal Paths & Business Causality Graph
4. Persistent Belief State Management (calibration_need, buy_prob, premium_potential, etc.)
5. Contradiction Detection & Adaptive Uncertainty-Reduction Research Tasks
6. Case-Based Reasoning (CBR) against reference customer archetypes
7. Separation of Scoring from Decision Policy Engine
8. Inspectable Reasoning Traces (EVIDENCE -> INTERPRETATION -> CAUSAL PATH -> BELIEF -> DECISION)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import Enum
import math
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.customer_asset import CustomerAsset
from models.reasoning_engine import CompanyBeliefState, SignalEvidenceNode
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent
from services.company_brain import record_timeline_event

logger = logging.getLogger(__name__)


class EpistemicType(str, Enum):
    FACT = "FACT"  # Verified observation, official announcement, accredited lab record
    INFERENCE = "INFERENCE"  # Logical deduction based on equipment/process causality
    HYPOTHESIS = "HYPOTHESIS"  # Unverified commercial or behavioral assumption
    UNKNOWN = "UNKNOWN"  # Missing data requiring adaptive research


# Domain-Validated Causal Templates
CAUSAL_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "plant_expansion": {
        "template_key": "plant_expansion",
        "name": "Plant Expansion to Calibration Demand",
        "causal_chain": [
            "Facility Expansion Announcement",
            "Machinery & Production Tool Installation",
            "New Measuring Instruments Deployed",
            "Initial Line Alignment & Baseline Verification",
            "Mandatory NABL Calibration Schedule",
        ],
        "likely_parameters": ["Dimensional", "Torque", "Pressure", "Thermal"],
        "baseline_need_boost": 0.25,
        "default_staleness_days": 180,
        "decay_rate": 0.005,
    },
    "capex_machining": {
        "template_key": "capex_machining",
        "name": "Machining CAPEX to Precision Metrology",
        "causal_chain": [
            "Multi-Axis CNC / Toolroom CAPEX",
            "Sub-Micron Tolerances Mandated",
            "CMM, Micrometer & Bore Gauge Dependency",
            "Tight Uncertainty Budget Requirements",
            "ISO/IEC 17025 Certified Calibration Demand",
        ],
        "likely_parameters": ["Dimensional", "Torque"],
        "baseline_need_boost": 0.20,
        "default_staleness_days": 120,
        "decay_rate": 0.008,
    },
    "regulatory_qco": {
        "template_key": "regulatory_qco",
        "name": "Statutory Mandate to Traceability Need",
        "causal_chain": [
            "BIS QCO / Legal Metrology Gazette Notification",
            "Statutory Deadline Set for Testing Equipment",
            "Pressure Gauges & Commercial Sensors Require Re-verification",
            "Government Approved Test Centre (GATC) Calibration Urgency",
        ],
        "likely_parameters": ["Pressure", "Thermal", "Mass / Balance"],
        "baseline_need_boost": 0.30,
        "default_staleness_days": 365,
        "decay_rate": 0.002,
    },
    "qa_headcount": {
        "template_key": "qa_headcount",
        "name": "QA Team Expansion to Tool Audit",
        "causal_chain": [
            "Quality Assurance / Metrology Engineer Hiring",
            "Stricter Quality Control Protocols Enacted",
            "Internal Measuring Equipment Audit",
            "Overdue & Drifted Instrument Calibration Requirement",
        ],
        "likely_parameters": ["Dimensional", "Torque", "Electrical"],
        "baseline_need_boost": 0.15,
        "default_staleness_days": 90,
        "decay_rate": 0.012,
    },
    "ev_battery": {
        "template_key": "ev_battery",
        "name": "EV Transition to Multi-Parameter Compliance",
        "causal_chain": [
            "EV Battery & Traction Motor Line Setup",
            "Thermal Runway & High-Voltage Testing Mandated",
            "Environmental Chamber & Insulation Resistance Testing",
            "Dual-Parameter (Thermal + Electrical) Calibration Need",
        ],
        "likely_parameters": ["Electrical", "Thermal", "Environmental", "Dimensional"],
        "baseline_need_boost": 0.25,
        "default_staleness_days": 180,
        "decay_rate": 0.005,
    },
}

# Reference Archetypes for Case-Based Reasoning (CBR)
REFERENCE_CUSTOMER_ARCHETYPES = [
    {
        "archetype_id": "auto_tier1_chakan",
        "name": "Tier-1 Automotive Transmission & Chassis Manufacturer (Pune)",
        "industry": "Automotive",
        "typical_parameters": ["Dimensional", "Torque", "Pressure"],
        "typical_deal_size_inr": 250000.0,
        "key_buying_factor": "Turnaround speed and NABL CMC scope for CMM & torque transducers",
        "winning_pitch_role": "Quality Head & Metrology Manager",
        "observed_conversion_rate": 0.68,
    },
    {
        "archetype_id": "heavy_eng_fabrication",
        "name": "Heavy Engineering & Pressure Vessel Fabricator (Gujarat/Hazira)",
        "industry": "Heavy Engineering",
        "typical_parameters": ["Pressure", "Thermal", "Dimensional"],
        "typical_deal_size_inr": 350000.0,
        "key_buying_factor": "On-site hydrostatic pressure gauge and furnace thermal profiling",
        "winning_pitch_role": "Plant Operations Head & Maintenance",
        "observed_conversion_rate": 0.55,
    },
    {
        "archetype_id": "pharma_sterile_formulation",
        "name": "Pharma Sterile Injectables & Formulation Unit (Dahej/Baddi)",
        "industry": "Pharmaceuticals",
        "typical_parameters": ["Thermal", "Humidity / Environmental", "Pressure"],
        "typical_deal_size_inr": 420000.0,
        "key_buying_factor": "FDA/WHO audit readiness and temperature mapping data integrity",
        "winning_pitch_role": "VP Quality Assurance & Regulatory Compliance",
        "observed_conversion_rate": 0.72,
    },
]


def calculate_temporal_decay(
    initial_confidence: float,
    event_time: Optional[datetime],
    detection_time: datetime,
    staleness_days: int = 90,
    daily_decay_rate: float = 0.01,
) -> Dict[str, Any]:
    """Calculates temporal decay of evidence confidence over time."""
    ref_time = event_time or detection_time
    now = datetime.utcnow()
    days_elapsed = max(0, (now - ref_time).days)

    # Exponential decay formula: C(t) = C_0 * exp(-lambda * t)
    decay_factor = math.exp(-daily_decay_rate * days_elapsed)
    effective_confidence = max(0.20, round(initial_confidence * decay_factor, 3))

    is_stale = days_elapsed >= staleness_days
    temporal_status = "stale" if is_stale else ("decaying" if days_elapsed > 30 else "active")

    return {
        "initial_confidence": initial_confidence,
        "effective_confidence": effective_confidence,
        "days_elapsed": days_elapsed,
        "staleness_threshold_days": staleness_days,
        "temporal_status": temporal_status,
        "is_stale": is_stale,
    }


def get_or_create_belief_state(company: Company, db: Session) -> CompanyBeliefState:
    """Retrieves or initializes the persistent belief state for an account."""
    state = db.query(CompanyBeliefState).filter(CompanyBeliefState.company_id == company.id).first()
    if not state:
        # Base initial belief prior
        industry_archetype = (company.industry or "Automotive").lower()
        is_auto = "auto" in industry_archetype
        
        initial_beliefs = {
            "calibration_need": {
                "value": 0.70 if is_auto else 0.55,
                "confidence": 0.60,
                "epistemic_type": EpistemicType.INFERENCE.value,
                "supporting_evidence": [f"Industry standard requirement for {company.industry or 'Manufacturing'}"],
                "contradicting_evidence": [],
                "last_updated": datetime.utcnow().isoformat(),
                "update_reason": "Baseline industry prior initialization",
            },
            "buy_probability": {
                "value": float(company.icp_score or 60) / 100.0,
                "confidence": 0.55,
                "epistemic_type": EpistemicType.INFERENCE.value,
                "supporting_evidence": ["Initial CRM qualification"],
                "contradicting_evidence": [],
                "last_updated": datetime.utcnow().isoformat(),
                "update_reason": "Initial CRM ICP score baseline",
            },
            "buying_window": {
                "value": company.buying_window or "30_days",
                "confidence": 0.65,
                "epistemic_type": EpistemicType.HYPOTHESIS.value,
                "supporting_evidence": ["Default qualification window"],
                "contradicting_evidence": [],
                "last_updated": datetime.utcnow().isoformat(),
                "update_reason": "Default hypothesis",
            },
            "price_sensitivity": {
                "value": "Medium",
                "confidence": 0.50,
                "epistemic_type": EpistemicType.HYPOTHESIS.value,
                "supporting_evidence": ["Standard manufacturing profile"],
                "contradicting_evidence": [],
                "last_updated": datetime.utcnow().isoformat(),
                "update_reason": "Market baseline",
            },
            "premium_potential": {
                "value": "High" if is_auto else "Medium",
                "confidence": 0.55,
                "epistemic_type": EpistemicType.HYPOTHESIS.value,
                "supporting_evidence": ["High consequence industry"],
                "contradicting_evidence": [],
                "last_updated": datetime.utcnow().isoformat(),
                "update_reason": "Criticality hypothesis",
            },
            "opportunity_value_inr": {
                "value": 150000.0 if is_auto else 75000.0,
                "confidence": 0.60,
                "epistemic_type": EpistemicType.INFERENCE.value,
                "supporting_evidence": ["4-tier instrument population estimation model"],
                "contradicting_evidence": [],
                "last_updated": datetime.utcnow().isoformat(),
                "update_reason": "Headcount & process estimation",
            },
        }

        state = CompanyBeliefState(
            company_id=company.id,
            beliefs=initial_beliefs,
            contradictions=[],
            causal_traces=[],
            active_research_tasks=[],
            overall_confidence=0.58,
            last_reasoned_at=datetime.utcnow(),
        )
        db.add(state)
        db.commit()
        db.refresh(state)
        
    return state


def update_belief_with_evidence(
    company: Company,
    db: Session,
    epistemic_type: EpistemicType,
    signal_type: str,
    title: str,
    description: str,
    source: str,
    source_url: Optional[str] = None,
    source_reliability: float = 0.85,
    event_time: Optional[datetime] = None,
    causal_template_key: Optional[str] = None,
    contradicting_statement: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates company belief state with new evidence using temporal decay and causal templates."""
    state = get_or_create_belief_state(company, db)
    
    # 1. Temporal Decay Computation
    tpl = CAUSAL_TEMPLATES.get(causal_template_key or signal_type, {})
    staleness_days = tpl.get("default_staleness_days", 90)
    decay_rate = tpl.get("decay_rate", 0.01)
    
    temporal = calculate_temporal_decay(
        initial_confidence=source_reliability,
        event_time=event_time,
        detection_time=datetime.utcnow(),
        staleness_days=staleness_days,
        daily_decay_rate=decay_rate,
    )
    
    # 2. Persist Evidence Node
    node = SignalEvidenceNode(
        company_id=company.id,
        epistemic_type=epistemic_type.value,
        signal_type=signal_type,
        title=title,
        description=description,
        source=source,
        source_url=source_url,
        source_reliability=source_reliability,
        event_time=event_time or datetime.utcnow(),
        activation_window=tpl.get("activation_window", "30_days"),
        staleness_threshold_days=staleness_days,
        decay_rate=decay_rate,
        current_effective_confidence=temporal["effective_confidence"],
        causal_template_key=causal_template_key or signal_type,
        is_contradicted=bool(contradicting_statement),
        evidence_metadata={"temporal": temporal},
    )
    db.add(node)
    db.commit()

    # 3. Handle Contradictions
    current_contradictions = list(state.contradictions or [])
    active_research_tasks = list(state.active_research_tasks or [])
    
    if contradicting_statement:
        contra_entry = {
            "contradiction_id": f"contra_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "signal_type": signal_type,
            "evidence_a": f"{title} ({source}) - Reliability {source_reliability}",
            "evidence_b": contradicting_statement,
            "detected_at": datetime.utcnow().isoformat(),
            "status": "unresolved",
            "resolution_guidance": "Reduce confidence. Conduct adaptive research before initiating commercial action.",
        }
        current_contradictions.append(contra_entry)
        
        # Spawn Adaptive Research Task
        research_task = {
            "task_id": f"task_res_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "priority": "High",
            "objective": f"Resolve contradiction regarding {signal_type} for {company.name}",
            "question_to_answer": f"Verify whether '{title}' or '{contradicting_statement}' reflects the actual ground reality.",
            "recommended_sources": ["Company Website / Filings", "LinkedIn Metrology Engineers", "Phone Discovery Check"],
            "created_at": datetime.utcnow().isoformat(),
        }
        active_research_tasks.append(research_task)

    # 4. Evidential Belief Update
    beliefs = dict(state.beliefs or {})
    weight = temporal["effective_confidence"] * (0.5 if contradicting_statement else 1.0)
    
    # Calibration Need Update
    cur_need = beliefs.get("calibration_need", {})
    boost = tpl.get("baseline_need_boost", 0.15) * weight
    new_need_val = min(0.98, max(0.30, float(cur_need.get("value", 0.60)) + boost))
    new_need_conf = min(0.95, max(0.40, float(cur_need.get("confidence", 0.60)) * 0.7 + weight * 0.3))
    
    sup = list(cur_need.get("supporting_evidence", []))
    contra = list(cur_need.get("contradicting_evidence", []))
    if contradicting_statement:
        contra.append(contradicting_statement)
    else:
        sup.append(f"[{epistemic_type.value}] {title} via {source} (eff_conf: {temporal['effective_confidence']:.2f})")
        
    beliefs["calibration_need"] = {
        "value": round(new_need_val, 2),
        "confidence": round(new_need_conf, 2),
        "epistemic_type": epistemic_type.value if epistemic_type == EpistemicType.FACT else EpistemicType.INFERENCE.value,
        "supporting_evidence": sup[-5:],
        "contradicting_evidence": contra[-5:],
        "last_updated": datetime.utcnow().isoformat(),
        "update_reason": f"Updated by {signal_type} ({epistemic_type.value})",
    }

    # Buy Probability Update
    cur_buy = beliefs.get("buy_probability", {})
    new_buy_val = min(0.95, max(0.30, float(cur_buy.get("value", 0.55)) + boost * 0.8))
    beliefs["buy_probability"] = {
        "value": round(new_buy_val, 2),
        "confidence": round(new_need_conf * 0.9, 2),
        "epistemic_type": EpistemicType.INFERENCE.value,
        "supporting_evidence": sup[-5:],
        "contradicting_evidence": contra[-5:],
        "last_updated": datetime.utcnow().isoformat(),
        "update_reason": f"Derived from calibration need shift ({new_need_val:.2f})",
    }

    # 5. Build Inspectable Causal Trace
    causal_chain = tpl.get("causal_chain", [title, "Calibration Demand"])
    trace_entry = {
        "trace_id": f"trace_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "evidence_title": title,
        "epistemic_type": epistemic_type.value,
        "source": source,
        "effective_confidence": temporal["effective_confidence"],
        "temporal_status": temporal["temporal_status"],
        "causal_path": " ➔ ".join(causal_chain),
        "resulting_belief_shifts": {
            "calibration_need": round(new_need_val, 2),
            "buy_probability": round(new_buy_val, 2),
            "overall_confidence": round(new_need_conf, 2),
        },
        "has_contradiction": bool(contradicting_statement),
        "timestamp": datetime.utcnow().isoformat(),
    }
    
    traces = list(state.causal_traces or [])
    traces.append(trace_entry)
    
    # Save back to State
    state.beliefs = beliefs
    state.contradictions = current_contradictions
    state.active_research_tasks = active_research_tasks
    state.causal_traces = traces[-10:]
    state.overall_confidence = round(new_need_conf, 2)
    state.last_reasoned_at = datetime.utcnow()
    db.commit()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "node_id": node.id,
        "epistemic_type": epistemic_type.value,
        "temporal": temporal,
        "contradiction_detected": bool(contradicting_statement),
        "belief_state": beliefs,
        "reasoning_trace": trace_entry,
    }


def execute_decision_policy(company: Company, db: Session) -> Dict[str, Any]:
    """Applies rigorous decision policies separating Scoring from Action Selection."""
    state = get_or_create_belief_state(company, db)
    beliefs = state.beliefs or {}
    contradictions = state.contradictions or []
    
    need_val = float(beliefs.get("calibration_need", {}).get("value", 0.6))
    buy_val = float(beliefs.get("buy_probability", {}).get("value", 0.55))
    confidence = float(state.overall_confidence or 0.5)
    opp_val = float(beliefs.get("opportunity_value_inr", {}).get("value", 100000.0))
    buying_window = beliefs.get("buying_window", {}).get("value", "30_days")

    # Decision Constraint 1: Unresolved Contradictions -> Research Priority
    if len(contradictions) > 0:
        return {
            "decision": "ADAPTIVE_RESEARCH",
            "channel": "Internal Research / Non-Invasive Intelligence",
            "target_role": "Research Analyst",
            "policy_rule_fired": "POLICY_CONTRADICTION_SAFETY_GUARD",
            "reasoning": (
                f"Account has {len(contradictions)} active evidential contradiction(s). "
                f"Aggressive outreach suppressed to protect brand authority. Resolve ground reality first."
            ),
            "research_tasks": state.active_research_tasks,
            "overall_confidence": confidence,
        }

    # Decision Constraint 2: Low Confidence (< 0.50) -> Passive Enrichment
    if confidence < 0.50:
        return {
            "decision": "DATA_ENRICHMENT",
            "channel": "Apollo / LinkedIn Background Verification",
            "target_role": "Quality / Procurement",
            "policy_rule_fired": "POLICY_UNCERTAINTY_THRESHOLD",
            "reasoning": (
                f"Overall belief confidence ({confidence:.2f}) is below operational action threshold (0.50). "
                f"Perform stakeholder and facility verification before drafting outbound pitch."
            ),
            "overall_confidence": confidence,
        }

    # Decision Constraint 3: High Value (>= ₹1,50,000) & Immediate Window -> Direct Voice Calling
    if opp_val >= 150000.0 and (buying_window == "immediate" or need_val >= 0.80):
        return {
            "decision": "PRIORITY_PHONE_CALL",
            "channel": "Phone / Direct Voice",
            "target_role": "Head of Quality Assurance / Metrology",
            "policy_rule_fired": "POLICY_HIGH_VALUE_COMMISSIONING_ESCALATION",
            "reasoning": (
                f"High predicted opportunity (₹{opp_val:,.2f}) with immediate calibration demand ({need_val:.2f}). "
                f"Direct calling required with 30-second on-site turnaround script."
            ),
            "recommended_objective": "Qualify calibration scope & schedule on-site plant audit",
            "overall_confidence": confidence,
        }

    # Decision Constraint 4: Standard Qualified Lead -> Role-Specific HTML Email
    if buy_val >= 0.60:
        return {
            "decision": "ROLE_SPECIFIC_EMAIL",
            "channel": "NABL Accredited HTML Email",
            "target_role": "Head of Quality & Purchase Manager",
            "policy_rule_fired": "POLICY_QUALIFIED_OUTREACH",
            "reasoning": (
                f"Strong calibration belief ({need_val:.2f}) and confirmed commercial fit ({buy_val:.2f}). "
                f"Dispatch dual-sequence: Audit Readiness to Quality, Rate Contract to Purchase."
            ),
            "overall_confidence": confidence,
        }

    # Decision Constraint 5: Default -> 30-Day Nurture
    return {
        "decision": "NURTURE_CADENCE",
        "channel": "Monthly Metrology Standards Advisory",
        "target_role": "Quality Department",
        "policy_rule_fired": "POLICY_PASSIVE_MONITORING",
        "reasoning": "Baseline profile without urgent trigger. Maintain brand presence with regulatory updates.",
        "overall_confidence": confidence,
    }


def find_similar_customer_cases(company: Company) -> List[Dict[str, Any]]:
    """Case-Based Reasoning (CBR) matching against reference customer archetypes."""
    target_ind = (company.industry or "").lower()
    results = []
    
    for arch in REFERENCE_CUSTOMER_ARCHETYPES:
        score = 0.50  # Base similarity
        arch_ind = arch["industry"].lower()
        if arch_ind in target_ind or target_ind in arch_ind:
            score += 0.35
        if company.city and "pune" in company.city.lower() and "pune" in arch["name"].lower():
            score += 0.10
        if company.city and "dahej" in company.city.lower() and "dahej" in arch["name"].lower():
            score += 0.10
            
        results.append({
            "archetype_id": arch["archetype_id"],
            "archetype_name": arch["name"],
            "similarity_score": min(0.95, round(score, 2)),
            "industry": arch["industry"],
            "typical_parameters": arch["typical_parameters"],
            "expected_deal_size_inr": arch["typical_deal_size_inr"],
            "winning_pitch_role": arch["winning_pitch_role"],
            "key_buying_factor": arch["key_buying_factor"],
            "historical_conversion_rate": arch["observed_conversion_rate"],
        })
        
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results
