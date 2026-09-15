"""Signal-Driven Lead Discovery & Business Causality Engine.

Implements the core discovery philosophy:
Identifies demand BEFORE an explicit RFQ is issued by tracking direct,
indirect, and second-order signals (CAPEX, plant expansion, QA hiring,
regulatory mandates, OEM quality standards).

Translates every signal into the mandatory 5-Question commercial framework.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from sqlalchemy.orm import Session

from models.company import Company
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent
from models.facility import Facility
from models.intent_signal import CompanyIntentSignal
from services.company_brain import record_intelligence_fact, record_timeline_event
from services.calibration_inference_engine import infer_calibration_need, estimate_instrument_population

logger = logging.getLogger(__name__)

# Direct and Indirect Signal Types
SIGNAL_TAXONOMY = {
    # Direct Signals (Explicit market demand)
    "tender_calibration": {
        "category": "direct",
        "name": "Calibration Tender / Public RFQ",
        "urgency": "immediate",
        "buying_window": "immediate",
        "price_sensitivity": "High",
        "default_icp_boost": 25,
    },
    "rfq_metrology": {
        "category": "direct",
        "name": "Private Metrology Scope RFQ",
        "urgency": "immediate",
        "buying_window": "immediate",
        "price_sensitivity": "Medium",
        "default_icp_boost": 30,
    },
    # Indirect First-Order Signals
    "plant_expansion": {
        "category": "indirect_first_order",
        "name": "Greenfield / Brownfield Plant Expansion",
        "urgency": "high",
        "buying_window": "30_days",
        "price_sensitivity": "Low",
        "default_icp_boost": 20,
    },
    "capex_announcement": {
        "category": "indirect_first_order",
        "name": "Major Machinery CAPEX / New Production Line",
        "urgency": "high",
        "buying_window": "60_days",
        "price_sensitivity": "Low",
        "default_icp_boost": 18,
    },
    "qa_hiring": {
        "category": "indirect_first_order",
        "name": "Quality / Metrology / QA Engineer Hiring",
        "urgency": "medium",
        "buying_window": "30_days",
        "price_sensitivity": "Medium",
        "default_icp_boost": 12,
    },
    "oem_supplier_mandate": {
        "category": "indirect_first_order",
        "name": "New OEM Tier-1 Supply Contract / Supplier Qualification",
        "urgency": "high",
        "buying_window": "immediate",
        "price_sensitivity": "Low",
        "default_icp_boost": 22,
    },
    "iso_iatf_audit": {
        "category": "indirect_first_order",
        "name": "Upcoming ISO 9001 / IATF 16949 / FDA Audit Preparation",
        "urgency": "immediate",
        "buying_window": "immediate",
        "price_sensitivity": "Low",
        "default_icp_boost": 24,
    },
    # Second-Order Signals (Derived systemic triggers)
    "regulatory_qco": {
        "category": "second_order",
        "name": "BIS QCO / Legal Metrology Mandatory Standardization",
        "urgency": "high",
        "buying_window": "30_days",
        "price_sensitivity": "Low",
        "default_icp_boost": 15,
    },
    "ev_battery_manufacturing": {
        "category": "second_order",
        "name": "Transition to EV / High-Voltage Battery Assembly",
        "urgency": "high",
        "buying_window": "60_days",
        "price_sensitivity": "Low",
        "default_icp_boost": 20,
    },
}


def reason_signal_causality(
    signal_type: str,
    raw_event_title: str,
    raw_event_description: str,
    company_name: str,
    industry: str = "Automotive",
    evidence_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Applies the mandatory 5-Question Causality Framework to any raw signal."""
    meta = SIGNAL_TAXONOMY.get(signal_type, {
        "category": "general_signal",
        "name": signal_type.replace("_", " ").title(),
        "urgency": "medium",
        "buying_window": "60_days",
        "price_sensitivity": "Medium",
        "default_icp_boost": 10,
    })

    # Question 1: What changed?
    what_changed = f"{meta['name']}: {raw_event_title}. {raw_event_description[:180]}"

    # Question 2: Which company/facility is affected?
    affected_entity = f"{company_name} ({industry})"

    # Question 3: How does it affect calibration requirements?
    if "expansion" in signal_type or "capex" in signal_type:
        calibration_impact = (
            "New production equipment and machine tools require baseline NABL master verification, "
            "on-site dimensional alignment (CMM/lasers), and process parameter calibration before commissioning."
        )
        likely_parameters = ["Dimensional", "Torque", "Pressure", "Thermal"]
    elif "qa_hiring" in signal_type:
        calibration_impact = (
            "Expansion of QA headcount indicates new quality control protocols, stricter tolerance enforcement, "
            "and inventory audit of overdue measuring equipment."
        )
        likely_parameters = ["Dimensional", "Torque", "Electrical"]
    elif "audit" in signal_type or "iso" in signal_type:
        calibration_impact = (
            "Audit readiness requires valid NABL certificates with documented measurement uncertainty budgets (ISO/IEC 17025:2017) "
            "for 100% of production-line measuring instruments."
        )
        likely_parameters = ["Dimensional", "Thermal", "Pressure", "Electrical"]
    elif "regulatory" in signal_type or "qco" in signal_type:
        calibration_impact = (
            "New statutory standards mandate traceable calibration for all commercial testing sensors and pressure gauges "
            "with Government Approved Test Centre (GATC) verification."
        )
        likely_parameters = ["Pressure", "Thermal", "Mass / Balance"]
    elif "ev" in signal_type or "battery" in signal_type:
        calibration_impact = (
            "EV manufacturing requires tight environmental chamber thermal mapping, high-voltage electrical safety calibration, "
            "and cell-welding temperature verification."
        )
        likely_parameters = ["Electrical", "Thermal", "Environmental", "Dimensional"]
    else:
        calibration_impact = (
            "Operational shift creates immediate requirement for ISO/IEC 17025 accredited calibration across primary production parameters."
        )
        likely_parameters = ["Dimensional", "Pressure", "Thermal"]

    # Question 4: How does it change buying behavior / price sensitivity?
    if meta["price_sensitivity"] == "Low":
        buying_behavior = (
            "High consequence of delay or audit failure makes buyer value fast turnaround and accredited technical competence "
            "over lowest-bid discounting. Premium acceptance potential is High."
        )
    else:
        buying_behavior = (
            "Competitive quoting environment. Buyer will prioritize consolidated annual pricing and predictable turnarounds."
        )

    # Question 5: What should Oorja do differently?
    if "audit" in signal_type or "iso" in signal_type:
        action_strategy = "Engage Head of Quality Assurance immediately with Audit-Readiness Checklist and NABL accreditation CMC scope."
        target_role = "Quality / Metrology Head"
    elif "expansion" in signal_type or "capex" in signal_type:
        action_strategy = "Pitch on-site multi-parameter commissioning calibration to Plant Operations Head & Maintenance Manager."
        target_role = "Plant Head / Maintenance Manager"
    elif "regulatory" in signal_type:
        action_strategy = "Send Regulatory Compliance Advisory explaining the specific QCO deadline to Quality and Corporate Legal/Purchase."
        target_role = "Quality Head & Purchase Manager"
    else:
        action_strategy = "Initiate multi-touch sequence highlighting accredited SLA and fast on-site turnaround."
        target_role = "Quality Manager"

    return {
        "signal_type": signal_type,
        "signal_category": meta["category"],
        "raw_event_title": raw_event_title,
        "evidence_url": evidence_url,
        "urgency": meta["urgency"],
        "buying_window": meta["buying_window"],
        "price_sensitivity": meta["price_sensitivity"],
        "icp_boost": meta["default_icp_boost"],
        "likely_parameters": likely_parameters,
        # 5-Question Framework
        "five_question_reasoning": {
            "q1_what_changed": what_changed,
            "q2_affected_entity": affected_entity,
            "q3_calibration_impact": calibration_impact,
            "q4_buying_behavior_change": buying_behavior,
            "q5_oorja_action_strategy": action_strategy,
        },
        "recommended_target_role": target_role,
    }


