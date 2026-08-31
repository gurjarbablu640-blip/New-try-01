"""Specialist Sub-Agents for Ask Oorja AI Orchestration.

Five specialist sub-agents that reason and recommend only:
1. LeadPrioritizer: Prioritization, account targeting, decision makers
2. CalibrationAnalyst: Calibration due dates, NABL scope capability
3. TerritoryPlanner: Industrial clusters, visit route itineraries
4. QuotationAdvisor: Pricing intelligence, quotation history, learned rule application
5. OutreachDrafter: Follow-up drafting, competitor battle-card synthesis

All sub-agents execute sequentially and use deterministic tool functions.
"""
from dataclasses import dataclass, field
import json
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.competitor_intel import CompetitorProfile
from services.llm_provider import LLMProvider, LLMResponse
from services.sales_assistant import (
    draft_followup_message_tool,
    get_calibration_due_tool,
    get_priority_leads_tool,
    get_quotation_history_tool,
    match_nabl_fit_tool,
    sales_summary,
    search_companies,
    search_contacts,
)
from services.territory_intelligence import get_industrial_clusters, get_visit_recommendations

logger = logging.getLogger(__name__)


@dataclass
class SubAgentTask:
    agent_name: str
    question: str
    context: dict[str, Any] = field(default_factory=dict)
    learning_rules: list[dict[str, Any]] = field(default_factory=list)
    session_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SubAgentResult:
    agent_name: str
    tool_calls: list[dict[str, Any]]
    reasoning: str
    recommendation: dict[str, Any]
    confidence: float
    tokens_used: dict[str, int]
    verified_facts: list[dict[str, Any]] = field(default_factory=list)


class BaseSubAgent:
    name: str = "BaseAgent"
    description: str = ""

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        raise NotImplementedError


class LeadPrioritizerAgent(BaseSubAgent):
    name = "LeadPrioritizer"
    description = "Evaluates ICP scores, buying signals, and priority outreach targets."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        tool_calls = []
        verified_facts = []

        # Execute primary lead tools
        query_company = task.context.get("company_name") or task.context.get("query")
        if query_company:
            comp_data = search_companies(db, str(query_company), limit=5)
            tool_calls.append({"tool": "search_companies", "args": {"query": query_company}, "result_count": comp_data["total"]})
            verified_facts.extend(comp_data["results"])

        leads_data = get_priority_leads_tool(db, limit=10)
        tool_calls.append({"tool": "get_priority_leads", "args": {"limit": 10}, "result_count": leads_data["total"]})
        verified_facts.extend(leads_data["results"])

        system_prompt = (
            "You are the LeadPrioritizer specialist for Oorja Technical Services Sales OS.\n"
            "Analyze the verified company and lead data to prioritize outreach targets.\n"
            "Explain *why* each lead is urgent based on buying windows, ICP score, and calibration due dates.\n"
            "Return JSON with keys: reasoning (string), recommended_leads (list of dicts), confidence (float 0.0-1.0)."
        )

        user_content = {
            "question": task.question,
            "leads_data": leads_data["results"][:5],
            "context": task.context,
            "approved_learning_rules": task.learning_rules,
        }

        if provider and provider.is_available():
            try:
                resp: LLMResponse = provider.complete(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": json.dumps(user_content)}],
                    response_format="json",
                )
                parsed = resp.parse_json() or {}
                return SubAgentResult(
                    agent_name=self.name,
                    tool_calls=tool_calls,
                    reasoning=parsed.get("reasoning") or resp.text,
                    recommendation=parsed,
                    confidence=float(parsed.get("confidence", 0.9)),
                    tokens_used=resp.usage,
                    verified_facts=verified_facts,
                )
            except Exception as e:
                logger.warning(f"{self.name} LLM completion error: {e}")

        # Fallback deterministic synthesis
        top_leads = leads_data["results"][:3]
        facts_summary = [f"{l['company_name']} ({l.get('city')}): Score {l.get('icp_score')}, Window {l.get('buying_window')}" for l in top_leads]
        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning="Ranked priority leads by ICP score and active calibration urgency window.",
            recommendation={"recommended_leads": top_leads, "summary": facts_summary},
            confidence=0.85,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


