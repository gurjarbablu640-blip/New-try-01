"""Call Recording, Voice Analytics & Sales Coaching Service.

Manages call records, audio transcript analysis, salesperson coaching scorecards,
and feeds extracted customer facts directly into the Company Brain.
"""
from datetime import datetime
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.call_record import CallRecord
from models.company import Company
from models.person import Person
from models.company_brain import CompanyTimelineEvent
from services.call_intelligence import analyze_call_transcript
from services.company_brain import record_intelligence_fact, record_timeline_event

logger = logging.getLogger(__name__)


def log_completed_call(
    db: Session,
    company_id: int,
    transcript_text: str,
    person_id: Optional[int] = None,
    salesperson_name: str = "Sales Rep",
    duration_seconds: int = 240,
    call_channel: str = "Phone",
    recording_file_url: Optional[str] = None,
    call_objective: str = "discovery",
) -> CallRecord:
    """
    Analyzes, scores, and persists a completed sales call, extracting customer facts
    into the Company Brain and logging a chronological timeline event.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    analysis = analyze_call_transcript(transcript_text, company=company)

    # Persist Call Record
    record = CallRecord(
        company_id=company_id,
        person_id=person_id,
        salesperson_name=salesperson_name,
        duration_seconds=duration_seconds,
        call_channel=call_channel,
        recording_file_url=recording_file_url,
        transcript_text=transcript_text,
        call_objective=call_objective,
        call_score=analysis["call_score"],
        score_breakdown=analysis["score_breakdown"],
        buying_signals_detected=analysis["buying_signals_detected"],
        objections_detected=analysis["objections_detected"],
        extracted_facts={"has_buying_signals": bool(analysis["buying_signals_detected"])},
        coaching_advice=analysis["playbook_coaching_advice"],
        outcome_status="qualified" if analysis["buying_signals_detected"] else "completed",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 1. Log Chronological Timeline Event
    record_timeline_event(
        db=db,
        company_id=company_id,
        event_type="sales_call_completed",
        title=f"Sales Call ({call_channel}) - Score: {record.call_score}/100",
        description=f"Objective: {call_objective}. Signals: {len(analysis['buying_signals_detected'])}. Next Action: {analysis['recommended_next_action']}",
        impact_level="high" if analysis["buying_signals_detected"] else "medium",
        buying_window_impact="immediate" if analysis["buying_signals_detected"] else None,
        source="call_intelligence",
        source_ref=f"call-{record.id}",
    )

    # 2. Extract Verifiable Facts from Call Transcript
    if analysis["buying_signals_detected"]:
        record_intelligence_fact(
            db=db,
            company_id=company_id,
            category="sales_conversation",
            fact_key=f"call_signals_{record.id}",
            fact_value={"signals": analysis["buying_signals_detected"], "score": record.call_score},
            source="call_recording",
            confidence=0.95,
            evidence_text=transcript_text[:250],
        )

    return record


def get_sales_coaching_overview(db: Session, salesperson_name: Optional[str] = None) -> dict[str, Any]:
    """
    Aggregates calling analytics, average scores, objection frequency, and sales coaching insights.
    """
    query = db.query(CallRecord)
    if salesperson_name:
        query = query.filter(CallRecord.salesperson_name == salesperson_name)
    records = query.order_by(desc(CallRecord.call_date)).limit(100).all()

    total_calls = len(records)
    if total_calls == 0:
        return {
            "total_calls": 0,
            "average_call_score": 0,
            "top_objections": [],
            "top_signals": [],
            "coaching_summary": "No recorded calls yet. Upload call audio or paste transcripts to activate Voice Intelligence.",
        }

    avg_score = round(sum(r.call_score for r in records) / total_calls, 1)

    all_objections = []
    all_signals = []
    for r in records:
        if r.objections_detected:
            all_objections.extend(r.objections_detected)
        if r.buying_signals_detected:
            all_signals.extend(r.buying_signals_detected)

    from collections import Counter
    objection_counts = Counter(all_objections).most_common(5)
    signal_counts = Counter(all_signals).most_common(5)

    return {
        "total_calls": total_calls,
        "average_call_score": avg_score,
        "top_objections": [{"objection": o, "count": c} for o, c in objection_counts],
        "top_buying_signals": [{"signal": s, "count": c} for s, c in signal_counts],
        "coaching_summary": f"Analyzed {total_calls} calls (avg score {avg_score}/100). High-converting calls maintain >50% discovery talk ratio before introducing pricing.",
    }