def ingest_discovered_signal_lead(
    db: Session,
    company_name: str,
    city: str,
    state: str,
    industry: str,
    signal_type: str,
    event_title: str,
    event_description: str,
    evidence_url: Optional[str] = None,
    source: str = "signal_discovery_engine",
    trigger_evidence: Optional[Dict[str, Any]] = None,
    facility_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingests or updates a company based on a verified business trigger signal."""
    # 1. Deduplicate or fetch company
    company = db.query(Company).filter(Company.name.ilike(company_name.strip())).first()
    is_new = False
    if not company:
        is_new = True
        company = Company(
            name=company_name.strip(),
            city=city,
            state=state,
            industry=industry,
            icp_score=75,
            lead_status="Discovered",
            buying_window="30_days",
            source=source,
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    # 2. Reason through 5-Question Framework
    causality = reason_signal_causality(
        signal_type=signal_type,
        raw_event_title=event_title,
        raw_event_description=event_description,
        company_name=company.name,
        industry=industry,
        evidence_url=evidence_url,
    )

    # 3. Update company score & buying window
    company.buying_window = causality["buying_window"]
    company.source = source
    company.icp_score = max(
        int(company.icp_score or 0),
        min(98, max(50, 75 + causality["icp_boost"])),
    )
    if evidence_url and not company.domain:
        company.domain = urlparse(evidence_url).netloc.casefold().removeprefix("www.") or None
    db.commit()

    # 4. Record fact in Company Brain
    record_intelligence_fact(
        db=db,
        company_id=company.id,
        category="business_signal",
        fact_key=f"signal_{signal_type}_{datetime.now().strftime('%Y%m%d')}",
        fact_value={
            "signal_type": signal_type,
            "event_title": event_title,
            "likely_parameters": causality["likely_parameters"],
            "five_question_reasoning": causality["five_question_reasoning"],
        },
        source=source,
        source_url=evidence_url,
        confidence=0.90,
        evidence_text=f"{event_title} - {event_description[:200]}",
    )

    # 5. Record Chronological Timeline Event
    record_timeline_event(
        db=db,
        company_id=company.id,
        event_type=f"signal_{signal_type}",
        title=f"Detected Signal: {event_title}",
        description=causality["five_question_reasoning"]["q3_calibration_impact"],
        impact_level="high",
        buying_window_impact=causality["buying_window"],
        source=source,
        source_ref=evidence_url,
    )

    structured_signal = None
    if trigger_evidence:
        structured_signal = (
            db.query(CompanyIntentSignal)
            .filter(
                CompanyIntentSignal.company_id == company.id,
                CompanyIntentSignal.signal_type == signal_type,
                CompanyIntentSignal.source_url == evidence_url,
            )
            .first()
        )
        if not structured_signal:
            structured_signal = CompanyIntentSignal(
                company_id=company.id,
                signal_type=signal_type,
                source_url=evidence_url,
            )
            db.add(structured_signal)
        structured_signal.weight_applied = float(company.icp_score or 0)
        structured_signal.source_snippet = str(
            trigger_evidence.get("source_snippet") or f"{event_title}. {event_description}"
        )[:2000]
        structured_signal.urgency_reason = str(trigger_evidence.get("urgency_reason") or "Current industrial event")
        structured_signal.opportunity_note = causality["five_question_reasoning"]["q3_calibration_impact"]
        utc_now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        structured_signal.detected_at = utc_now_naive
        structured_signal.expires_at = utc_now_naive + timedelta(days=180)
        structured_signal.is_active = 1

    structured_facility = None
    if facility_evidence and facility_evidence.get("facility_verified"):
        facility_name = str(facility_evidence.get("facility_name") or "").strip()
        if facility_name:
            structured_facility = (
                db.query(Facility)
                .filter(Facility.company_id == company.id, Facility.name == facility_name)
                .first()
            )
            if not structured_facility:
                structured_facility = Facility(company_id=company.id, name=facility_name)
                db.add(structured_facility)
            structured_facility.address = str(facility_evidence.get("facility_address") or "") or None
            structured_facility.city = str(facility_evidence.get("city") or city or "") or None
            structured_facility.state = str(facility_evidence.get("state") or state or "") or None
            structured_facility.industrial_estate = str(facility_evidence.get("industrial_cluster") or "") or None

    db.commit()

    return {
        "status": "lead_discovered" if is_new else "signal_attached",
        "company_id": company.id,
        "company_name": company.name,
        "icp_score": company.icp_score,
        "buying_window": company.buying_window,
        "causality": causality,
        "intent_signal_id": structured_signal.id if structured_signal else None,
        "facility_id": structured_facility.id if structured_facility else None,
    }


def _extract_company_name_from_title(title: str) -> str:
    from services.entity_truth_gate import extract_clean_company_name_from_title
    return extract_clean_company_name_from_title(title)


def _resolve_live_facility(company_name: str, evidence_text: str) -> Dict[str, Any]:
    from services.deep_facility_resolver import deep_facility_resolver
    from services.trigger_discovery_service import (
        TRIGGER_FACILITY_DIRECT,
        TRIGGER_FACILITY_STRONG,
        bind_trigger_to_facility,
        extract_trigger_facility_link,
    )

    extracted = extract_trigger_facility_link(evidence_text)
    known_city = str(extracted.get("facility_city_from_trigger") or "")
    resolved = deep_facility_resolver.resolve_facility(
        company_name=company_name,
        trigger_text=evidence_text,
        known_city=known_city or None,
    )
    if (
        resolved.get("facility_verified")
        and resolved.get("linkage_confidence") in {"DIRECT", "STRONG"}
        and resolved.get("facility_name")
    ):
        return resolved

    specificity = str(extracted.get("trigger_facility_specificity") or "")
    area = str(extracted.get("facility_area_from_trigger") or "")
    exact_name = str(extracted.get("facility_name_from_trigger") or "")
    meaningful_facility_words = [
        word
        for word in re.findall(r"[a-z0-9]+", exact_name.casefold())
        if len(word) > 2 and word not in {"new", "plant", "facility", "factory", "unit", "works"}
    ]
    if exact_name and not meaningful_facility_words:
        exact_name = ""
        if specificity == "EXACT_FACILITY":
            specificity = "CITY" if known_city else "COMPANY_ONLY"

    # A facility cannot be validated without an identified city or industrial corridor
    if not known_city and not area:
        return resolved

    facility_name = exact_name or (f"{company_name} Manufacturing Unit, {area}" if area else f"{company_name} {known_city} Facility")
    binding = bind_trigger_to_facility(
        evidence_text,
        target_facility=facility_name,
        target_city=known_city,
    )
    if binding.get("linkage") not in {TRIGGER_FACILITY_DIRECT, TRIGGER_FACILITY_STRONG}:
        return resolved
    return {
        "facility_name": facility_name,
        "facility_address": ", ".join(value for value in (area, known_city, "India") if value),
        "city": known_city,
        "state": "",
        "industrial_cluster": area or None,
        "linkage_confidence": "DIRECT" if binding.get("linkage") == TRIGGER_FACILITY_DIRECT else "STRONG",
        "linkage_evidence": binding.get("reason"),
        "facility_verified": True,
        "trigger_facility": facility_name,
        "target_facility": facility_name,
    }


def discover_new_calibration_opportunities(
    db: Session,
    geography: str = "PAN INDIA",
    industry_filter: Optional[str] = None,
    limit: int = 10,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Autonomous calibration demand discovery engine across Pan-India industrial corridors.
    
    Discovers candidate manufacturing accounts from direct and indirect triggers,
    applies second-order causal reasoning, identifies decision-maker personas,
    and returns ranked candidate accounts ready for review and Apollo enrichment.
    """
    # Pan-India Real Industrial Triggers Database
    PAN_INDIA_DISCOVERY_CATALOG = [
        {
            "company_name": "Bharat Forge Ltd",
            "city": "Pune",
            "state": "Maharashtra",
            "industry": "Automotive & Aerospace",
            "signal_type": "plant_expansion",
            "event_title": "₹450 Cr Heavy Machining & Aerospace Turbine Bay Commissioned",
            "event_description": "Commissioned 16 DMG MORI 5-axis CNC machines and Zeiss CMM measurement facility at Chakan Unit 2 for Boeing/Rolls-Royce aerospace turbine disk production.",
            "evidence_url": "https://www.bharatforge.com/investors/announcements/capex-2026",
            "source_classification": "OFFICIAL_COMPANY_ANNOUNCEMENT",
        },
        {
            "company_name": "Endurance Technologies Ltd",
            "city": "Aurangabad",
            "state": "Maharashtra",
            "industry": "Automotive Components",
            "signal_type": "capex_announcement",
            "event_title": "₹180 Cr High-Pressure Aluminum Die Casting Line Installation",
            "event_description": "Installed 6 Toshiba 1200T high-pressure die casting machines and automated torque assembly lines for EV transmission housing fabrication.",
            "evidence_url": "https://www.endurancegroup.com/press-releases/expansion-aurangabad",
            "source_classification": "INDUSTRY_PORTAL",
        },
        {
            "company_name": "Godrej Aerospace Precision Division",
            "city": "Mumbai",
            "state": "Maharashtra",
            "industry": "Aerospace & Defence",
            "signal_type": "regulatory_qco",
            "event_title": "AS9100 Rev D & BIS Mandatory Quality Control Order Mandate",
            "event_description": "Mandatory sub-micron dimensional tolerance audit and cryogenic sensor calibration for ISRO semi-cryogenic engine fabrication project.",
            "evidence_url": "https://www.godrej.com/godrej-aerospace/news/quality-mandate-2026",
            "source_classification": "REGULATORY_RADAR",
        },
        {
            "company_name": "Kalyani Technoforge Ltd",
            "city": "Pune",
            "state": "Maharashtra",
            "industry": "Precision Engineering",
            "signal_type": "qa_hiring",
            "event_title": "Senior Quality Assurance & Metrology Headcount Addition",
            "event_description": "Recruited 4 CMM Quality Engineers and Lead Metrologist for precision driveline components testing ahead of IATF 16949 audit.",
            "evidence_url": "https://www.naukri.com/job-listings-kalyani-technoforge-metrology-qa",
            "source_classification": "JOB_PORTAL_SIGNALS",
        },
        {
            "company_name": "Sundram Fasteners Ltd",
            "city": "Chennai",
            "state": "Tamil Nadu",
            "industry": "Automotive Fasteners",
            "signal_type": "oem_supplier_mandate",
            "event_title": "₹220 Cr European OEM Fastener Export Qualification",
            "event_description": "New Tier-1 export contract requiring 100% calibration traceability on digital torque masters, optical profile projectors, and tensile testing load cells.",
            "evidence_url": "https://www.sundram.com/press/europe-oem-supply-agreement",
            "source_classification": "EXPORT_PROMOTION_PORTAL",
        },
        {
            "company_name": "Tata Electronics Ltd",
            "city": "Hosur",
            "state": "Tamil Nadu",
            "industry": "Electronics & Precision Enclosures",
            "signal_type": "plant_expansion",
            "event_title": "Precision CNC Enclosure Facility Phase-2 Commissioning",
            "event_description": "Rapid ramp-up of 2,000+ precision CNC machining centers with daily dimensional touch-probe calibration requirements.",
            "evidence_url": "https://www.tataelectronics.com/news/hosur-phase2-expansion",
            "source_classification": "OFFICIAL_COMPANY_ANNOUNCEMENT",
        },
        {
            "company_name": "Dynamatic Technologies Ltd",
            "city": "Bengaluru",
            "state": "Karnataka",
            "industry": "Aerospace & Hydraulics",
            "signal_type": "iso_iatf_audit",
            "event_title": "Airbus A220 Door Assemblies Aerospace Metrology Audit",
            "event_description": "Mandatory annual calibration renewal for laser trackers, Faro arms, and multi-axis hydraulic pressure gauges.",
            "evidence_url": "https://www.dynamatics.com/investor-relations/aerospace-contracts",
            "source_classification": "INDUSTRY_PUBLICATIONS",
        },
        {
            "company_name": "Aarti Industries Ltd",
            "city": "Dahej",
            "state": "Gujarat",
            "industry": "Specialty Chemicals",
            "signal_type": "capex_announcement",
            "event_title": "₹600 Cr Nitration Plant Expansion & Flow Metering Upgrade",
            "event_description": "Commissioning 40+ high-pressure reactors with safety-critical differential pressure transmitters and thermal RTD sensors.",
            "evidence_url": "https://www.aarti-industries.com/investor/capex-update",
            "source_classification": "PUBLIC_FILING",
        },
        {
            "company_name": "Minda Corporation Ltd",
            "city": "Noida",
            "state": "Delhi NCR",
            "industry": "Automotive Electronics",
            "signal_type": "ev_battery_manufacturing",
            "event_title": "EV Battery Management System Assembly Line Launch",
            "event_description": "Setting up high-voltage electrical safety testing stations and environmental chamber calibration facilities.",
            "evidence_url": "https://www.sparkminda.com/news/ev-bms-line",
            "source_classification": "INDUSTRY_PORTAL",
        },
    ]

    # Filter by geography
    filtered = PAN_INDIA_DISCOVERY_CATALOG
    if geography and geography != "PAN INDIA" and geography != "All":
        filtered = [c for c in filtered if c["state"].lower() == geography.lower()]

    if industry_filter and industry_filter != "All":
        filtered = [c for c in filtered if industry_filter.lower() in c["industry"].lower()]

    # Phase 2 Adaptive Discovery Integration
    from services.discovery_query_planner import discovery_query_planner
    from services.discovery_query_memory import (
        discovery_query_memory,
        STATE_SUCCESS_PRODUCTIVE,
        STATE_SUCCESS_EXHAUSTED,
        STATE_PROVIDER_ERROR,
        STATE_RATE_LIMITED,
        STATE_TIMEOUT,
    )
    from services.opportunity_reasoner import (
        opportunity_reasoner,
        CLASSIFICATION_STRONG,
        CLASSIFICATION_INCOMPLETE,
        CLASSIFICATION_WEAK,
        CLASSIFICATION_UNAVAILABLE,
    )
    from services.adaptive_research_service import adaptive_research_service
    from services.research_provider import (
        ResearchProviderRouter,
        PROVIDER_BUDGET_EXHAUSTED,
        PROVIDER_QUOTA_EXHAUSTED,
        PROVIDER_ERROR,
    )

    router = ResearchProviderRouter()
    live_search_candidates = []
    search_res: Dict[str, Any] = {
        "provider": "none",
        "provider_status": "NOT_CALLED",
        "cache_hit": False,
        "results": [],
    }

    planned_query: Dict[str, Any] = {
        "query": "catalog_fallback",
        "page": 1,
        "sector": "Precision Manufacturing",
        "trigger": "plant_expansion",
        "geography": geography,
        "weight": 1.0,
        "rationale": "Default catalog mode",
    }
    execution_state = STATE_SUCCESS_PRODUCTIVE
    yield_score = 0.0
    exhaustion_score = 0.0
    score_components: Dict[str, Any] = {}

    if not use_cache:
        # 1. Stateful Adaptive Query Planning (Amendment 7)
        planned_query = discovery_query_planner.get_next_planned_query(
            db=db,
            preferred_sector=industry_filter if industry_filter and industry_filter != "All" else None,
            preferred_geo=geography if geography and geography != "PAN INDIA" and geography != "All" else None,
        )

        query_to_execute = planned_query["query"]
        page_to_execute = planned_query.get("page", 1)
        sector_to_execute = planned_query.get("sector", "Automotive & Auto Components")
        trigger_to_execute = planned_query.get("trigger", "plant_expansion")
        geo_to_execute = planned_query.get("geography", geography)

        try:
            search_res = router.search(
                query_to_execute,
                num_results=min(max(int(limit), 5), 10),
                db=db,
                use_cache=use_cache,
                page=page_to_execute,
            )

            p_status = search_res.get("provider_status")
            err_msg = str(search_res.get("error") or "")

            # 2. Check Execution States & Provider Errors (Amendment 4)
            if p_status in {PROVIDER_BUDGET_EXHAUSTED, PROVIDER_QUOTA_EXHAUSTED} or "429" in err_msg:
                execution_state = STATE_RATE_LIMITED
                discovery_query_memory.record_query_execution(
                    query=query_to_execute,
                    page=page_to_execute,
                    sector=sector_to_execute,
                    trigger=trigger_to_execute,
                    geography=geo_to_execute,
                    execution_state=execution_state,
                    metadata_json={"error": err_msg},
                    db=db,
                )
            elif p_status == PROVIDER_ERROR or (err_msg and "no organic results" not in err_msg.lower()):
                execution_state = (
                    STATE_TIMEOUT
                    if ("timed out" in err_msg.lower() or "timeout" in err_msg.lower())
                    else STATE_PROVIDER_ERROR
                )
                discovery_query_memory.record_query_execution(
                    query=query_to_execute,
                    page=page_to_execute,
                    sector=sector_to_execute,
                    trigger=trigger_to_execute,
                    geography=geo_to_execute,
                    execution_state=execution_state,
                    metadata_json={"error": err_msg},
                    db=db,
                )
            elif (
                search_res.get("provider") == "serper"
                and search_res.get("provider_status") in {"LIVE", "EMPTY"}
                and not search_res.get("cache_hit")
            ):
                raw_results = search_res.get("results", []) or []

                # 3. Cheap Filters Before LLM (Amendment 6)
                grouped_candidates, filter_telemetry = opportunity_reasoner.apply_cheap_filters(raw_results)

                strong_count = 0
                incomplete_count = 0
                weak_count = 0

                from services.trigger_discovery_service import evaluate_event_semantics, extract_event_date

                for candidate_group in grouped_candidates:
                    company_name = candidate_group.get("company_name", "")

                    # 4. Opportunity Reasoner (Amendment 1 & 3)
                    assessment = opportunity_reasoner.reason_opportunity(
                        candidate_group=candidate_group,
                        sector=sector_to_execute,
                        geography=geo_to_execute,
                    )

                    # 5. Targeted Research for Incomplete Leads (if promising)
                    if assessment.get("opportunity_classification") == CLASSIFICATION_INCOMPLETE:
                        incomplete_count += 1
                        research_res = adaptive_research_service.conduct_targeted_research(
                            candidate_group=candidate_group,
                            initial_assessment=assessment,
                            sector=sector_to_execute,
                            geography=geo_to_execute,
                            db=db,
                        )
                        assessment = research_res.get("final_assessment", assessment)

                    classification = assessment.get("opportunity_classification")
                    if classification == CLASSIFICATION_STRONG:
                        strong_count += 1
                    elif classification == CLASSIFICATION_INCOMPLETE:
                        pass
                    else:
                        weak_count += 1

                    # Deterministic Grounding & Verification
                    title = candidate_group["titles"][0] if candidate_group.get("titles") else ""
                    snippet = candidate_group["snippets"][0] if candidate_group.get("snippets") else ""
                    url = candidate_group["source_urls"][0] if candidate_group.get("source_urls") else ""
                    source_item = next((item for item in raw_results if str(item.get("url") or "") == url), {})
                    result_date = str((source_item.get("metadata") or {}).get("date") or "")
                    evidence_text = ". ".join(value for value in (title, snippet, result_date) if value)

                    semantics = evaluate_event_semantics(snippet, title=title)
                    recency = extract_event_date(
                        f"{snippet} {result_date}",
                        title=title,
                        now_dt=datetime.now(timezone.utc),
                        url=url,
                    )
                    facility = _resolve_live_facility(company_name, evidence_text)

                    trigger_valid = bool(
                        semantics.get("is_valid")
                        and recency.get("recency_tier") in {"CURRENT", "RECENT"}
                        and not recency.get("is_future_planned_milestone")
                    )
                    facility_verified = bool(
                        facility.get("facility_verified")
                        and facility.get("linkage_confidence") in {"DIRECT", "STRONG"}
                    )

                    opportunity_qualified = bool(
                        classification == CLASSIFICATION_STRONG
                        and trigger_valid
                        and facility_verified
                    )

                    live_search_candidates.append({
                        "company_name": company_name[:100],
                        "city": facility.get("city") or geo_to_execute,
                        "state": facility.get("state") or geo_to_execute,
                        "industry": sector_to_execute,
                        "signal_type": trigger_to_execute,
                        "event_title": title[:200],
                        "event_description": snippet[:500],
                        "evidence_url": url,
                        "source_classification": f"LIVE_SEARCH_{search_res.get('provider', 'WEB').upper()}",
                        "data_provenance": "LIVE_SEARCH_DISCOVERED",
                        "current_run_live": True,
                        "trigger_valid": trigger_valid,
                        "trigger_semantics": semantics,
                        "trigger_recency": recency,
                        "facility_verified": facility_verified,
                        "facility": facility.get("facility_name") or "",
                        "facility_evidence": facility,
                        "opportunity_qualified": opportunity_qualified,
                        "opportunity_classification": classification,
                        "opportunity_assessment": assessment,
                        "evidence_provenance": assessment.get("evidence_provenance", {}),
                    })

                # 6. Productivity and Exhaustion Calculation (Amendment 2)
                raw_count = len(raw_results)
                dup_count = filter_telemetry.get("duplicate_urls", 0)
                new_comp = len(grouped_candidates)
                inval_ent = filter_telemetry.get("invalid_entities_rejected", 0)

                yield_score, exhaustion_score, execution_state, score_components = (
                    discovery_query_memory.compute_productivity_and_exhaustion(
                        results_count=raw_count,
                        duplicate_count=dup_count,
                        new_companies=new_comp,
                        strong_opps=strong_count,
                        incomplete_opps=incomplete_count,
                        weak_opps=weak_count,
                        invalid_entities=inval_ent,
                    )
                )

                # Persist execution in PostgreSQL + 24h Redis cooldown for success (Amendment 5)
                discovery_query_memory.record_query_execution(
                    query=query_to_execute,
                    page=page_to_execute,
                    sector=sector_to_execute,
                    trigger=trigger_to_execute,
                    geography=geo_to_execute,
                    execution_state=execution_state,
                    results_count=raw_count,
                    unique_results=max(0, raw_count - dup_count),
                    new_companies=new_comp,
                    strong_opps=strong_count,
                    incomplete_opps=incomplete_count,
                    weak_opps=weak_count,
                    yield_score=yield_score,
                    exhaustion_score=exhaustion_score,
                    metadata_json=score_components,
                    db=db,
                )

                # Mark newly seen URLs in Redis
                fresh_urls = [r.get("url") for r in raw_results if r.get("url")]
                discovery_query_memory.mark_urls_seen(fresh_urls)

            else:
                # 0 organic results returned
                execution_state = STATE_SUCCESS_EXHAUSTED
                yield_score, exhaustion_score, execution_state, score_components = (
                    discovery_query_memory.compute_productivity_and_exhaustion(
                        results_count=0,
                        duplicate_count=0,
                        new_companies=0,
                        strong_opps=0,
                        incomplete_opps=0,
                        weak_opps=0,
                        invalid_entities=0,
                    )
                )
                discovery_query_memory.record_query_execution(
                    query=query_to_execute,
                    page=page_to_execute,
                    sector=sector_to_execute,
                    trigger=trigger_to_execute,
                    geography=geo_to_execute,
                    execution_state=execution_state,
                    results_count=0,
                    unique_results=0,
                    new_companies=0,
                    strong_opps=0,
                    incomplete_opps=0,
                    weak_opps=0,
                    yield_score=yield_score,
                    exhaustion_score=exhaustion_score,
                    metadata_json=score_components,
                    db=db,
                )
        except Exception as e:
            logger.warning("Live search discovery note: %s", e)

    # Production no-cache discovery must never persist pilot catalog rows as current work.
    candidate_pool = live_search_candidates
    if use_cache:
        candidate_pool += [dict(c, data_provenance="PILOT_CATALOG_CANDIDATE") for c in filtered]
    discovered_candidates = []
    for candidate in candidate_pool[:limit]:
        ingested = ingest_discovered_signal_lead(
            db=db,
            company_name=candidate["company_name"],
            city=candidate["city"],
            state=candidate["state"],
            industry=candidate["industry"],
            signal_type=candidate["signal_type"],
            event_title=candidate["event_title"],
            event_description=candidate["event_description"],
            evidence_url=candidate["evidence_url"],
            source=f"autonomous_discovery_{candidate['source_classification'].lower()}",
            trigger_evidence=(
                {
                    "source_snippet": f"{candidate['event_title']}. {candidate['event_description']}",
                    "urgency_reason": candidate.get("trigger_semantics", {}).get("description"),
                }
                if candidate.get("current_run_live") and candidate.get("trigger_valid")
                else None
            ),
            facility_evidence=(
                candidate.get("facility_evidence")
                if candidate.get("current_run_live") and candidate.get("facility_verified")
                else None
            ),
        )

        discovered_candidates.append({
            "company_id": ingested["company_id"],
            "company_name": candidate["company_name"],
            "city": candidate["city"],
            "state": candidate["state"],
            "industry": candidate["industry"],
            "icp_score": ingested["icp_score"],
            "buying_window": ingested["buying_window"],
            "signal_type": candidate["signal_type"],
            "event_title": candidate["event_title"],
            "source_classification": candidate["source_classification"],
            "evidence_url": candidate["evidence_url"],
            "data_provenance": candidate.get("data_provenance", "PILOT_CATALOG_CANDIDATE"),
            "current_run_live": bool(candidate.get("current_run_live")),
            "trigger_valid": bool(candidate.get("trigger_valid")),
            "trigger_semantics": candidate.get("trigger_semantics") or {},
            "trigger_recency": candidate.get("trigger_recency") or {},
            "facility_verified": bool(candidate.get("facility_verified")),
            "facility": candidate.get("facility") or (candidate.get("facility_evidence") or {}).get("facility_name") or "",
            "target_facility": candidate.get("facility") or (candidate.get("facility_evidence") or {}).get("facility_name") or "",
            "facility_evidence": candidate.get("facility_evidence") or {},
            "opportunity_qualified": bool(candidate.get("opportunity_qualified")),
            "opportunity_classification": candidate.get("opportunity_classification", "UNKNOWN"),
            "opportunity_assessment": candidate.get("opportunity_assessment") or {},
            "evidence_provenance": candidate.get("evidence_provenance") or {},
            "causality_chain": {
                "event": candidate["event_title"],
                "business_change": ingested["causality"]["five_question_reasoning"]["q1_what_changed"],
                "calibration_impact": ingested["causality"]["five_question_reasoning"]["q3_calibration_impact"],
                "likely_parameters": ingested["causality"]["likely_parameters"],
                "recommended_role": ingested["causality"]["recommended_target_role"],
                "action_strategy": ingested["causality"]["five_question_reasoning"]["q5_oorja_action_strategy"],
            },
        })

    # Sort candidates by ICP Score descending
    discovered_candidates.sort(key=lambda x: x["icp_score"], reverse=True)

    return {
        "status": "SUCCESS",
        "geography_scope": geography,
        "total_discovered": len(discovered_candidates),
        "source_status": {
            "search_router": search_res.get("provider_status"),
            "provider": search_res.get("provider"),
            "cache_hit": bool(search_res.get("cache_hit")),
            "current_run_live": bool(
                search_res.get("provider") == "serper"
                and search_res.get("provider_status") == "LIVE"
                and not search_res.get("cache_hit")
                and not use_cache
            ),
        },
        "candidates": discovered_candidates,
        "planned_query": planned_query,
        "execution_state": execution_state,
        "yield_score": yield_score,
        "exhaustion_score": exhaustion_score,
        "score_components": score_components,
    }


def generate_industrial_trigger_query(company_name: str) -> str:
    """Generate an industrial trigger query with negative financial and stock keywords.

    Ensures Serper research prioritizes capex, commissioning, plant expansions,
    machinery setup, and metrology rather than stock prices, brokerage ratings, and equity noise.
    """
    clean_name = company_name.strip()
    return (
        f'"{clean_name}" ("new plant" OR "manufacturing facility" OR "commissioning" OR '
        f'"commercial production" OR "capacity expansion" OR "new production line" OR '
        f'"new machinery" OR "new laboratory" OR "metrology" OR "capex commissioning" OR '
        f'"production ramp-up") -stock -share -"target price" -brokerage -"price target" -trading'
    )


def generate_secondary_capex_query(company_name: str) -> str:
    """Generate a targeted industrial capex and capacity milestone query for reference year 2026."""
    clean_name = re.sub(r"\b(Limited|Ltd\.?|Pvt\.?|Private|LLP|Inc\.?)\b", "", company_name, flags=re.IGNORECASE).strip()
    return (
        f'"{clean_name}" ("capacity expansion" OR "commissioning" OR "new line" OR "new plant" OR "capex") "2026" '
        f'-stock -share-price -market-cap -screener -dividend'
    )


def filter_negative_financial_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Strictly filter out stock/share price quote pages, aggregators, and non-event financial articles.

    Enforces deterministic hard rejects on URLs and strips generic ticker/market noise.
    Never falls back to returning rejected results.
    """
    from services.source_verification_pipeline import (
        classify_source_class,
        TRIGGER_HARD_REJECT_CLASSES,
    )
    from services.trigger_discovery_service import evaluate_event_semantics

    clean_results = []
    for r in results:
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("content", "") or r.get("snippet", "")

        # 1. Deterministic URL classification gate
        src_class = classify_source_class(url, title=title, snippet=snippet)
        if src_class in TRIGGER_HARD_REJECT_CLASSES:
            continue

        # 2. Check event semantics
        sem_eval = evaluate_event_semantics(snippet, title=title)
        if sem_eval["is_generic_financial"] and not sem_eval["is_verified"]:
            continue

        clean_results.append(r)

    return clean_results


def generate_adaptive_trigger_queries(
    company_name: str,
    sector: str = "",
    hub: str = "",
    official_domain: str = "",
) -> Dict[str, List[str]]:
    """Generate adaptive 3-pass search queries for industrial trigger recovery.

    PASS 1: High-yield company and core industrial event queries
    PASS 2: Facility, corridor, city, and sector-specific variants
    PASS 3: Official domain, BSE/NSE exchange filings, and corporate newsroom searches
    """
    clean_name = re.sub(r"\b(Limited|Ltd\.?|Pvt\.?|Private|LLP|Inc\.?)\b", "", company_name, flags=re.IGNORECASE).strip()
    full_name = company_name.strip()

    # Pass 1: High-yield event queries with uncluttered boolean terms
    pass1 = [
        f'"{clean_name}" "new plant" OR "plant expansion" OR "commissioning" -stock -share',
        f'"{clean_name}" "commercial production" OR "capacity expansion" -stock',
        f'"{clean_name}" "capex" "manufacturing" -brokerage -screener',
    ]

    # Pass 2: Specific facility / corridor / sector / equipment queries
    pass2 = []
    if hub:
        pass2.append(f'"{clean_name}" "{hub}" plant OR facility OR expansion -stock')
    if sector:
        pass2.append(f'"{clean_name}" "{sector}" manufacturing OR commissioning -stock')
    pass2.append(f'"{clean_name}" ("new unit" OR "assembly line" OR "inaugurated" OR "new line") manufacturing -stock')
    pass2.append(f'"{clean_name}" ("machinery" OR "equipment" OR "metrology lab" OR "quality lab") -stock')

    # Pass 3: Regulatory / exchange filings / official disclosures / press releases
    pass3 = [
        f'"{clean_name}" (site:bseindia.com OR site:nseindia.com) ("expansion" OR "commissioning" OR "commercial production" OR "capex")',
        f'"{clean_name}" ("press release" OR "investor presentation" OR "annual report") ("commissioning" OR "new facility" OR "plant expansion")',
    ]
    if official_domain:
        clean_dom = official_domain.lower().replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
        pass3.append(f'site:{clean_dom} ("commissioning" OR "expansion" OR "manufacturing" OR "new plant" OR "press release")')

    return {
        "pass_1": pass1,
        "pass_2": pass2,
        "pass_3": pass3,
    }


def expand_trigger_queries_with_gemini(
    company_name: str,
    sector: str = "",
    hub: str = "",
    max_queries: int = 3,
) -> List[str]:
    """Generate up to 3 targeted industrial search queries using Gemini if deterministic passes fail.

    Strictly capped at max_queries (3) per company. Skips cleanly if key unavailable.
    """
    import os
    try:
        from services.settings_manager import get_setting_value
    except ImportError:
        get_setting_value = lambda k, d=None: os.environ.get(k, d)
    gemini_key = str(os.environ.get("GEMINI_API_KEY", "") or get_setting_value("GEMINI_API_KEY", "")).strip()
    if not gemini_key or gemini_key.startswith("mock_") or gemini_key.startswith("YOUR_"):
        return []

    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            f"Generate {max_queries} concise Google search queries to find recent factory expansions, new plants, "
            f"commissioning, or capex for {company_name} (Sector: {sector}, Location: {hub}). "
            f"Focus on manufacturing milestones. Exclude stock prices. Return only the {max_queries} queries, one per line."
        )
        response = model.generate_content(prompt)
        lines = [line.strip().strip('"') for line in response.text.strip().split("\n") if line.strip()]
        valid_queries = [q for q in lines if len(q) > 10][:max_queries]
        return valid_queries
    except Exception as e:
        logger.debug(f"Gemini query expansion skipped: {e}")
        return []