class CalibrationAnalystAgent(BaseSubAgent):
    name = "CalibrationAnalyst"
    description = "Analyzes asset calibration due dates and tests NABL accreditation scope fit."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        tool_calls = []
        verified_facts = []

        days = task.context.get("days", 60)
        due_data = get_calibration_due_tool(db, days=days, limit=15)
        # Check NABL fit if an instrument name is provided or in question
        instrument_query = task.context.get("instrument_name")
        if not instrument_query:
            if ":" in task.question:
                instrument_query = task.question.split(":")[-1].strip("? .")
            elif any(k in task.question.lower() for k in ["caliper", "cmm", "gauge", "micrometer", "indicator"]):
                for cand in ["Vernier Caliper", "CMM", "Pressure Gauge", "Height Gauge", "Micrometer"]:
                    if cand.lower() in task.question.lower():
                        instrument_query = cand
                        break

        nabl_fit = None
        if instrument_query:
            nabl_fit = match_nabl_fit_tool(instrument_query)
            tool_calls.append({"tool": "match_nabl_fit", "args": {"instrument_name": instrument_query}, "fit_status": nabl_fit["fit_status"]})
            verified_facts.insert(0, nabl_fit)

        system_prompt = (
            "You are the CalibrationAnalyst specialist for Oorja Technical Services.\n"
            "Analyze instrument calibration due dates and assess NABL scope coverage.\n"
            "Highlight overdue vs upcoming instruments and identify any capability gaps.\n"
            "Return JSON with keys: reasoning (string), due_summary (dict), nabl_assessment (dict), confidence (float)."
        )

        user_content = {
            "question": task.question,
            "due_data": due_data["results"][:8],
            "nabl_fit": nabl_fit,
            "context": task.context,
            "approved_learning_rules": task.learning_rules,
        }

        if provider and provider.is_available():
            try:
                resp: LLMResponse = provider.complete(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": json.dumps(user_content)}],
                    response_format="json",
                )
                parsed = resp.parse_json() or {}
                return SubAgentResult(
                    agent_name=self.name,
                    tool_calls=tool_calls,
                    reasoning=parsed.get("reasoning") or resp.text,
                    recommendation=parsed,
                    confidence=float(parsed.get("confidence", 0.95)),
                    tokens_used=resp.usage,
                    verified_facts=verified_facts,
                )
            except Exception as e:
                logger.warning(f"{self.name} LLM error: {e}")

        # Deterministic fallback
        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning=f"Identified {due_data['total']} instruments due within {days} days.",
            recommendation={"total_due": due_data["total"], "items": due_data["results"][:5], "nabl_fit": nabl_fit},
            confidence=0.88,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


class TerritoryPlannerAgent(BaseSubAgent):
    name = "TerritoryPlanner"
    description = "Optimizes on-site sales itineraries and analyzes industrial territory corridors."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        tool_calls = []
        verified_facts = []

        visit_data = get_visit_recommendations(db, max_stops=4)
        tool_calls.append({"tool": "get_visit_recommendations", "args": {"max_stops": 4}, "routes_count": len(visit_data.get("routes", []))})
        verified_facts.extend(visit_data.get("routes", []))

        clusters_data = get_industrial_clusters(db)
        tool_calls.append({"tool": "get_territory_clusters", "args": {}, "clusters_count": clusters_data.get("total_clusters", 0)})

        system_prompt = (
            "You are the TerritoryPlanner specialist for Oorja Sales OS.\n"
            "Synthesize geographical cluster densities and visit itineraries to maximize on-site calibration value.\n"
            "Return JSON with keys: reasoning (string), recommended_route (dict), clusters_summary (list), confidence (float)."
        )

        user_content = {
            "question": task.question,
            "routes": visit_data.get("routes", [])[:2],
            "clusters": clusters_data.get("clusters", [])[:4],
            "context": task.context,
            "approved_learning_rules": task.learning_rules,
        }

        if provider and provider.is_available():
            try:
                resp: LLMResponse = provider.complete(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": json.dumps(user_content)}],
                    response_format="json",
                )
                parsed = resp.parse_json() or {}
                return SubAgentResult(
                    agent_name=self.name,
                    tool_calls=tool_calls,
                    reasoning=parsed.get("reasoning") or resp.text,
                    recommendation=parsed,
                    confidence=float(parsed.get("confidence", 0.9)),
                    tokens_used=resp.usage,
                    verified_facts=verified_facts,
                )
            except Exception as e:
                logger.warning(f"{self.name} LLM error: {e}")

        # Deterministic fallback
        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning="Analyzed industrial clusters and generated top visit route.",
            recommendation={"routes": visit_data.get("routes", [])[:2], "clusters": clusters_data.get("clusters", [])[:3]},
            confidence=0.85,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


