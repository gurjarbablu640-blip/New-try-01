"""Tool-based orchestration for the Oorja Sales Assistant (Ask Oorja).

Provides typed, deterministic tool execution for structured sales facts,
integrated with RAG retrieval for unstructured technical knowledge.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from models.company import Company
from models.customer_asset import CustomerAsset
from models.facility import Facility
from models.person import Person
from models.pipeline import PipelineStage
from models.sales_os import AIFeedback, Opportunity, Quotation, SalesTask
from services.calibration_intelligence import (
    calculate_asset_due_status,
    calculate_company_asset_calibration_summary,
    match_nabl_service_fit,
)
from services.nextBestAction import get_next_best_action


def search_companies(db: Session, query: str = "", limit: int = 20) -> dict[str, Any]:
    """Search CRM companies by name, city, industry, or status."""
    q = (query or "").strip()
    base = db.query(Company)
    if q:
        pattern = f"%{q}%"
        base = base.filter(or_(Company.name.ilike(pattern), Company.city.ilike(pattern), Company.industry.ilike(pattern)))
    rows = (
        base.order_by(Company.icp_score.desc().nullslast(), Company.id.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "tool": "search_companies",
        "total": len(rows),
        "results": [
            {
                "id": row.id,
                "name": row.name,
                "industry": row.industry,
                "city": row.city,
                "state": row.state,
                "lead_status": row.lead_status,
                "qualification_status": row.qualification_status,
                "icp_score": row.icp_score or 0,
                "buying_window": row.buying_window,
            }
            for row in rows
        ],
    }


def search_contacts(db: Session, query: str = "", limit: int = 20) -> dict[str, Any]:
    """Search CRM contacts by name, designation, department or email."""
    q = (query or "").strip()
    base = db.query(Person, Company).join(Company, Company.id == Person.company_id)
    if q:
        pattern = f"%{q}%"
        base = base.filter(
            or_(
                Person.full_name.ilike(pattern),
                Person.designation.ilike(pattern),
                Person.department.ilike(pattern),
                Person.email.ilike(pattern),
            )
        )
    rows = (
        base.order_by(Person.is_decision_maker.desc(), Person.id.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "tool": "search_contacts",
        "total": len(rows),
        "results": [
            {
                "id": person.id,
                "name": person.full_name,
                "designation": person.designation,
                "department": person.department,
                "email": person.email,
                "phone": person.phone,
                "company_id": company.id,
                "company": company.name,
                "decision_maker": person.is_decision_maker,
            }
            for person, company in rows
        ],
    }


def get_calibration_due_tool(db: Session, days: int = 60, limit: int = 50) -> dict[str, Any]:
    """Get instruments due for calibration within N days across all customers."""
    today = date.today()
    target_date = today + timedelta(days=days)
    assets = (
        db.query(CustomerAsset, Company)
        .join(Company, Company.id == CustomerAsset.company_id)
        .filter(
            CustomerAsset.status == "Active",
            CustomerAsset.calibration_due_date.isnot(None),
            CustomerAsset.calibration_due_date <= target_date,
        )
        .order_by(CustomerAsset.calibration_due_date.asc())
        .limit(limit)
        .all()
    )

    results = []
    for asset, comp in assets:
        status_info = calculate_asset_due_status(asset.calibration_due_date, reference_date=today)
        nabl_fit = match_nabl_service_fit(asset.instrument_name, asset.parameter, asset.range_value)
        results.append({
            "asset_id": asset.id,
            "instrument_name": asset.instrument_name,
            "company_id": comp.id,
            "company_name": comp.name,
            "facility_id": asset.facility_id,
            "parameter": asset.parameter,
            "calibration_due_date": asset.calibration_due_date.isoformat(),
            "due_status": status_info["due_status"],
            "days_until_due": status_info["days_until_due"],
            "urgency_level": status_info["urgency_level"],
            "nabl_fit": nabl_fit["fit_status"],
            "discipline": nabl_fit["discipline"],
        })

    return {
        "tool": "get_calibration_due",
        "filter_days": days,
        "total": len(results),
        "results": results,
    }


def get_priority_leads_tool(db: Session, limit: int = 20) -> dict[str, Any]:
    """Identify which companies to contact today based on buying windows and urgency."""
    today = date.today()
    # Find companies with active buying window or overdue/30-day calibrations
    companies = (
        db.query(Company)
        .filter(
            or_(
                Company.buying_window.in_(["next_30_days", "next_60_days"]),
                Company.lead_status.in_(["New", "Contacted", "Replied"]),
                Company.icp_score >= 60,
            )
        )
        .order_by(Company.icp_score.desc().nullslast(), Company.id.desc())
        .limit(limit)
        .all()
    )

    results = []
    for c in companies:
        calib_sum = calculate_company_asset_calibration_summary(c.id, db, reference_date=today)
        person = db.query(Person).filter(Person.company_id == c.id).first()
        results.append({
            "company_id": c.id,
            "company_name": c.name,
            "city": c.city,
            "state": c.state,
            "industry": c.industry,
            "lead_status": c.lead_status,
            "icp_score": c.icp_score,
            "buying_window": c.buying_window or calib_sum.get("buying_window"),
            "urgency_summary": c.urgency_reason or calib_sum.get("urgency_summary"),
            "urgent_assets_count": calib_sum["due_metrics"]["overdue"] + calib_sum["due_metrics"]["due_next_30_days"],
            "contact_person": person.full_name if person else None,
            "contact_phone": person.phone if person else None,
            "contact_email": person.email if person else None,
        })

    return {
        "tool": "get_priority_leads",
        "total": len(results),
        "results": results,
    }


def match_nabl_fit_tool(instrument_name: str, parameter: Optional[str] = None, range_val: Optional[str] = None) -> dict[str, Any]:
    """Test instrument calibration parameters against Oorja NABL accredited scope."""
    fit = match_nabl_service_fit(instrument_name, parameter, range_val)
    return {
        "tool": "match_nabl_fit",
        "instrument_name": instrument_name,
        "fit_status": fit["fit_status"],
        "discipline": fit["discipline"],
        "nabl_accredited": fit["nabl_accredited"],
        "reason": fit["reason"],
    }


def get_quotation_history_tool(db: Session, company_id: Optional[int] = None, query: Optional[str] = None, limit: int = 20) -> dict[str, Any]:
    """Retrieve quotation history and pricing for a company or instrument."""
    base = db.query(Quotation)
    if company_id:
        base = base.filter(Quotation.company_id == company_id)
    if query:
        pattern = f"%{query.strip()}%"
        base = base.filter(or_(Quotation.customer_name.ilike(pattern), Quotation.quotation_number.ilike(pattern)))

    rows = base.order_by(Quotation.quotation_date.desc(), Quotation.id.desc()).limit(limit).all()
    return {
        "tool": "get_quotation_history",
        "total": len(rows),
        "results": [
            {
                "id": r.id,
                "quotation_number": r.quotation_number,
                "version_number": r.version_number,
                "customer_name": r.customer_name,
                "quotation_date": r.quotation_date.isoformat(),
                "status": r.status,
                "subtotal": float(r.subtotal or 0),
                "total": float(r.total or 0),
                "human_approved": bool(r.human_approved),
                "items_count": len(r.items),
            }
            for r in rows
        ],
    }


def search_quotations(db: Session, query: str = "", limit: int = 20) -> dict[str, Any]:
    """Search quotations by number or customer name."""
    return get_quotation_history_tool(db, query=query, limit=limit)


def draft_followup_message_tool(db: Session, company_id: int) -> dict[str, Any]:
    """Draft a context-aware follow-up message using physical plant and calibration due data."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    person = db.query(Person).filter(Person.company_id == company_id, Person.is_decision_maker == 1).first() or \
             db.query(Person).filter(Person.company_id == company_id).first()

    summary = calculate_company_asset_calibration_summary(company_id, db)
    due_metrics = summary.get("due_metrics", {})
    facility = db.query(Facility).filter(Facility.company_id == company_id).first()

    salutation = f"Hi {person.full_name.split()[0]}," if person and person.full_name else "Hello,"
    plant_ref = f"for your {facility.name}" if facility else f"for {company.name}"

    if due_metrics.get("overdue", 0) > 0 or due_metrics.get("due_next_30_days", 0) > 0:
        count = due_metrics.get("overdue", 0) + due_metrics.get("due_next_30_days", 0)
        subject = f"NABL Calibration Due Notice — {company.name}"
        body = (
            f"{salutation}\n\n"
            f"I am writing from Oorja Technical Services regarding upcoming calibration requirements {plant_ref}. "
            f"We noticed that {count} critical instruments are currently approaching or past their calibration due date.\n\n"
            f"Our NABL accredited laboratory (CC-3498) offers on-site testing for Pressure, Temperature, and Electro-Technical parameters "
            f"with standard 48-hour certificate turnaround.\n\n"
            f"Could we schedule a brief 5-minute call this week to review the master asset list?\n\n"
            f"Best regards,\nOorja Sales Team"
        )
    else:
        subject = f"NABL Calibration Support — {company.name}"
        body = (
            f"{salutation}\n\n"
            f"I hope you're having a productive week. Reaching out from Oorja Technical Services regarding NABL calibration capabilities {plant_ref}.\n\n"
            f"We support leading industrial plants across Gujarat with comprehensive Pressure (-0.95 to 700 bar), Thermal (-40 to 1200°C), and Electrical scope.\n\n"
            f"Would you be open to a quick introductory exchange?\n\n"
            f"Best regards,\nOorja Sales Team"
        )

    return {
        "tool": "draft_followup_message",
        "company_id": company_id,
        "recipient_name": person.full_name if person else None,
        "recipient_email": person.email if person else None,
        "subject": subject,
        "body": body,
    }


