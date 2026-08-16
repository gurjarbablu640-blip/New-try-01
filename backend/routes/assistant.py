"""Sales Assistant API (Ask Oorja).

Provides explicit, auditable tool calls and high-level conversational routing.
"""
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from database import SessionLocal
from services.sales_assistant import (
    ask_oorja,
    draft_followup_message_tool,
    get_calibration_due_tool,
    get_priority_leads_tool,
    get_quotation_history_tool,
    match_nabl_fit_tool,
    record_feedback,
    sales_summary,
    search_companies,
    search_contacts,
    search_quotations,
)
from services.web_research_service import search_research

router = APIRouter(prefix="/api/assistant", tags=["Sales Assistant"])


class ToolRequest(BaseModel):
    tool: str = Field(min_length=1)
    query: Optional[str] = None
    company_id: Optional[int] = None
    days: Optional[int] = 60
    limit: int = Field(default=20, ge=1, le=100)


class AskOorjaRequest(BaseModel):
    question: str = Field(min_length=1)


class FeedbackRequest(BaseModel):
    entity_type: str
    entity_id: Optional[int] = None
    action_type: str
    ai_value: Optional[dict[str, Any]] = None
    human_value: Optional[dict[str, Any]] = None
    reason: Optional[str] = None


@router.get("/tools")
def list_tools():
    return {
        "tools": [
            {"name": "search_companies", "read_only": True, "description": "Search CRM companies by name, city or industry."},
            {"name": "search_contacts", "read_only": True, "description": "Search CRM contacts by name, designation, department or email."},
            {"name": "search_quotations", "read_only": True, "description": "Search historical and active quotations."},
            {"name": "get_calibration_due", "read_only": True, "description": "Get instruments due for calibration within N days across customers."},
            {"name": "get_priority_leads", "read_only": True, "description": "Identify high-priority companies to contact today based on buying windows and urgency."},
            {"name": "match_nabl_fit", "read_only": True, "description": "Test instrument calibration parameters against Oorja NABL accredited scope."},
            {"name": "draft_followup_message", "read_only": True, "description": "Draft context-aware outreach/follow-up email based on plant assets."},
            {"name": "search_web_evidence", "read_only": True, "description": "Search stored, source-traceable web research evidence."},
            {"name": "sales_summary", "read_only": True, "description": "Summarize active opportunities, tasks, quotations, and due calibrations."},
            {"name": "record_feedback", "read_only": False, "approval_required": False, "description": "Record an AI-to-human correction for learning."},
        ]
    }


@router.post("/ask")
def ask_assistant(payload: AskOorjaRequest):
    """Conversational endpoint for Ask Oorja."""
    db = SessionLocal()
    try:
        return ask_oorja(payload.question, db)
    finally:
        db.close()


@router.post("/tool")
def run_tool(payload: ToolRequest):
    db = SessionLocal()
    try:
        query = (payload.query or "").strip()
        if payload.tool == "sales_summary":
            return sales_summary(db)
        if payload.tool == "search_companies":
            return search_companies(db, query, payload.limit)
        if payload.tool == "search_contacts":
            return search_contacts(db, query, payload.limit)
        if payload.tool == "search_quotations":
            return search_quotations(db, query, payload.limit)
        if payload.tool == "get_calibration_due":
            return get_calibration_due_tool(db, days=payload.days or 60, limit=payload.limit)
        if payload.tool == "get_priority_leads":
            return get_priority_leads_tool(db, limit=payload.limit)
        if payload.tool == "match_nabl_fit":
            return match_nabl_fit_tool(query)
        if payload.tool == "draft_followup_message" and payload.company_id:
            return draft_followup_message_tool(db, payload.company_id)
        if payload.tool == "search_web_evidence":
            return search_research(db, query, company_id=payload.company_id, limit=payload.limit)
        return {"error": f"Unknown tool: {payload.tool}"}
    finally:
        db.close()


@router.post("/feedback")
def feedback(payload: FeedbackRequest):
    db = SessionLocal()
    try:
        return record_feedback(
            db,
            payload.entity_type,
            payload.entity_id,
            payload.action_type,
            payload.ai_value,
            payload.human_value,
            payload.reason,
        )
    finally:
        db.close()