class QuotationAdvisorAgent(BaseSubAgent):
    name = "QuotationAdvisor"
    description = "Provides quotation history, pricing intelligence, and applies human-approved margin rules."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        tool_calls = []
        verified_facts = []

        company_id = task.context.get("company_id")
        query = task.context.get("query") or task.context.get("instrument_category")
        quote_data = get_quotation_history_tool(db, company_id=company_id, query=query, limit=10)
        tool_calls.append({"tool": "get_quotation_history", "args": {"company_id": company_id, "query": query}, "total": quote_data["total"]})
        verified_facts.extend(quote_data["results"])

        summary = sales_summary(db)
        tool_calls.append({"tool": "sales_summary", "args": {}, "open_quotations": summary["open_quotations"]})

        system_prompt = (
            "You are the QuotationAdvisor specialist for Oorja Sales OS.\n"
            "Analyze historical quotation pricing and formulate pricing recommendations.\n"
            "CRITICAL: Always check and apply any APPROVED learning rules (e.g. instrument margin adjustments).\n"
            "Return JSON with keys: reasoning (string), recommended_price (number or null), rules_applied (list of strings), confidence (float)."
        )

        user_content = {
            "question": task.question,
            "quotation_history": quote_data["results"][:5],
            "sales_summary": summary,
            "context": task.context,
            "approved_learning_rules": task.learning_rules,
        }

        if provider and provider.is_available():
            try:
                resp: LLMResponse = provider.complete(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": json.dumps(user_content)}],
                    response_format="json",
                )
                parsed = resp.parse_json() or {}
                return SubAgentResult(
                    agent_name=self.name,
                    tool_calls=tool_calls,
                    reasoning=parsed.get("reasoning") or resp.text,
                    recommendation=parsed,
                    confidence=float(parsed.get("confidence", 0.92)),
                    tokens_used=resp.usage,
                    verified_facts=verified_facts,
                )
            except Exception as e:
                logger.warning(f"{self.name} LLM error: {e}")

        # Fallback with rule calculation
        base_price = 4500.0
        applied_rules = []
        margin_mult = 1.0
        for rule in task.learning_rules:
            pat = rule.get("pattern", {})
            adj = pat.get("adjustment_percent")
            if adj:
                margin_mult *= (1.0 + float(adj) / 100.0)
                applied_rules.append(f"{rule.get('rule_key')}: +{adj}%")

        final_price = base_price * margin_mult
        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning=f"Calculated pricing with {len(applied_rules)} approved rules applied.",
            recommendation={"recommended_price": final_price, "rules_applied": applied_rules, "history": quote_data["results"][:3]},
            confidence=0.88,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


class OutreachDrafterAgent(BaseSubAgent):
    name = "OutreachDrafter"
    description = "Drafts personalized follow-up messages and competitor rebuttal angles."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        tool_calls = []
        verified_facts = []

        company_id = task.context.get("company_id")
        draft_data = None
        if company_id:
            draft_data = draft_followup_message_tool(db, company_id)
            tool_calls.append({"tool": "draft_followup_message", "args": {"company_id": company_id}})
            verified_facts.append(draft_data)

        # Check competitor intelligence
        comps = db.query(CompetitorProfile).filter(CompetitorProfile.active == True).all()
        comp_facts = [{"name": c.name, "positioning": c.positioning, "weaknesses": c.weaknesses} for c in comps]
        tool_calls.append({"tool": "search_competitors", "args": {}, "competitors_count": len(comps)})

        system_prompt = (
            "You are the OutreachDrafter specialist for Oorja Sales OS.\n"
            "Draft a professional, compelling, and specific outreach/follow-up email.\n"
            "Reference specific plant assets, NABL certifications, and competitive advantages.\n"
            "Return JSON with keys: reasoning (string), subject (string), body (string), confidence (float)."
        )

        user_content = {
            "question": task.question,
            "draft_template": draft_data,
            "competitor_intel": comp_facts[:3],
            "context": task.context,
            "approved_learning_rules": task.learning_rules,
        }

        if provider and provider.is_available():
            try:
                resp: LLMResponse = provider.complete(
                    system_prompt=system_prompt,
                    messages=[{"role": "user", "content": json.dumps(user_content)}],
                    response_format="json",
                )
                parsed = resp.parse_json() or {}
                return SubAgentResult(
                    agent_name=self.name,
                    tool_calls=tool_calls,
                    reasoning=parsed.get("reasoning") or resp.text,
                    recommendation=parsed,
                    confidence=float(parsed.get("confidence", 0.9)),
                    tokens_used=resp.usage,
                    verified_facts=verified_facts,
                )
            except Exception as e:
                logger.warning(f"{self.name} LLM error: {e}")

        # Deterministic fallback
        subj = draft_data.get("subject", "Calibration Services Follow-up") if draft_data else "Calibration Inquiry"
        body = draft_data.get("body", "Following up on your instrument calibration requirements.") if draft_data else "Inquiry regarding calibration."
        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning="Constructed personalized message using plant asset context.",
            recommendation={"subject": subj, "body": body},
            confidence=0.85,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