def sales_summary(db: Session) -> dict[str, Any]:
    """Summarize active pipeline, tasks, quotations, and due calibrations."""
    opportunities = db.query(Opportunity).filter(Opportunity.stage.notin_(["Won", "Lost"])).all()
    tasks = db.query(SalesTask).filter(SalesTask.status == "Open").all()
    quotations = db.query(Quotation).filter(Quotation.status.notin_(["Won", "Lost"])).all()
    pipeline_value = sum(float(item.estimated_value or 0) for item in opportunities)

    # Active calibration due metrics
    today = date.today()
    due_60 = (
        db.query(CustomerAsset)
        .filter(
            CustomerAsset.status == "Active",
            CustomerAsset.calibration_due_date.isnot(None),
            CustomerAsset.calibration_due_date <= (today + timedelta(days=60)),
        )
        .count()
    )

    return {
        "tool": "sales_summary",
        "open_opportunities": len(opportunities),
        "open_pipeline_value": pipeline_value,
        "open_tasks": len(tasks),
        "open_quotations": len(quotations),
        "active_calibrations_due_60d": due_60,
        "generated_at": datetime.utcnow().isoformat(),
    }


def record_feedback(
    db: Session,
    entity_type: str,
    entity_id: int | None,
    action_type: str,
    ai_value: dict | None,
    human_value: dict | None,
    reason: str | None,
) -> dict[str, Any]:
    """Record an AI-to-human feedback event for the learning loop."""
    feedback = AIFeedback(
        entity_type=entity_type,
        entity_id=entity_id,
        action_type=action_type,
        ai_value=ai_value,
        human_value=human_value,
        reason=reason,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {"tool": "record_feedback", "id": feedback.id, "status": "recorded"}


# Bounded Tool Registry Map
from services.territory_intelligence import get_industrial_clusters, get_visit_recommendations
from models.competitor_intel import CompetitorProfile

TOOLS = {
    "search_companies": search_companies,
    "search_contacts": search_contacts,
    "get_calibration_due": get_calibration_due_tool,
    "get_priority_leads": get_priority_leads_tool,
    "match_nabl_fit": match_nabl_fit_tool,
    "get_quotation_history": get_quotation_history_tool,
    "get_territory_clusters": get_industrial_clusters,
    "get_visit_recommendations": get_visit_recommendations,
    "draft_followup_message": draft_followup_message_tool,
    "sales_summary": sales_summary,
    "record_feedback": record_feedback,
}


def _legacy_keyword_routing(query: str, db: Session) -> dict[str, Any]:
    """Legacy deterministic keyword router for Ask Oorja."""
    q = (query or "").strip().lower()

    # 1. Intent: Priority contacts / Whom to contact today
    if any(k in q for k in ["contact today", "priority", "who should i call", "which companies"]):
        data = get_priority_leads_tool(db, limit=10)
        facts = [
            f"• {r['company_name']} ({r['city']}): {r['urgency_summary']} (Score: {r['icp_score']})"
            for r in data["results"][:5]
        ]
        answer = (
            f"Here are the top priority companies to contact today based on active calibration windows and ICP scores:\n\n"
            + ("\n".join(facts) if facts else "No immediate high-urgency companies found.")
        )
        return {
            "query": query,
            "intent": "priority_outreach",
            "verified_facts": data["results"],
            "answer": answer,
            "tool_used": "get_priority_leads",
        }

    # 2. Intent: Calibration due dates / Upcoming renewals
    if any(k in q for k in ["calibration due", "due within", "overdue", "expiring", "instruments due"]):
        days_match = re.search(r"(\d+)\s*days?", q)
        days = int(days_match.group(1)) if days_match else 60
        data = get_calibration_due_tool(db, days=days, limit=10)
        facts = [
            f"• {r['instrument_name']} at {r['company_name']}: Due {r['calibration_due_date']} ({r['due_status']}, {r['days_until_due']}d remaining)"
            for r in data["results"][:5]
        ]
        answer = (
            f"Found {data['total']} instruments due for calibration within {days} days:\n\n"
            + ("\n".join(facts) if facts else f"No instruments due within {days} days.")
        )
        return {
            "query": query,
            "intent": "calibration_due_lookup",
            "verified_facts": data["results"],
            "answer": answer,
            "tool_used": "get_calibration_due",
        }

    # 3. Intent: NABL Scope & Capability Matching
    if any(k in q for k in ["nabl", "scope", "capability", "can we calibrate", "in-house", "within oorja"]):
        clean_name = query
        for remove_word in ["is", "this", "instrument", "within", "oorja's", "oorja", "nabl", "capability", "can we calibrate", "?"]:
            clean_name = re.sub(re.escape(remove_word), "", clean_name, flags=re.IGNORECASE)
        inst_name = clean_name.strip() or query
        fit = match_nabl_service_fit(inst_name)
        answer = (
            f"NABL Scope Assessment for '{inst_name}':\n\n"
            f"• Fit Status: {fit['fit_status']}\n"
            f"• Discipline: {fit['discipline']}\n"
            f"• In-House Accredited: {'Yes' if fit['nabl_accredited'] else 'No'}\n"
            f"• Detail: {fit['reason']}"
        )
        return {
            "query": query,
            "intent": "nabl_fit_check",
            "verified_facts": [fit],
            "answer": answer,
            "tool_used": "match_nabl_fit",
        }

    # 4. Intent: Territory & Visit Itineraries
    if any(k in q for k in ["territory", "cluster", "visit", "itinerary", "corridor", "trip"]):
        routes_data = get_visit_recommendations(db, max_stops=3)
        if routes_data["routes"]:
            top_route = routes_data["routes"][0]
            stops_str = "\n".join([f"  {s['stop_number']}. {s['time_slot']}: {s['company_name']} ({s['objective']})" for s in top_route["itinerary"]])
            answer = (
                f"Recommended Visit Route for {top_route['cluster_name']} ({top_route['region']}):\n\n"
                f"• Estimated Calibration Opportunity: INR {top_route['est_calibration_opportunity']:,.2f}\n"
                f"• Planned Stops ({top_route['total_stops']}):\n{stops_str}"
            )
            return {
                "query": query,
                "intent": "territory_visit_plan",
                "verified_facts": routes_data["routes"],
                "answer": answer,
                "tool_used": "get_visit_recommendations",
            }
        else:
            clusters_data = get_industrial_clusters(db)
            top_clusters = clusters_data["clusters"][:3]
            cluster_strs = [f"• {c['cluster_name']}: {c['companies_count']} plants, {c['total_assets']} assets ({c['overdue_assets']} overdue)" for c in top_clusters]
            answer = (
                f"Industrial Corridors Overview ({clusters_data['total_clusters']} regions analyzed):\n\n"
                + "\n".join(cluster_strs)
                + "\n\nTip: Add specific assets or calibration dates to generate dedicated on-site audit itineraries."
            )
            return {
                "query": query,
                "intent": "territory_visit_plan",
                "verified_facts": clusters_data["clusters"],
                "answer": answer,
                "tool_used": "get_industrial_clusters",
            }

    # 5. Intent: Competitor Intelligence & Battlecards
    if any(k in q for k in ["competitor", "tcr", "micro calibration", "aditi", "rival"]):
        comps = db.query(CompetitorProfile).filter(CompetitorProfile.active == True).all()
        if comps:
            comp_facts = [
                f"• {c.name}: {c.positioning}\n  - Weakness/Angle: {', '.join(c.weaknesses or ['Standard pricing'])}"
                for c in comps[:3]
            ]
            answer = (
                f"Regional Calibration Competitor Intelligence:\n\n"
                + "\n".join(comp_facts)
                + "\n\nOorja Differentiator: 48-hour certificate turnaround, direct NABL accreditation, and emergency on-site dispatch."
            )
            return {
                "query": query,
                "intent": "competitor_intel",
                "verified_facts": [{"name": c.name, "focus": c.service_focus} for c in comps],
                "answer": answer,
                "tool_used": "search_competitors",
            }

    # 6. Intent: Next best action
    if any(k in q for k in ["next action", "what should i do", "next step", "what to do next"]):
        leads = get_priority_leads_tool(db, limit=1)
        if leads["results"]:
            top_company = leads["results"][0]
            nba = get_next_best_action(top_company["company_id"], db)
            answer = (
                f"Next Best Action Recommendation:\n\n"
                f"• Target Company: {top_company['company_name']}\n"
                f"• Action: {nba.get('action')}\n"
                f"• Timing: {nba.get('timing')}\n"
                f"• Reason: {nba.get('reason')}"
            )
            return {
                "query": query,
                "intent": "next_best_action",
                "verified_facts": [nba],
                "answer": answer,
                "tool_used": "get_next_best_action",
            }

    # 7. Intent: Draft follow-up message
    if any(k in q for k in ["draft", "email", "follow-up", "follow up", "message"]):
        leads = get_priority_leads_tool(db, limit=1)
        if leads["results"]:
            cid = leads["results"][0]["company_id"]
            draft = draft_followup_message_tool(db, cid)
            answer = (
                f"Drafted follow-up for {leads['results'][0]['company_name']}:\n\n"
                f"Subject: {draft.get('subject')}\n\n"
                f"{draft.get('body')}"
            )
            return {
                "query": query,
                "intent": "draft_message",
                "verified_facts": [draft],
                "answer": answer,
                "tool_used": "draft_followup_message",
            }

    # 8. Default Fallback: Sales Summary + Search
    comp_search = search_companies(db, query, limit=5)
    summary = sales_summary(db)
    answer = (
        f"Sales OS Status:\n"
        f"• Open Opportunities: {summary['open_opportunities']} (INR {summary['open_pipeline_value']:,.2f})\n"
        f"• Open Quotations: {summary['open_quotations']}\n"
        f"• Active Calibrations Due (60d): {summary['active_calibrations_due_60d']}\n\n"
        f"Matching Companies ({comp_search['total']}):\n"
        + "\n".join([f"• {c['name']} ({c['city']})" for c in comp_search["results"][:3]])
    )
    return {
        "query": query,
        "intent": "general_overview",
        "verified_facts": comp_search["results"],
        "answer": answer,
        "tool_used": "sales_summary",
    }


def ask_oorja(query: str, db: Session, session_id: Optional[str] = None) -> dict[str, Any]:
    """
    Intelligent Ask Oorja AI Orchestrator coordinator.
    Dispatches to multi-step reasoning orchestrator when configured, or falls back to
    deterministic keyword routing.
    """
    try:
        from services.orchestrator import AskOorjaOrchestrator
        orchestrator = AskOorjaOrchestrator()
        if orchestrator.is_available():
            return orchestrator.run(query, db, session_id=session_id)
    except Exception as e:
        logger.warning(f"Orchestrator execution error: {e}. Falling back to legacy routing.")

    return _legacy_keyword_routing(query, db)
