"""Pre-Serper Business Analyst / Search Strategist Engine for Salesoorja.

Phase 3 Core Architecture:
- Evaluates historical search yield, downstream conversions, and cost efficiency.
- Authoritative FK: discovery_query_logs.analyst_decision_id.
- Exposure-normalized strategy performance with sample-size confidence.
- 75% EXPLOIT / 25% EXPLORE rolling window policy with anti-starvation.
- Weak cold-start priors with evidence-dominant prior decay.
- Recency weighting (<=7d 1.0x, 8-30d 0.7x, >30d 0.4x).
- LLM Role: DeepSeek primary commercial rationale, Gemini fallback, deterministic template fallback.
- Primary KPI: ENQUIRIES GENERATED.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import SessionLocal
from models.business_analyst_decision import BusinessAnalystDecision
from models.company import Company
from models.discovery_query_log import DiscoveryQueryLog
from services.discovery_query_planner import (
    INDUSTRIAL_CORRIDORS,
    MANUFACTURING_SECTORS,
    TRIGGER_FAMILIES,
)

logger = logging.getLogger(__name__)

# Business Outcome Valuation Weights (v1 transparent weights)
W_ENQUIRY = 100.0
W_REPLY = 40.0
W_EMAIL_SENT = 10.0
W_VERIFIED_PERSON = 6.0
W_APOLLO_REACHED = 3.0
W_STRONG_OPPORTUNITY = 2.0
W_PRODUCTIVE_QUERY = 1.0

# Base Calibration Relevance Priors (Weak initial guidance)
SECTOR_CALIBRATION_PRIORS: Dict[str, float] = {
    "Automotive & Auto Components": 0.70,
    "EV & Battery Systems": 0.70,
    "Aerospace & Defense": 0.75,
    "Precision Engineering & CNC Tooling": 0.65,
    "Semiconductor & Electronics (EMS)": 0.70,
    "Pharmaceuticals & Bulk Drugs": 0.65,
    "Medical Devices & Healthcare Equipment": 0.65,
    "Solar & Renewable Energy Equipment": 0.55,
    "Heavy Engineering & Industrial Machinery": 0.60,
    "Chemicals & Specialty Materials": 0.50,
    "Power Transmission & Electrical Equipment": 0.55,
    "Telecom & Optical Fiber Equipment": 0.50,
    "Railways & Rolling Stock Components": 0.60,
    "Packaging & Converting Machinery": 0.50,
    "Metals & Advanced Alloys Processing": 0.55,
}


class BusinessAnalystService:
    """Intelligent Pre-Serper Search Strategist and Portfolio Optimizer."""

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            return self._redis
        except Exception:
            return None

    # ── 1. Downstream Outcome Aggregation & Normalization ───────────────────

    def aggregate_historical_outcomes(
        self,
        db: Session,
        sector: str,
        trigger_family: Optional[str] = None,
        geography: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate historical queries and downstream conversions with recency weighting.

        Maintains RAW counts and EXPOSURE-NORMALIZED rates with denominator guards.
        """
        now_dt = now or datetime.now(timezone.utc)
        d7 = now_dt - timedelta(days=7)
        d30 = now_dt - timedelta(days=30)

        # 1. Fetch historical DiscoveryQueryLog records for this angle
        query = db.query(DiscoveryQueryLog).filter(DiscoveryQueryLog.sector == sector)
        if trigger_family:
            query = query.filter(DiscoveryQueryLog.trigger == trigger_family)
        if geography and geography != "Pan-India" and geography != "PAN INDIA":
            query = query.filter(DiscoveryQueryLog.geography == geography)

        query_logs = query.all()

        query_count = len(query_logs)
        productive_query_count = 0
        strong_opps = 0
        incomplete_opps = 0

        weighted_query_count = 0.0
        weighted_productive_count = 0.0
        weighted_strong_opps = 0.0

        query_ids = []
        for ql in query_logs:
            if ql.id is not None:
                query_ids.append(ql.id)

            executed_dt = ql.executed_at
            if executed_dt.tzinfo is None:
                executed_dt = executed_dt.replace(tzinfo=timezone.utc)

            # Recency weighting
            if executed_dt >= d7:
                w = 1.0
            elif executed_dt >= d30:
                w = 0.7
            else:
                w = 0.4

            weighted_query_count += w
            if ql.execution_state == "SUCCESS_PRODUCTIVE":
                productive_query_count += 1
                weighted_productive_count += w

            strong_opps += int(ql.strong_opportunities or 0)
            incomplete_opps += int(ql.incomplete_opportunities or 0)
            weighted_strong_opps += w * int(ql.strong_opportunities or 0)

        # 2. Downstream attribution: find companies linked to these queries or sector
        apollo_reached = 0
        person_passes = 0
        emails_sent = 0
        replies = 0
        enquiries = 0

        weighted_apollo = 0.0
        weighted_persons = 0.0
        weighted_emails = 0.0
        weighted_replies = 0.0
        weighted_enquiries = 0.0

        if query_ids:
            companies = (
                db.query(Company)
                .filter(Company.discovery_query_log_id.in_(query_ids))
                .all()
            )
        else:
            companies = (
                db.query(Company)
                .filter(Company.industry == sector)
                .limit(20)
                .all()
            )

        for comp in companies:
            c_created = comp.created_at or now_dt
            if c_created.tzinfo is None:
                c_created = c_created.replace(tzinfo=timezone.utc)
            w = 1.0 if c_created >= d7 else (0.7 if c_created >= d30 else 0.4)

            # Person counts
            persons = comp.persons or []
            if persons:
                apollo_reached += len(persons)
                weighted_apollo += w * len(persons)
                for p in persons:
                    if p.email or p.phone:
                        person_passes += 1
                        weighted_persons += w

            # Outreach emails & replies
            if comp.email_sent:
                emails_sent += 1
                weighted_emails += w
            if comp.reply_received:
                replies += 1
                weighted_replies += w

            # Orders / enquiries
            if comp.order_received or getattr(comp, "lead_status", "") in {"Won", "Enquiry", "Qualified"}:
                enquiries += 1
                weighted_enquiries += w

        # Denominator guards
        denom_queries = max(1, query_count)
        denom_emails = max(1, emails_sent)

        # Exposure-normalized rates
        productive_query_rate = round(productive_query_count / denom_queries, 3)
        strong_per_query = round(strong_opps / denom_queries, 3)
        apollo_per_query = round(apollo_reached / denom_queries, 3)
        person_pass_per_query = round(person_passes / denom_queries, 3)
        email_per_query = round(emails_sent / denom_queries, 3)
        reply_per_email = round(replies / denom_emails, 3) if emails_sent > 0 else 0.0
        enquiry_per_query = round(enquiries / denom_queries, 3)
        enquiry_per_email = round(enquiries / denom_emails, 3) if emails_sent > 0 else 0.0

        return {
            # Raw Counts
            "query_count": query_count,
            "productive_query_count": productive_query_count,
            "strong_opportunities": strong_opps,
            "incomplete_opportunities": incomplete_opps,
            "apollo_reached": apollo_reached,
            "person_passes": person_passes,
            "emails_sent": emails_sent,
            "replies": replies,
            "enquiries": enquiries,
            # Recency-weighted counts
            "weighted_query_count": round(weighted_query_count, 2),
            "weighted_productive_count": round(weighted_productive_count, 2),
            "weighted_strong_opps": round(weighted_strong_opps, 2),
            "weighted_apollo": round(weighted_apollo, 2),
            "weighted_persons": round(weighted_persons, 2),
            "weighted_emails": round(weighted_emails, 2),
            "weighted_replies": round(weighted_replies, 2),
            "weighted_enquiries": round(weighted_enquiries, 2),
            # Exposure-Normalized Rates
            "productive_query_rate": productive_query_rate,
            "strong_per_query": strong_per_query,
            "apollo_per_query": apollo_per_query,
            "person_pass_per_query": person_pass_per_query,
            "email_per_query": email_per_query,
            "reply_per_email": reply_per_email,
            "enquiry_per_query": enquiry_per_query,
            "enquiry_per_email": enquiry_per_email,
        }

    # ── 2. Sample-Size Confidence Calculation ──────────────────────────────

    def compute_sample_size_confidence(
        self,
        query_count: int,
        downstream_obs: int,
        productive_rate: float,
    ) -> float:
        """Calculate transparent sample-size confidence.

        Prevents small lucky samples from permanently dominating exploitation.
        """
        if query_count == 0:
            return 0.05

        # Query volume confidence (ramps to 1.0 at 10 queries)
        c_queries = min(1.0, query_count / 10.0)

        # Downstream observations confidence (ramps to 1.0 at 5 downstream events)
        c_obs = min(1.0, downstream_obs / 5.0)

        # Consistency factor
        consistency = max(0.1, min(1.0, productive_rate))

        conf = (0.5 * c_queries) + (0.3 * c_obs) + (0.2 * consistency)
        return round(max(0.05, min(1.0, conf)), 3)

    # ── 3. Transparent Strategy Scoring & Prior Decay ──────────────────────

    def compute_strategy_score(
        self,
        metrics: Dict[str, Any],
        sector: str,
        trigger: str,
        geography: str,
    ) -> Tuple[float, float, Dict[str, Any]]:
        """Calculate transparent strategy score balancing empirical rate vs weak prior.

        Returns: (priority_score, confidence, score_components)
        """
        query_count = metrics["query_count"]
        downstream_obs = (
            metrics["strong_opportunities"]
            + metrics["emails_sent"]
            + metrics["replies"]
            + metrics["enquiries"]
        )

        confidence = self.compute_sample_size_confidence(
            query_count=query_count,
            downstream_obs=downstream_obs,
            productive_rate=metrics["productive_query_rate"],
        )

        # Normalized Performance Score (weighted exposure rates)
        # Using recency-weighted rates for responsiveness
        w_queries = max(1.0, metrics["weighted_query_count"])
        w_emails = max(1.0, metrics["weighted_emails"])

        w_enquiry_rate = metrics["weighted_enquiries"] / w_queries
        w_reply_rate = metrics["weighted_replies"] / w_emails if metrics["weighted_emails"] > 0 else 0.0
        w_email_rate = metrics["weighted_emails"] / w_queries
        w_person_rate = metrics["weighted_persons"] / w_queries
        w_strong_rate = metrics["weighted_strong_opps"] / w_queries
        w_prod_rate = metrics["weighted_productive_count"] / w_queries

        empirical_score = (
            (W_ENQUIRY * w_enquiry_rate)
            + (W_REPLY * w_reply_rate * 0.5)
            + (W_EMAIL_SENT * w_email_rate * 0.2)
            + (W_VERIFIED_PERSON * w_person_rate * 0.1)
            + (W_STRONG_OPPORTUNITY * w_strong_rate * 0.1)
            + (W_PRODUCTIVE_QUERY * w_prod_rate * 0.1)
        )

        # Normalize empirical score into a clean 0 - 10 range
        normalized_empirical = min(10.0, empirical_score)

        # Base Prior (Calibration relevance + under-exploration bonus)
        base_prior = SECTOR_CALIBRATION_PRIORS.get(sector, 0.50) * 5.0
        if query_count == 0:
            base_prior += 1.5  # Under-tested boost

        # Prior Decay: as confidence grows, empirical evidence dominates
        prior_weight = max(0.05, 1.0 - confidence)
        evidence_weight = confidence

        priority_score = (base_prior * prior_weight) + (normalized_empirical * evidence_weight)
        priority_score = round(max(0.1, priority_score), 3)

        components = {
            "base_prior": round(base_prior, 2),
            "prior_weight": round(prior_weight, 2),
            "normalized_empirical": round(normalized_empirical, 2),
            "evidence_weight": round(evidence_weight, 2),
            "confidence": confidence,
            "weighted_enquiry_rate": round(w_enquiry_rate, 3),
            "weighted_reply_rate": round(w_reply_rate, 3),
            "weighted_strong_rate": round(w_strong_rate, 3),
            "weighted_prod_rate": round(w_prod_rate, 3),
        }

        return priority_score, confidence, components

    # ── 4. Rolling Exploration / Exploitation Policy ───────────────────────

    def determine_exploration_mode(
        self,
        db: Session,
        rolling_window_size: int = 16,
    ) -> Tuple[str, Dict[str, Any]]:
        """Implement ~75% EXPLOIT / ~25% EXPLORE over rolling recent decisions.

        Guarantees:
        - COLD_START when total system query volume is minimal (< 5 queries).
        - Rolling ratio check prevents independent random coin flip drift.
        """
        total_queries = db.query(func.count(DiscoveryQueryLog.id)).scalar() or 0
        if total_queries < 5:
            return "COLD_START", {
                "reason": f"System in cold-start ({total_queries}/5 total queries recorded)",
                "explore_ratio": 0.0,
                "window_size": 0,
            }

        recent_decisions = (
            db.query(BusinessAnalystDecision)
            .order_by(BusinessAnalystDecision.id.desc())
            .limit(rolling_window_size)
            .all()
        )

        if not recent_decisions:
            return "COLD_START", {
                "reason": "No previous strategic decisions recorded",
                "explore_ratio": 0.0,
                "window_size": 0,
            }

        explore_count = sum(1 for d in recent_decisions if d.mode == "EXPLORE")
        window_size = len(recent_decisions)
        explore_ratio = explore_count / max(1, window_size)

        # If explore ratio is below 25%, schedule an EXPLORE turn
        if explore_ratio < 0.25:
            mode = "EXPLORE"
            reason = f"Rolling explore ratio {explore_ratio:.1%} < 25% target over last {window_size} decisions"
        else:
            mode = "EXPLOIT"
            reason = f"Rolling explore ratio {explore_ratio:.1%} satisfies target (exploit mode active)"

        return mode, {
            "reason": reason,
            "explore_ratio": round(explore_ratio, 3),
            "explore_count": explore_count,
            "window_size": window_size,
        }

    # ── 5. Anti-Starvation & Portfolio Strategy Selection ──────────────────

    def evaluate_next_strategy(
        self,
        db: Session,
        preferred_sector: Optional[str] = None,
        preferred_geo: Optional[str] = None,
        preferred_trigger: Optional[str] = None,
    ) -> BusinessAnalystDecision:
        """Main entry point: evaluate strategic portfolio and select optimal next search angle."""
        mode, mode_meta = self.determine_exploration_mode(db)

        all_sectors = list(MANUFACTURING_SECTORS.keys())
        all_triggers = list(TRIGGER_FAMILIES.keys())
        all_geos = INDUSTRIAL_CORRIDORS

        # Track recent decision history for anti-starvation
        recent_decisions = (
            db.query(BusinessAnalystDecision)
            .order_by(BusinessAnalystDecision.id.desc())
            .limit(10)
            .all()
        )
        recent_sectors = [d.sector for d in recent_decisions if d.sector]
        recent_geos = [d.geography for d in recent_decisions if d.geography]
        recent_triggers = [d.trigger_family for d in recent_decisions if d.trigger_family]

        # Evaluate candidate angles
        candidate_scores: List[Dict[str, Any]] = []

        sectors_to_evaluate = (
            [preferred_sector]
            if (preferred_sector and preferred_sector in MANUFACTURING_SECTORS)
            else all_sectors
        )

        for sector in sectors_to_evaluate:
            # Check sector starvation: has sector been neglected in recent decisions?
            sector_starved = sector not in recent_sectors[:5] if len(recent_sectors) >= 5 else False

            # Default trigger for sector
            sec_default_trigger = MANUFACTURING_SECTORS[sector].get("default_trigger", "plant_expansion")
            triggers_to_test = (
                [preferred_trigger]
                if (preferred_trigger and preferred_trigger in TRIGGER_FAMILIES)
                else [sec_default_trigger, "plant_expansion", "capex_announcement"]
            )

            for trigger in triggers_to_test:
                geo_to_test = (
                    preferred_geo
                    if (preferred_geo and preferred_geo != "All" and preferred_geo != "PAN INDIA")
                    else (all_geos[0] if not recent_geos else next((g for g in all_geos if g not in recent_geos[:2]), all_geos[0]))
                )

                metrics = self.aggregate_historical_outcomes(
                    db=db,
                    sector=sector,
                    trigger_family=trigger,
                    geography=geo_to_test,
                )

                score, confidence, score_comps = self.compute_strategy_score(
                    metrics=metrics,
                    sector=sector,
                    trigger=trigger,
                    geography=geo_to_test,
                )

                # Anti-starvation adjustments:
                # In EXPLORE mode or COLD_START: strongly boost starved sectors and under-tested angles
                if mode in {"EXPLORE", "COLD_START"}:
                    if metrics["query_count"] == 0:
                        score += 3.0  # Big boost to untested angle
                    if sector_starved:
                        score += 2.0  # Anti-starvation boost
                    if trigger not in recent_triggers[:4]:
                        score += 1.0  # Trigger diversity boost
                else:
                    # In EXPLOIT mode: modest penalty if recently exhausted
                    if metrics["query_count"] > 0 and metrics["productive_query_rate"] < 0.2:
                        score = max(0.1, score - 1.5)

                candidate_scores.append({
                    "sector": sector,
                    "trigger_family": trigger,
                    "geography": geo_to_test,
                    "score": score,
                    "confidence": confidence,
                    "metrics": metrics,
                    "score_components": score_comps,
                })

        # Sort candidate angles descending by score
        candidate_scores.sort(key=lambda x: x["score"], reverse=True)
        chosen = candidate_scores[0]

        chosen_sector = chosen["sector"]
        chosen_trigger = chosen["trigger_family"]
        chosen_geo = chosen["geography"]
        chosen_score = chosen["score"]
        chosen_conf = chosen["confidence"]
        chosen_metrics = chosen["metrics"]
        chosen_comps = chosen["score_components"]

        # Search budget allocation (1 - 3 queries)
        search_budget = 3 if (mode == "EXPLOIT" and chosen_score >= 4.0) else 2

        # 6. Commercial Rationale Generation (LLM Advisory only)
        rationale = self._generate_commercial_rationale(
            mode=mode,
            sector=chosen_sector,
            trigger=chosen_trigger,
            geography=chosen_geo,
            score=chosen_score,
            confidence=chosen_conf,
            metrics=chosen_metrics,
        )

        # 7. Persist BusinessAnalystDecision in PostgreSQL
        decision = BusinessAnalystDecision(
            sector=chosen_sector,
            trigger_family=chosen_trigger,
            geography=chosen_geo,
            mode=mode,
            priority_score=chosen_score,
            confidence=chosen_conf,
            search_budget=search_budget,
            # Raw Counts
            historical_query_count=chosen_metrics["query_count"],
            productive_query_count=chosen_metrics["productive_query_count"],
            strong_opportunities=chosen_metrics["strong_opportunities"],
            incomplete_opportunities=chosen_metrics["incomplete_opportunities"],
            apollo_reached=chosen_metrics["apollo_reached"],
            person_passes=chosen_metrics["person_passes"],
            emails_sent=chosen_metrics["emails_sent"],
            replies=chosen_metrics["replies"],
            enquiries=chosen_metrics["enquiries"],
            # Normalized Rates
            productive_query_rate=chosen_metrics["productive_query_rate"],
            strong_per_query=chosen_metrics["strong_per_query"],
            apollo_per_query=chosen_metrics["apollo_per_query"],
            person_pass_per_query=chosen_metrics["person_pass_per_query"],
            email_per_query=chosen_metrics["email_per_query"],
            reply_per_email=chosen_metrics["reply_per_email"],
            enquiry_per_query=chosen_metrics["enquiry_per_query"],
            enquiry_per_email=chosen_metrics["enquiry_per_email"],
            score_components=chosen_comps,
            rationale=rationale,
            was_substituted=False,
            substitution_reason=None,
            actual_sector=chosen_sector,
            actual_trigger=chosen_trigger,
            actual_geography=chosen_geo,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)

        # 8. Cache current strategy in Redis
        r = self._get_redis()
        if r is not None:
            try:
                cache_payload = json.dumps({
                    "decision_id": decision.id,
                    "mode": mode,
                    "sector": chosen_sector,
                    "trigger_family": chosen_trigger,
                    "geography": chosen_geo,
                    "priority_score": chosen_score,
                    "confidence": chosen_conf,
                    "rationale": rationale,
                    "created_at": decision.created_at.isoformat() if decision.created_at else None,
                })
                r.setex("salesoorja:strategy:current", 86400, cache_payload)
            except Exception as e:
                logger.debug("Redis strategy cache write note: %s", e)

        return decision

    # ── 6. LLM Commercial Rationale Generation ─────────────────────────────

    def _generate_commercial_rationale(
        self,
        mode: str,
        sector: str,
        trigger: str,
        geography: str,
        score: float,
        confidence: float,
        metrics: Dict[str, Any],
    ) -> str:
        """Generate concise commercial rationale using DeepSeek primary, Gemini fallback, deterministic template."""
        # Fallback template
        deterministic_template = (
            f"{mode} | {sector} in {geography} ({trigger}): priority {score:.2f}, "
            f"confidence {confidence:.2f}. "
            f"Historical yield: {metrics['strong_opportunities']} strong opps, "
            f"{metrics['enquiries']} enquiries generated."
        )

        prompt = (
            f"You are the Salesoorja Business Analyst. Provide a concise 1-2 sentence commercial rationale for this search strategy.\n"
            f"Strategy Target: Mode={mode}, Sector={sector}, Corridor={geography}, Trigger={trigger}\n"
            f"Metrics: Score={score:.2f}, Confidence={confidence:.2f}, Historical Queries={metrics['query_count']}, "
            f"Productive Rate={metrics['productive_query_rate']:.1%}, Enquiries={metrics['enquiries']}.\n"
            f"Rules: Maximum 2 sentences. Professional B2B industrial tone. Focus on calibration demand drivers. Do not invent numbers."
        )

        # Step 1: DeepSeek Primary
        try:
            from services.llm_provider import HiveProvider
            hive = HiveProvider(model_name="deepseek-ai/DeepSeek-V4.1-Flash")
            if hive.is_available():
                resp = hive.generate_text(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.2,
                )
                if resp and len(resp.strip()) >= 10:
                    return resp.strip()
        except Exception as exc:
            logger.debug("Business Analyst DeepSeek rationale call note: %s", exc)

        # Step 2: Gemini Fallback
        try:
            from services.llm_provider import GeminiProvider
            for model_name in ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-1.5-flash"]:
                try:
                    gemini = GeminiProvider(model_name=model_name)
                    if gemini.is_available():
                        resp = gemini.generate_text(
                            messages=[{"role": "user", "content": prompt}],
                            max_tokens=100,
                            temperature=0.2,
                        )
                        if resp and len(resp.strip()) >= 10:
                            return resp.strip()
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Business Analyst Gemini rationale call note: %s", exc)

        # Step 3: Deterministic template fallback
        return deterministic_template

    # ── 7. Reporting & Operational Status ──────────────────────────────────

    def get_strategy_status(self, db: Session) -> Dict[str, Any]:
        """Return concise factual strategy status for operator and API."""
        latest = (
            db.query(BusinessAnalystDecision)
            .order_by(BusinessAnalystDecision.id.desc())
            .first()
        )

        recent = (
            db.query(BusinessAnalystDecision)
            .order_by(BusinessAnalystDecision.id.desc())
            .limit(10)
            .all()
        )

        total_decisions = db.query(func.count(BusinessAnalystDecision.id)).scalar() or 0
        total_queries = db.query(func.count(DiscoveryQueryLog.id)).scalar() or 0

        # Efficiency metrics across system
        total_strong = db.query(func.sum(DiscoveryQueryLog.strong_opportunities)).scalar() or 0
        total_persons = db.query(func.count(Company.id)).filter(Company.discovery_query_log_id.isnot(None)).scalar() or 0
        total_enquiries = db.query(func.count(Company.id)).filter(Company.order_received == True).scalar() or 0

        explore_count = sum(1 for d in recent if d.mode == "EXPLORE")
        rolling_explore_ratio = round(explore_count / max(1, len(recent)), 3)

        return {
            "status": "ACTIVE",
            "total_strategic_decisions": total_decisions,
            "total_queries_logged": total_queries,
            "rolling_exploration_ratio": rolling_explore_ratio,
            "current_strategy": latest.to_dict() if latest else None,
            "recent_decisions": [d.to_dict() for d in recent],
            "efficiency_metrics": {
                "qualified_opps_total": int(total_strong),
                "attributed_accounts_total": int(total_persons),
                "enquiries_generated_total": int(total_enquiries),
                "strong_per_query": round(int(total_strong) / max(1, total_queries), 3),
            },
            "primary_kpi": "ENQUIRIES GENERATED",
        }


business_analyst_service = BusinessAnalystService()
