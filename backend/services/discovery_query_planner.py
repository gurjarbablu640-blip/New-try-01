"""Stateful Adaptive Discovery Query Planner for Salesoorja.

Implements:
- 15 Trigger Families x 15 Manufacturing Sectors x Indian Industrial Corridors
- Adaptive Angle Weighting (Amendment 7): Historical yields from PostgreSQL
  modestly boost high-yield angles and penalize repeatedly exhausted angles.
- Exploration guarantee: Unsearched angles receive an exploration bonus.
- 24-hour Cooldown Integration: Checks DiscoveryQueryMemory before dispatching.
- Multi-page progression: Generates page 2 queries for productive runs.
- Negative keyword filtering to exclude stock/share noise.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import case, func

from database import SessionLocal
from models.discovery_query_log import DiscoveryQueryLog
from services.discovery_query_memory import (
    discovery_query_memory,
    normalize_discovery_query,
    STATE_SUCCESS_PRODUCTIVE,
    STATE_SUCCESS_EXHAUSTED,
)

logger = logging.getLogger(__name__)

# 15 Trigger Families
TRIGGER_FAMILIES: Dict[str, Dict[str, Any]] = {
    "plant_expansion": {
        "name": "Plant & Facility Expansion",
        "keywords": ["plant expansion", "factory expansion", "new facility", "capacity expansion"],
        "icp_boost": 20,
    },
    "capex_announcement": {
        "name": "CAPEX & Capital Investment",
        "keywords": ["capex", "capital expenditure", "investment crores", "new production line"],
        "icp_boost": 18,
    },
    "commercial_production": {
        "name": "Commercial Production Launch",
        "keywords": ["commercial production", "begins production", "starts operations", "commercial rollout"],
        "icp_boost": 22,
    },
    "plant_inauguration": {
        "name": "Plant Inauguration & Commissioning",
        "keywords": ["inaugurates manufacturing plant", "new facility inaugurated", "plant commissioned", "inauguration"],
        "icp_boost": 24,
    },
    "machinery_procurement": {
        "name": "Advanced Machinery Procurement",
        "keywords": ["new machinery installed", "CNC machines", "automated assembly line", "tooling installation"],
        "icp_boost": 16,
    },
    "qa_lab_setup": {
        "name": "Quality & Testing Lab Setup",
        "keywords": ["new testing laboratory", "metrology lab", "quality testing facility", "inspection lab"],
        "icp_boost": 25,
    },
    "cleanroom_commissioning": {
        "name": "Cleanroom & Controlled Environment",
        "keywords": ["cleanroom commissioned", "clean room facility", "contamination control", "ISO Class cleanroom"],
        "icp_boost": 22,
    },
    "defense_aerospace_indigenization": {
        "name": "Aerospace & Defense Indigenization",
        "keywords": ["defense manufacturing facility", "aerospace component plant", "iDEX vendor", "defense production"],
        "icp_boost": 26,
    },
    "automotive_ev_transition": {
        "name": "EV & High-Voltage Battery Systems",
        "keywords": ["EV battery plant", "electric vehicle manufacturing", "battery pack assembly", "motor plant"],
        "icp_boost": 24,
    },
    "semiconductor_electronics": {
        "name": "Semiconductor & OSAT Electronics",
        "keywords": ["semiconductor facility", "OSAT unit", "electronics manufacturing cluster", "PCB assembly"],
        "icp_boost": 25,
    },
    "medical_device_manufacturing": {
        "name": "Medical Devices & Implant Manufacturing",
        "keywords": ["medical device manufacturing", "orthopedic implant plant", "diagnostic equipment facility"],
        "icp_boost": 22,
    },
    "pharmaceutical_formulation": {
        "name": "Pharmaceutical & Sterile Injectables",
        "keywords": ["pharma formulation plant", "sterile injectables facility", "API manufacturing unit", "USFDA unit"],
        "icp_boost": 20,
    },
    "solar_renewable_equipment": {
        "name": "Solar & Renewable Equipment",
        "keywords": ["solar cell manufacturing", "solar module plant", "wind turbine component facility"],
        "icp_boost": 18,
    },
    "heavy_engineering_fabrication": {
        "name": "Heavy Engineering & Precision Forging",
        "keywords": ["heavy fabrication unit", "pressure vessel manufacturing", "precision forging plant"],
        "icp_boost": 17,
    },
    "oem_tier1_qualification": {
        "name": "OEM Tier-1 Qualification & Audit",
        "keywords": ["Tier-1 supplier contract", "OEM quality qualification", "IATF 16949 audit", "vendor approval"],
        "icp_boost": 22,
    },
}

# 15 Manufacturing Sectors
MANUFACTURING_SECTORS: Dict[str, Dict[str, Any]] = {
    "Automotive & Auto Components": {
        "keywords": ["automotive components", "auto parts manufacturing", "transmission components", "chassis"],
        "default_trigger": "plant_expansion",
    },
    "EV & Battery Systems": {
        "keywords": ["electric vehicle battery", "battery pack assembly", "EV powertrain", "traction motor"],
        "default_trigger": "automotive_ev_transition",
    },
    "Aerospace & Defense": {
        "keywords": ["aerospace precision engineering", "defense component manufacturing", "avionics enclosure"],
        "default_trigger": "defense_aerospace_indigenization",
    },
    "Precision Engineering & CNC Tooling": {
        "keywords": ["precision machining", "CNC tooling", "die and mould manufacturing", "carbide cutting tools"],
        "default_trigger": "machinery_procurement",
    },
    "Semiconductor & Electronics (EMS)": {
        "keywords": ["electronics manufacturing services EMS", "SMT assembly", "semiconductor testing", "microelectronics"],
        "default_trigger": "semiconductor_electronics",
    },
    "Pharmaceuticals & Bulk Drugs": {
        "keywords": ["pharmaceutical formulation", "API manufacturing", "bulk drugs plant", "sterile injectables"],
        "default_trigger": "pharmaceutical_formulation",
    },
    "Medical Devices & Healthcare Equipment": {
        "keywords": ["medical devices manufacturing", "surgical equipment", "diagnostic instruments", "implants"],
        "default_trigger": "medical_device_manufacturing",
    },
    "Solar & Renewable Energy Equipment": {
        "keywords": ["solar cell manufacturing", "solar PV module", "wind turbine tower", "inverter manufacturing"],
        "default_trigger": "solar_renewable_equipment",
    },
    "Heavy Engineering & Industrial Machinery": {
        "keywords": ["heavy industrial machinery", "pressure vessels", "turbines boilers", "crane manufacturing"],
        "default_trigger": "heavy_engineering_fabrication",
    },
    "Chemicals & Specialty Materials": {
        "keywords": ["specialty chemicals plant", "industrial polymers", "performance resins", "catalyst manufacturing"],
        "default_trigger": "capex_announcement",
    },
    "Power Transmission & Electrical Equipment": {
        "keywords": ["power transformers", "high voltage switchgear", "electrical panel manufacturing", "substation equipment"],
        "default_trigger": "commercial_production",
    },
    "Telecom & Optical Fiber Equipment": {
        "keywords": ["optical fiber cable manufacturing", "telecom hardware", "5G network equipment"],
        "default_trigger": "plant_inauguration",
    },
    "Railways & Rolling Stock Components": {
        "keywords": ["railway rolling stock", "locomotive components", "bogie manufacturing", "metro rail equipment"],
        "default_trigger": "plant_expansion",
    },
    "Packaging & Converting Machinery": {
        "keywords": ["packaging machinery manufacturing", "converting equipment", "high-speed labeling lines"],
        "default_trigger": "machinery_procurement",
    },
    "Metals & Advanced Alloys Processing": {
        "keywords": ["precision metal extrusion", "titanium alloy processing", "specialty steel tubes", "aluminum casting"],
        "default_trigger": "capex_announcement",
    },
}

# Corridors / Geographies
INDUSTRIAL_CORRIDORS: List[str] = [
    "Gujarat",
    "Maharashtra",
    "Tamil Nadu",
    "Karnataka",
    "Haryana",
    "Telangana",
    "Andhra Pradesh",
    "Rajasthan",
    "Madhya Pradesh",
    "Pan-India",
]

NEGATIVE_SEARCH_TERMS = "-stock -share -brokerage -screener -dividend -trading -equity -sensex -nifty"


class DiscoveryQueryPlanner:
    """Stateful query planning engine with adaptive yield weighting."""

    def __init__(self, memory=None):
        self.memory = memory or discovery_query_memory

    def get_all_angles(self) -> List[Tuple[str, str]]:
        """Return all sector x trigger combinations (15 x 15 = 225 angles), interleaved across sectors."""
        angles = []
        for trigger in TRIGGER_FAMILIES.keys():
            for sector in MANUFACTURING_SECTORS.keys():
                angles.append((sector, trigger))
        return angles

    def compute_angle_weights(self, db: Optional[Session] = None) -> Dict[Tuple[str, str], float]:
        """Compute transparent adaptive priority weights per angle based on historical performance (Amendment 7).

        Formula:
        - Base weight = 1.0
        - Never-searched angle (0 runs in DB) = 2.0 (exploration opportunity)
        - Historical runs:
            avg_yield = sum(yield_score) / total_runs
            exhausted_ratio = count(SUCCESS_EXHAUSTED) / total_runs
            weight = max(0.2, 1.0 + (0.5 * avg_yield) - (0.4 * exhausted_ratio))
        """
        weights: Dict[Tuple[str, str], float] = {}
        all_angles = self.get_all_angles()

        should_close = False
        if db is None:
            try:
                db = SessionLocal()
                should_close = True
            except Exception:
                # Default uniform exploration weights if DB unavailable
                return {angle: 1.0 for angle in all_angles}

        try:
            # Query aggregated historical performance by sector and trigger
            stats = (
                db.query(
                    DiscoveryQueryLog.sector,
                    DiscoveryQueryLog.trigger,
                    func.count(DiscoveryQueryLog.id).label("total_runs"),
                    func.sum(DiscoveryQueryLog.yield_score).label("total_yield"),
                    func.sum(
                        case(
                            (DiscoveryQueryLog.execution_state == STATE_SUCCESS_EXHAUSTED, 1),
                            else_=0,
                        )
                    ).label("exhausted_runs"),
                )
                .group_by(DiscoveryQueryLog.sector, DiscoveryQueryLog.trigger)
                .all()
            )

            stats_map = {}
            for row in stats:
                stats_map[(row.sector, row.trigger)] = {
                    "total_runs": int(row.total_runs or 0),
                    "total_yield": float(row.total_yield or 0.0),
                    "exhausted_runs": int(row.exhausted_runs or 0),
                }

            for sector, trigger in all_angles:
                hist = stats_map.get((sector, trigger))
                if not hist or hist["total_runs"] == 0:
                    # Never-searched angle: exploration boost
                    weights[(sector, trigger)] = 2.0
                else:
                    runs = hist["total_runs"]
                    avg_yield = hist["total_yield"] / runs
                    exhausted_ratio = hist["exhausted_runs"] / runs
                    # Adaptive weight calculation
                    score = 1.0 + (0.5 * avg_yield) - (0.4 * exhausted_ratio)
                    weights[(sector, trigger)] = round(max(0.2, score), 3)

            return weights
        except Exception as exc:
            logger.warning("Error computing adaptive angle weights: %s", exc)
            return {angle: 1.0 for angle in all_angles}
        finally:
            if should_close and db is not None:
                db.close()

    def build_search_query(
        self,
        sector: str,
        trigger: str,
        geography: str,
        page: int = 1,
    ) -> str:
        """Construct a focused, boolean industrial search query."""
        sec_info = MANUFACTURING_SECTORS.get(sector, {})
        trig_info = TRIGGER_FAMILIES.get(trigger, {})

        sec_kw = sec_info.get("keywords", [sector])[0]
        trig_kw = trig_info.get("keywords", ["expansion"])[0]

        geo_term = f'"{geography}"' if geography and geography != "Pan-India" else "India"

        # Construct concise boolean query targeting 2026 manufacturing milestones
        query = f'{geo_term} "{sec_kw}" "{trig_kw}" manufacturing 2026 {NEGATIVE_SEARCH_TERMS}'
        return query.strip()

    def get_next_planned_query(
        self,
        db: Optional[Session] = None,
        preferred_sector: Optional[str] = None,
        preferred_geo: Optional[str] = None,
        preferred_trigger: Optional[str] = None,
        strategy_decision_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Select the highest-priority non-cooldown query using adaptive weighting.

        If a preferred strategic angle (from Business Analyst) is in 24h cooldown,
        authoritatively substitutes nearest available angle and records substitution telemetry.

        Returns:
            {
                "query": str,
                "normalized_query": str,
                "page": int,
                "sector": str,
                "trigger": str,
                "geography": str,
                "weight": float,
                "rationale": str,
                "analyst_decision_id": Optional[int],
                "was_substituted": bool,
                "substitution_reason": Optional[str],
                "actual_sector": str,
                "actual_trigger": str,
                "actual_geography": str,
            }
        """
        weights = self.compute_angle_weights(db)

        # 1. Check if specific preferred angle was requested by Business Analyst
        if preferred_sector and preferred_sector in MANUFACTURING_SECTORS:
            req_trigger = preferred_trigger or MANUFACTURING_SECTORS[preferred_sector].get("default_trigger", "plant_expansion")
            req_geo = preferred_geo or "Pan-India"

            req_query = self.build_search_query(preferred_sector, req_trigger, req_geo, page=1)
            req_normalized = normalize_discovery_query(req_query)

            if not self.memory.is_query_in_cooldown(req_normalized, page=1, db=db):
                # Preferred strategy is directly available!
                return {
                    "query": req_query,
                    "normalized_query": req_normalized,
                    "page": 1,
                    "sector": preferred_sector,
                    "trigger": req_trigger,
                    "geography": req_geo,
                    "weight": weights.get((preferred_sector, req_trigger), 1.0),
                    "rationale": f"Business Analyst strategy: {preferred_sector} in {req_geo} ({req_trigger})",
                    "analyst_decision_id": strategy_decision_id,
                    "was_substituted": False,
                    "substitution_reason": None,
                    "actual_sector": preferred_sector,
                    "actual_trigger": req_trigger,
                    "actual_geography": req_geo,
                }
            else:
                # Preferred angle is in 24h cooldown -> Query Planner performs authoritative substitution
                sub_reason = f"Requested strategy ({preferred_sector} | {req_geo} | {req_trigger}) in 24h cooldown"
                logger.info("Query Planner substitution triggered: %s", sub_reason)

                # Try other corridors for the same sector & trigger first
                other_geos = [g for g in INDUSTRIAL_CORRIDORS if g != req_geo]
                for alt_geo in other_geos:
                    alt_query = self.build_search_query(preferred_sector, req_trigger, alt_geo, page=1)
                    alt_normalized = normalize_discovery_query(alt_query)
                    if not self.memory.is_query_in_cooldown(alt_normalized, page=1, db=db):
                        full_reason = f"{sub_reason}; substituted geography with {alt_geo}"
                        self._update_decision_substitution(db, strategy_decision_id, preferred_sector, req_trigger, alt_geo, full_reason)
                        return {
                            "query": alt_query,
                            "normalized_query": alt_normalized,
                            "page": 1,
                            "sector": preferred_sector,
                            "trigger": req_trigger,
                            "geography": alt_geo,
                            "weight": weights.get((preferred_sector, req_trigger), 1.0),
                            "rationale": f"Planner substitution: {preferred_sector} in {alt_geo}",
                            "analyst_decision_id": strategy_decision_id,
                            "was_substituted": True,
                            "substitution_reason": full_reason,
                            "actual_sector": preferred_sector,
                            "actual_trigger": req_trigger,
                            "actual_geography": alt_geo,
                        }

                # Try alternative triggers for the same sector
                other_triggers = [t for t in TRIGGER_FAMILIES.keys() if t != req_trigger]
                for alt_trig in other_triggers:
                    for g in [req_geo] + other_geos:
                        alt_query = self.build_search_query(preferred_sector, alt_trig, g, page=1)
                        alt_normalized = normalize_discovery_query(alt_query)
                        if not self.memory.is_query_in_cooldown(alt_normalized, page=1, db=db):
                            full_reason = f"{sub_reason}; substituted trigger with {alt_trig} in {g}"
                            self._update_decision_substitution(db, strategy_decision_id, preferred_sector, alt_trig, g, full_reason)
                            return {
                                "query": alt_query,
                                "normalized_query": alt_normalized,
                                "page": 1,
                                "sector": preferred_sector,
                                "trigger": alt_trig,
                                "geography": g,
                                "weight": weights.get((preferred_sector, alt_trig), 1.0),
                                "rationale": f"Planner substitution: {preferred_sector} in {g} ({alt_trig})",
                                "analyst_decision_id": strategy_decision_id,
                                "was_substituted": True,
                                "substitution_reason": full_reason,
                                "actual_sector": preferred_sector,
                                "actual_trigger": alt_trig,
                                "actual_geography": g,
                            }

        # 2. General non-preferred search or cross-sector fallback
        sectors = list(MANUFACTURING_SECTORS.keys())
        start_idx = 0
        if db is not None and not preferred_sector:
            try:
                last_log = (
                    db.query(DiscoveryQueryLog.sector)
                    .filter(DiscoveryQueryLog.sector.isnot(None))
                    .order_by(DiscoveryQueryLog.id.desc())
                    .first()
                )
                if last_log and last_log[0] in sectors:
                    last_idx = sectors.index(last_log[0])
                    start_idx = (last_idx + 1) % len(sectors)
            except Exception as e:
                logger.debug("Could not inspect last sector from DB: %s", e)

        active_sectors = (
            [preferred_sector]
            if (preferred_sector and preferred_sector in MANUFACTURING_SECTORS)
            else (sectors[start_idx:] + sectors[:start_idx])
        )

        candidate_angles: List[Tuple[str, str]] = []
        for sector in active_sectors:
            sec_angles = [(sector, trig) for trig in TRIGGER_FAMILIES.keys()]
            sec_angles.sort(key=lambda a: weights.get(a, 1.0), reverse=True)
            candidate_angles.extend(sec_angles)

        geos = [preferred_geo] if preferred_geo else INDUSTRIAL_CORRIDORS

        for sector, trigger in candidate_angles:
            weight = weights.get((sector, trigger), 1.0)
            for geo in geos:
                query_str = self.build_search_query(sector, trigger, geo, page=1)
                normalized = normalize_discovery_query(query_str)

                if not self.memory.is_query_in_cooldown(normalized, page=1, db=db):
                    rationale = (
                        f"Exploration angle (never searched)"
                        if weight >= 2.0
                        else f"Adaptive yield score: {weight:.2f}"
                    )
                    was_sub = bool(preferred_sector and sector != preferred_sector)
                    sub_r = f"Preferred sector {preferred_sector} cooled down; substituted with {sector}" if was_sub else None
                    if was_sub:
                        self._update_decision_substitution(db, strategy_decision_id, sector, trigger, geo, sub_r)

                    return {
                        "query": query_str,
                        "normalized_query": normalized,
                        "page": 1,
                        "sector": sector,
                        "trigger": trigger,
                        "geography": geo,
                        "weight": weight,
                        "rationale": rationale,
                        "analyst_decision_id": strategy_decision_id,
                        "was_substituted": was_sub,
                        "substitution_reason": sub_r,
                        "actual_sector": sector,
                        "actual_trigger": trigger,
                        "actual_geography": geo,
                    }

        # Fallback angle if entire corridor is cooled down
        fallback_sec = preferred_sector or "Automotive & Auto Components"
        fallback_trig = "plant_expansion"
        fallback_geo = preferred_geo or "Pan-India"
        fallback_query = self.build_search_query(fallback_sec, fallback_trig, fallback_geo, page=1)

        return {
            "query": fallback_query,
            "normalized_query": normalize_discovery_query(fallback_query),
            "page": 1,
            "sector": fallback_sec,
            "trigger": fallback_trig,
            "geography": fallback_geo,
            "weight": 0.5,
            "rationale": "Fallback angle (cooldown rotation exhausted)",
            "analyst_decision_id": strategy_decision_id,
            "was_substituted": bool(strategy_decision_id is not None),
            "substitution_reason": "Full rotation cooldown fallback",
            "actual_sector": fallback_sec,
            "actual_trigger": fallback_trig,
            "actual_geography": fallback_geo,
        }

    def _update_decision_substitution(
        self,
        db: Optional[Session],
        decision_id: Optional[int],
        actual_sec: str,
        actual_trig: str,
        actual_geo: str,
        reason: Optional[str],
    ) -> None:
        """Update BusinessAnalystDecision record in DB when Query Planner performs substitution."""
        if not db or not decision_id:
            return
        try:
            from models.business_analyst_decision import BusinessAnalystDecision
            dec = db.query(BusinessAnalystDecision).filter(BusinessAnalystDecision.id == decision_id).first()
            if dec:
                dec.was_substituted = True
                dec.substitution_reason = reason
                dec.actual_sector = actual_sec
                dec.actual_trigger = actual_trig
                dec.actual_geography = actual_geo
                db.commit()
        except Exception as exc:
            logger.debug("Could not record decision substitution in DB: %s", exc)


    def get_page_2_query(self, previous_query_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate page 2 query for an opportunity-productive search."""
        sector = previous_query_info.get("sector", "Automotive & Auto Components")
        trigger = previous_query_info.get("trigger", "plant_expansion")
        geography = previous_query_info.get("geography", "Pan-India")

        base_query = previous_query_info.get("query", "")
        if not base_query:
            base_query = self.build_search_query(sector, trigger, geography, page=2)

        return {
            "query": base_query,
            "normalized_query": normalize_discovery_query(base_query),
            "page": 2,
            "sector": sector,
            "trigger": trigger,
            "geography": geography,
            "weight": previous_query_info.get("weight", 1.0),
            "rationale": f"Productive search page 2 expansion for {sector} in {geography}",
        }


discovery_query_planner = DiscoveryQueryPlanner()