class RegulatorySpecialistAgent(BaseSubAgent):
    name = "RegulatorySpecialist"
    description = "Scans Legal Metrology, BIS QCOs, NABL policies, and compliance deadlines affecting accounts."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        from services.regulatory_radar import scan_regulatory_radar_for_company, seed_default_regulatory_intelligence
        from models.company import Company
        tool_calls = []
        verified_facts = []

        seed_default_regulatory_intelligence(db)
        query_company = task.context.get("company_name") or task.context.get("query")
        company = None
        if query_company:
            company = db.query(Company).filter(Company.name.ilike(f"%{query_company}%")).first()

        if company:
            notices = scan_regulatory_radar_for_company(company, db)
            tool_calls.append({"tool": "scan_regulatory_radar", "args": {"company_id": company.id}, "matches_count": len(notices)})
            verified_facts.extend(notices)
        else:
            from models.company_brain import RegulatoryIntelligence
            all_notices = db.query(RegulatoryIntelligence).filter(RegulatoryIntelligence.active == True).limit(5).all()
            notices = [{"regulation_code": n.regulation_code, "title": n.title, "authority": n.authority, "deadline": str(n.compliance_deadline)} for n in all_notices]
            tool_calls.append({"tool": "get_active_regulations", "args": {}, "count": len(notices)})
            verified_facts.extend(notices)

        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning=f"Identified {len(notices)} active regulatory drivers requiring NABL-traceable measurement conformity.",
            recommendation={"regulatory_notices": notices},
            confidence=0.92,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


class RevenueAutopilotAgent(BaseSubAgent):
    name = "RevenueAutopilot"
    description = "Evaluates Next Best Revenue Actions, Deal Rescue diagnostics, and account white-space maps."

    def run(self, task: SubAgentTask, db: Session, provider: Optional[LLMProvider]) -> SubAgentResult:
        from services.revenue_autopilot import compute_next_best_revenue_action, generate_account_whitespace_map
        from models.company import Company
        tool_calls = []
        verified_facts = []

        query_company = task.context.get("company_name") or task.context.get("query")
        company = None
        if query_company:
            company = db.query(Company).filter(Company.name.ilike(f"%{query_company}%")).first()

        if not company:
            company = db.query(Company).first()

        if company:
            action = compute_next_best_revenue_action(company, db)
            tool_calls.append({"tool": "compute_next_best_action", "args": {"company_id": company.id}, "result": action["recommended_action"]})
            ws = generate_account_whitespace_map(company, db)
            tool_calls.append({"tool": "generate_whitespace_map", "args": {"company_id": company.id}, "unserved_count": ws["expansion_opportunity_count"]})
            verified_facts.append(action)
            verified_facts.append(ws)
            rec = {"next_action": action, "whitespace_expansion": ws}
            reasoning = f"Recommended action for {company.name}: {action['recommended_action']} ({action['priority']} priority)."
        else:
            rec = {"next_action": "No active company found for revenue autopilot evaluation."}
            reasoning = "No company in database."

        return SubAgentResult(
            agent_name=self.name,
            tool_calls=tool_calls,
            reasoning=reasoning,
            recommendation=rec,
            confidence=0.90,
            tokens_used={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            verified_facts=verified_facts,
        )


SUB_AGENT_REGISTRY: dict[str, BaseSubAgent] = {
    "LeadPrioritizer": LeadPrioritizerAgent(),
    "CalibrationAnalyst": CalibrationAnalystAgent(),
    "TerritoryPlanner": TerritoryPlannerAgent(),
    "QuotationAdvisor": QuotationAdvisorAgent(),
    "OutreachDrafter": OutreachDrafterAgent(),
    "RegulatorySpecialist": RegulatorySpecialistAgent(),
    "RevenueAutopilot": RevenueAutopilotAgent(),
}
