"""Sales Assistant API.

Provides explicit, auditable tool calls. Natural-language model selection can
be added above this layer later; tools themselves remain bounded and typed.
"""
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from database import SessionLocal
from services.sales_assistant import (
    record_feedback,
    sales_summary,
    search_companies,
    search_contacts,
    search_quotations,
)

router = APIRouter(prefix="/api/assistant", tags=["Sales Assistant"])


class ToolRequest(BaseModel):
    tool: str = Field(min_length=1)
    query: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


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
            {"name": "sales_summary", "read_only": True, "description": "Summarize active opportunities, tasks and quotations."},
            {"name": "record_feedback", "read_only": False, "approval_required": False, "description": "Record an AI-to-human correction for learning."},
        ]
    }


@router.post("/tool")
def run_tool(payload: ToolRequest):
    db = SessionLocal()
    try:
        if payload.tool == "sales_summary":
            return sales_summary(db)
        query = (payload.query or "").strip()
        if payload.tool == "search_companies":
            return search_companies(db, query, payload.limit)
        if payload.tool == "search_contacts":
            return search_contacts(db, query, payload.limit)
        if payload.tool == "search_quotations":
            return search_quotations(db, query, payload.limit)
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
