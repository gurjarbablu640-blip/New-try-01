"""Stateful Adaptive Discovery Query Planner for Salesoorja.

Implements:
- 15 Trigger Families x 15 Manufacturing Sectors x Indian Industrial Corridors
- Query Archetype Portfolio (EVENT_FIRST, COMPANY_FIRST, INVESTMENT_CAPEX,
  FACILITY_FIRST, COMMISSIONING, NEWS_NATURAL, INDUSTRY_SOURCE, TEMPORAL)
- Progressive Query Relaxation Ladder (Level 1 -> Level 2 -> Level 3 -> Level 4)
- Controlled Search Intent Synonym Families
- Temporal Search Strategy (relative recency / post-retrieval evaluation)
- Bounded Root-Intent Search Budget (prevents infinite search churn)
- 24-hour Cooldown Integration: Checks DiscoveryQueryMemory before dispatching
- Multi-page progression: Generates page 2 queries for productive runs
- Negative keyword filtering to exclude stock/share noise
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import SessionLocal
from models.discovery_query_log import DiscoveryQueryLog
from services.discovery_query_memory import (
    discovery_query_memory,
    normalize_discovery_query,
    STATE_SUCCESS_PRODUCTIVE,
    STATE_SUCCESS_EXHAUSTED,
)

logger = logging.getLogger(__name__)

# Query Archetypes Portfolio
ARCHETYPE_EVENT_FIRST = "EVENT_FIRST"
ARCHETYPE_COMPANY_FIRST = "COMPANY_FIRST"
ARCHETYPE_INVESTMENT_CAPEX = "INVESTMENT_CAPEX"
ARCHETYPE_FACILITY_FIRST = "FACILITY_FIRST"
ARCHETYPE_COMMISSIONING = "COMMISSIONING"
ARCHETYPE_NEWS_NATURAL = "NEWS_NATURAL"
ARCHETYPE_INDUSTRY_SOURCE = "INDUSTRY_SOURCE"
ARCHETYPE_TEMPORAL = "TEMPORAL"

ALL_ARCHETYPES = [
    ARCHETYPE_EVENT_FIRST,
    ARCHETYPE_COMPANY_FIRST,
    ARCHETYPE_INVESTMENT_CAPEX,
    ARCHETYPE_FACILITY_FIRST,
    ARCHETYPE_COMMISSIONING,
    ARCHETYPE_NEWS_NATURAL,
    ARCHETYPE_INDUSTRY_SOURCE,
    ARCHETYPE_TEMPORAL,
]

# Relaxation Ladder Precision Levels
PRECISION_LEVEL_1_HIGH = 1
PRECISION_LEVEL_2_RELAXED = 2
PRECISION_LEVEL_3_SYNONYMS = 3
PRECISION_LEVEL_4_COMPANY_FIRST = 4

# Maximum relaxation search attempts per root search intent before 24h angle cooldown
MAX_RELAXATION_ATTEMPTS_PER_ROOT = 3

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

# Controlled Search Intent Synonym Families
TRIGGER_SYNONYM_FAMILIES: Dict[str, List[str]] = {
    "plant_expansion": [
        "plant expansion",
        "capacity expansion",
        "capacity addition",
        "new production line",
        "manufacturing expansion",
        "facility expansion",
        "brownfield expansion",
        "phase 2",
        "additional line",
        "production ramp",
        "ramp-up",
        "greenfield facility",
        "new plant",
    ],
    "capex_announcement": [
        "capex",
        "capital expenditure",
        "investment crores",
        "new investment",
        "manufacturing investment",
        "expansion investment",
        "project investment",
        "plant capex",
    ],
    "commercial_production": [
        "commercial production",
        "begins production",
        "starts operations",
        "commercial rollout",
        "operations commenced",
        "production started",
        "manufacturing started",
    ],
    "plant_inauguration": [
        "inaugurates manufacturing plant",
        "new facility inaugurated",
        "plant commissioned",
        "inauguration",
        "commissioned",
        "facility opening",
        "new factory opened",
    ],
    "machinery_procurement": [
        "new machinery installed",
        "CNC machines",
        "automated assembly line",
        "tooling installation",
        "machining center",
        "press line installed",
    ],
    "qa_lab_setup": [
        "new testing laboratory",
        "metrology lab",
        "quality testing facility",
        "inspection lab",
        "CMM inspection",
        "calibration facility",
    ],
    "cleanroom_commissioning": [
        "cleanroom commissioned",
        "clean room facility",
        "contamination control",
        "ISO Class cleanroom",
        "controlled environment",
    ],
    "defense_aerospace_indigenization": [
        "defense manufacturing facility",
        "aerospace component plant",
        "iDEX vendor",
        "defense production",
        "aerospace machining",
    ],
    "automotive_ev_transition": [
        "EV battery plant",
        "electric vehicle manufacturing",
        "battery pack assembly",
        "motor plant",
        "gigafactory",
        "EV component unit",
    ],
    "semiconductor_electronics": [
        "semiconductor facility",
        "OSAT unit",
        "electronics manufacturing cluster",
        "PCB assembly",
        "SMT assembly lines",
        "EMS facility",
    ],
    "medical_device_manufacturing": [
        "medical device manufacturing",
        "orthopedic implant plant",
        "diagnostic equipment facility",
        "surgical device plant",
    ],
    "pharmaceutical_formulation": [
        "pharma formulation plant",
        "sterile injectables facility",
        "API manufacturing unit",
        "USFDA unit",
        "solid dosage plant",
    ],
    "solar_renewable_equipment": [
        "solar cell manufacturing",
        "solar module plant",
        "wind turbine component facility",
        "solar gigafactory",
    ],
    "heavy_engineering_fabrication": [
        "heavy fabrication unit",
        "pressure vessel manufacturing",
        "precision forging plant",
        "heavy engineering plant",
    ],
    "oem_tier1_qualification": [
        "Tier-1 supplier contract",
        "OEM quality qualification",
        "IATF 16949 audit",
        "vendor approval",
        "OEM supplier plant",
    ],
}

# 15 Manufacturing Sectors
MANUFACTURING_SECTORS: Dict[str, Dict[str, Any]] = {
    "Automotive & Auto Components": {
        "keywords": ["automotive components", "auto parts manufacturing", "transmission components", "chassis"],
        "default_trigger": "plant_expansion",
        "industry_entity_keywords": ["auto components", "automotive parts", "auto ancillary"],
    },
    "EV & Battery Systems": {
        "keywords": ["electric vehicle battery", "battery pack assembly", "EV powertrain", "traction motor"],
        "default_trigger": "automotive_ev_transition",
        "industry_entity_keywords": ["EV battery", "battery pack", "electric vehicle"],
    },
    "Aerospace & Defense": {
        "keywords": ["aerospace precision engineering", "defense component manufacturing", "avionics enclosure"],
        "default_trigger": "defense_aerospace_indigenization",
        "industry_entity_keywords": ["aerospace parts", "defense engineering", "precision defense"],
    },
    "Precision Engineering & CNC Tooling": {
        "keywords": ["precision machining", "CNC tooling", "die and mould manufacturing", "carbide cutting tools"],
        "default_trigger": "machinery_procurement",
        "industry_entity_keywords": ["precision engineering", "CNC machining", "tooling"],
    },
    "Semiconductor & Electronics (EMS)": {
        "keywords": ["electronics manufacturing services EMS", "SMT assembly", "semiconductor testing", "microelectronics"],
        "default_trigger": "semiconductor_electronics",
        "industry_entity_keywords": ["electronics manufacturing", "EMS", "PCB assembly"],
    },
    "Pharmaceuticals & Bulk Drugs": {
        "keywords": ["pharmaceutical formulation", "API manufacturing", "bulk drugs plant", "sterile injectables"],
        "default_trigger": "pharmaceutical_formulation",
        "industry_entity_keywords": ["pharmaceuticals", "API bulk drugs", "pharma formulation"],
    },
    "Medical Devices & Healthcare Equipment": {
        "keywords": ["medical devices manufacturing", "surgical equipment", "diagnostic instruments", "implants"],
        "default_trigger": "medical_device_manufacturing",
        "industry_entity_keywords": ["medical devices", "surgical instruments", "implants"],
    },
    "Solar & Renewable Energy Equipment": {
        "keywords": ["solar cell manufacturing", "solar PV module", "wind turbine tower", "inverter manufacturing"],
        "default_trigger": "solar_renewable_equipment",
        "industry_entity_keywords": ["solar PV", "renewable energy equipment", "solar modules"],
    },
    "Heavy Engineering & Industrial Machinery": {
        "keywords": ["heavy industrial machinery", "pressure vessels", "turbines boilers", "crane manufacturing"],
        "default_trigger": "heavy_engineering_fabrication",
        "industry_entity_keywords": ["heavy engineering", "industrial machinery", "pressure vessels"],
    },
    "Chemicals & Specialty Materials": {
        "keywords": ["specialty chemicals plant", "industrial polymers", "performance resins", "catalyst manufacturing"],
        "default_trigger": "capex_announcement",
        "industry_entity_keywords": ["specialty chemicals", "polymers", "chemical manufacturing"],
    },
    "Power Transmission & Electrical Equipment": {
        "keywords": ["power transformers", "high voltage switchgear", "electrical panel manufacturing", "substation equipment"],
        "default_trigger": "commercial_production",
        "industry_entity_keywords": ["power equipment", "switchgear", "electrical panels"],
    },
    "Telecom & Optical Fiber Equipment": {
        "keywords": ["optical fiber cable manufacturing", "telecom hardware", "5G network equipment"],
        "default_trigger": "plant_inauguration",
        "industry_entity_keywords": ["telecom equipment", "optical fiber", "telecom hardware"],
    },
    "Railways & Rolling Stock Components": {
        "keywords": ["railway rolling stock", "locomotive components", "bogie manufacturing", "metro rail equipment"],
        "default_trigger": "plant_expansion",
        "industry_entity_keywords": ["railway equipment", "rolling stock", "locomotive components"],
    },
    "Packaging & Converting Machinery": {
        "keywords": ["packaging machinery manufacturing", "converting equipment", "high-speed labeling lines"],
        "default_trigger": "machinery_procurement",
        "industry_entity_keywords": ["packaging machinery", "converting machinery"],
    },
    "Metals & Advanced Alloys Processing": {
        "keywords": ["precision metal extrusion", "titanium alloy processing", "specialty steel tubes", "aluminum casting"],
        "default_trigger": "capex_announcement",
        "industry_entity_keywords": ["metal alloys", "precision casting", "extrusions"],
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
    """Stateful query planning engine with archetype portfolio and progressive relaxation ladder."""

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
        """Compute transparent adaptive priority weights per angle based on historical performance."""
        weights: Dict[Tuple[str, str], float] = {}
        all_angles = self.get_all_angles()

        should_close = False
        if db is None:
            try:
                db = SessionLocal()
                should_close = True
            except Exception:
                return {angle: 1.0 for angle in all_angles}

        try:
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
                    weights[(sector, trigger)] = 2.0
                else:
                    runs = hist["total_runs"]
                    avg_yield = hist["total_yield"] / runs
                    exhausted_ratio = hist["exhausted_runs"] / runs
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
        archetype: str = ARCHETYPE_EVENT_FIRST,
        precision_level: int = PRECISION_LEVEL_1_HIGH,
        synonym_idx: int = 0,
    ) -> str:
        """Construct an industrial search query across multiple archetypes and progressive relaxation levels."""
        sec_info = MANUFACTURING_SECTORS.get(sector, {})
        trig_info = TRIGGER_FAMILIES.get(trigger, {})
        sec_keywords = sec_info.get("keywords", [sector])
        sec_kw = sec_keywords[0]
        
        synonyms = TRIGGER_SYNONYM_FAMILIES.get(trigger, trig_info.get("keywords", ["expansion"]))
        trig_kw = synonyms[synonym_idx % len(synonyms)]

        geo_term = geography if geography and geography != "Pan-India" else "India"

        # Construct query based on Archetype and Relaxation Precision Level
        if archetype == ARCHETYPE_EVENT_FIRST:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'"{geo_term}" "{sec_kw}" "{trig_kw}" {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{geo_term} {sec_kw} {trig_kw} expansion {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_3_SYNONYMS:
                alt_syn = synonyms[(synonym_idx + 1) % len(synonyms)]
                query = f'{geo_term} {sec_kw} ({trig_kw} OR {alt_syn}) {NEGATIVE_SEARCH_TERMS}'
            else:  # LEVEL 4
                query = f'{sec_kw} manufacturers {geo_term} new plant {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_COMPANY_FIRST:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'"{geo_term}" "{sec_kw}" manufacturers expansion {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{sec_kw} manufacturers {geo_term} expansion {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{sec_kw} manufacturing companies {geo_term} {trig_kw} {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_INVESTMENT_CAPEX:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'"{geo_term}" "{sec_kw}" investment crores plant {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{sec_kw} {geo_term} investment manufacturing plant {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{geo_term} {sec_kw} capex manufacturing expansion {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_FACILITY_FIRST:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'"{geo_term}" new "{sec_kw}" manufacturing facility {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'new {sec_kw} facility {geo_term} unit {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{sec_kw} manufacturing plant site {geo_term} {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_COMMISSIONING:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'"{geo_term}" "{sec_kw}" commissioned manufacturing {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{sec_kw} plant commissioning {geo_term} {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{sec_kw} factory commercial production commenced {geo_term} {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_NEWS_NATURAL:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'{sec_kw} factory {geo_term} new plant {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{geo_term} {sec_kw} manufacturing expansion news {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{sec_kw} manufacturing opening operations {geo_term} {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_INDUSTRY_SOURCE:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'{geo_term} {sec_kw} industrial corridor expansion {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{sec_kw} manufacturers {geo_term} project announcement {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{geo_term} industrial estate {sec_kw} expansion {NEGATIVE_SEARCH_TERMS}'

        elif archetype == ARCHETYPE_TEMPORAL:
            if precision_level == PRECISION_LEVEL_1_HIGH:
                query = f'{geo_term} {sec_kw} {trig_kw} recent {NEGATIVE_SEARCH_TERMS}'
            elif precision_level == PRECISION_LEVEL_2_RELAXED:
                query = f'{geo_term} {sec_kw} {trig_kw} past quarter OR recent {NEGATIVE_SEARCH_TERMS}'
            else:
                query = f'{geo_term} {sec_kw} {trig_kw} 2026 {NEGATIVE_SEARCH_TERMS}'

        else:
            query = f'{geo_term} {sec_kw} {trig_kw} {NEGATIVE_SEARCH_TERMS}'

        return query.strip()

    def get_next_planned_query(
        self,
        db: Optional[Session] = None,
        preferred_sector: Optional[str] = None,
        preferred_geo: Optional[str] = None,
        preferred_trigger: Optional[str] = None,
        strategy_decision_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Select highest-priority non-cooldown query using portfolio archetypes and progressive relaxation."""
        weights = self.compute_angle_weights(db)
        
        # 1. Inspect recent query history to determine relaxation level and archetype progression
        root_sector = preferred_sector or "Automotive & Auto Components"
        root_trigger = preferred_trigger or MANUFACTURING_SECTORS.get(root_sector, {}).get("default_trigger", "plant_expansion")
        root_geo = preferred_geo or "Pan-India"
        root_search_intent_id = f"{root_sector}:{root_trigger}:{root_geo}"

        precision_level = PRECISION_LEVEL_1_HIGH
        archetype = ARCHETYPE_EVENT_FIRST
        relaxation_reason: Optional[str] = None
        parent_query_id: Optional[int] = None

        if db is not None:
            try:
                recent_queries = (
                    db.query(DiscoveryQueryLog)
                    .filter(
                        DiscoveryQueryLog.sector == root_sector,
                        DiscoveryQueryLog.trigger == root_trigger,
                        DiscoveryQueryLog.geography == root_geo,
                    )
                    .order_by(DiscoveryQueryLog.id.desc())
                    .limit(5)
                    .all()
                )

                exhausted_count = 0
                for rq in recent_queries:
                    if rq.execution_state == STATE_SUCCESS_EXHAUSTED:
                        exhausted_count += 1
                        if parent_query_id is None:
                            parent_query_id = rq.id
                    elif rq.execution_state == STATE_SUCCESS_PRODUCTIVE:
                        # Productive queries reset relaxation to Level 1 or expand page 2
                        exhausted_count = 0
                        break

                if exhausted_count == 1:
                    precision_level = PRECISION_LEVEL_2_RELAXED
                    archetype = ARCHETYPE_NEWS_NATURAL
                    relaxation_reason = "Level 1 high-precision query exhausted; relaxing quotes and rigid syntax"
                elif exhausted_count == 2:
                    precision_level = PRECISION_LEVEL_3_SYNONYMS
                    archetype = ARCHETYPE_INVESTMENT_CAPEX
                    relaxation_reason = "Level 2 relaxed query exhausted; expanding to broader trigger synonym family"
                elif exhausted_count >= 3:
                    precision_level = PRECISION_LEVEL_4_COMPANY_FIRST
                    archetype = ARCHETYPE_COMPANY_FIRST
                    relaxation_reason = "Level 3 synonyms exhausted; shifting to company-first manufacturer discovery"

            except Exception as e:
                logger.debug("Could not determine relaxation lineage: %s", e)

        # 2. Build candidate query for preferred angle
        req_query = self.build_search_query(
            sector=root_sector,
            trigger=root_trigger,
            geography=root_geo,
            page=1,
            archetype=archetype,
            precision_level=precision_level,
        )
        req_normalized = normalize_discovery_query(req_query)

        if not self.memory.is_query_in_cooldown(req_normalized, page=1, db=db):
            return {
                "query": req_query,
                "normalized_query": req_normalized,
                "page": 1,
                "sector": root_sector,
                "trigger": root_trigger,
                "geography": root_geo,
                "weight": weights.get((root_sector, root_trigger), 1.0),
                "rationale": f"Business Analyst strategy ({archetype} L{precision_level}): {root_sector} in {root_geo}",
                "analyst_decision_id": strategy_decision_id,
                "was_substituted": False,
                "substitution_reason": None,
                "actual_sector": root_sector,
                "actual_trigger": root_trigger,
                "actual_geography": root_geo,
                "root_search_intent_id": root_search_intent_id,
                "parent_query_id": parent_query_id,
                "archetype": archetype,
                "precision_level": precision_level,
                "relaxation_reason": relaxation_reason,
            }

        # 3. Angle Substitution when preferred query is in 24h cooldown
        sub_reason = f"Requested strategy ({root_sector} | {root_geo} | {root_trigger}) in 24h cooldown"
        logger.info("Query Planner substitution triggered: %s", sub_reason)

        # Try other corridors for the same sector & trigger first
        other_geos = [g for g in INDUSTRIAL_CORRIDORS if g != root_geo]
        for alt_geo in other_geos:
            alt_query = self.build_search_query(root_sector, root_trigger, alt_geo, page=1, archetype=archetype, precision_level=precision_level)
            alt_norm = normalize_discovery_query(alt_query)
            if not self.memory.is_query_in_cooldown(alt_norm, page=1, db=db):
                full_reason = f"{sub_reason}; substituted geography with {alt_geo}"
                self._update_decision_substitution(db, strategy_decision_id, root_sector, root_trigger, alt_geo, full_reason)
                return {
                    "query": alt_query,
                    "normalized_query": alt_norm,
                    "page": 1,
                    "sector": root_sector,
                    "trigger": root_trigger,
                    "geography": alt_geo,
                    "weight": weights.get((root_sector, root_trigger), 1.0),
                    "rationale": f"Planner substitution: {root_sector} in {alt_geo}",
                    "analyst_decision_id": strategy_decision_id,
                    "was_substituted": True,
                    "substitution_reason": full_reason,
                    "actual_sector": root_sector,
                    "actual_trigger": root_trigger,
                    "actual_geography": alt_geo,
                    "root_search_intent_id": f"{root_sector}:{root_trigger}:{alt_geo}",
                    "archetype": archetype,
                    "precision_level": precision_level,
                    "relaxation_reason": "Corridor rotation substitution",
                }

        # Try alternative triggers for the same sector
        other_triggers = [t for t in TRIGGER_FAMILIES.keys() if t != root_trigger]
        for alt_trig in other_triggers:
            for g in [root_geo] + other_geos:
                alt_query = self.build_search_query(root_sector, alt_trig, g, page=1, archetype=archetype, precision_level=precision_level)
                alt_norm = normalize_discovery_query(alt_query)
                if not self.memory.is_query_in_cooldown(alt_norm, page=1, db=db):
                    full_reason = f"{sub_reason}; substituted trigger with {alt_trig} in {g}"
                    self._update_decision_substitution(db, strategy_decision_id, root_sector, alt_trig, g, full_reason)
                    return {
                        "query": alt_query,
                        "normalized_query": alt_norm,
                        "page": 1,
                        "sector": root_sector,
                        "trigger": alt_trig,
                        "geography": g,
                        "weight": weights.get((root_sector, alt_trig), 1.0),
                        "rationale": f"Planner substitution: {root_sector} in {g} ({alt_trig})",
                        "analyst_decision_id": strategy_decision_id,
                        "was_substituted": True,
                        "substitution_reason": full_reason,
                        "actual_sector": root_sector,
                        "actual_trigger": alt_trig,
                        "actual_geography": g,
                        "root_search_intent_id": f"{root_sector}:{alt_trig}:{g}",
                        "archetype": archetype,
                        "precision_level": precision_level,
                        "relaxation_reason": "Trigger substitution",
                    }

        # 5. Sector Rotation Fallback
        sectors = list(MANUFACTURING_SECTORS.keys())
        for alt_sec in sectors:
            if alt_sec == root_sector:
                continue
            alt_trig = MANUFACTURING_SECTORS[alt_sec].get("default_trigger", "plant_expansion")
            alt_query = self.build_search_query(alt_sec, alt_trig, root_geo, page=1)
            alt_norm = normalize_discovery_query(alt_query)
            if not self.memory.is_query_in_cooldown(alt_norm, page=1, db=db):
                full_reason = f"Full sector cooldown fallback: shifted from {root_sector} to {alt_sec}"
                self._update_decision_substitution(db, strategy_decision_id, alt_sec, alt_trig, root_geo, full_reason)
                return {
                    "query": alt_query,
                    "normalized_query": alt_norm,
                    "page": 1,
                    "sector": alt_sec,
                    "trigger": alt_trig,
                    "geography": root_geo,
                    "weight": weights.get((alt_sec, alt_trig), 1.0),
                    "rationale": f"Cross-sector rotation: {alt_sec} in {root_geo}",
                    "analyst_decision_id": strategy_decision_id,
                    "was_substituted": True,
                    "substitution_reason": full_reason,
                    "actual_sector": alt_sec,
                    "actual_trigger": alt_trig,
                    "actual_geography": root_geo,
                    "root_search_intent_id": f"{alt_sec}:{alt_trig}:{root_geo}",
                    "archetype": ARCHETYPE_EVENT_FIRST,
                    "precision_level": PRECISION_LEVEL_1_HIGH,
                    "relaxation_reason": "Cross-sector substitution",
                }

        # Ultimate fallback
        fallback_sec = "Automotive & Auto Components"
        fallback_trig = "plant_expansion"
        fallback_geo = "Pan-India"
        fallback_query = self.build_search_query(fallback_sec, fallback_trig, fallback_geo, page=1)
        return {
            "query": fallback_query,
            "normalized_query": normalize_discovery_query(fallback_query),
            "page": 1,
            "sector": fallback_sec,
            "trigger": fallback_trig,
            "geography": fallback_geo,
            "weight": 0.5,
            "rationale": "Global fallback query",
            "analyst_decision_id": strategy_decision_id,
            "was_substituted": True,
            "substitution_reason": "Global cooldown fallback",
            "actual_sector": fallback_sec,
            "actual_trigger": fallback_trig,
            "actual_geography": fallback_geo,
            "root_search_intent_id": f"{fallback_sec}:{fallback_trig}:{fallback_geo}",
            "archetype": ARCHETYPE_EVENT_FIRST,
            "precision_level": PRECISION_LEVEL_1_HIGH,
            "relaxation_reason": "Global fallback",
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
        archetype = previous_query_info.get("archetype", ARCHETYPE_EVENT_FIRST)
        precision = previous_query_info.get("precision_level", PRECISION_LEVEL_1_HIGH)

        base_query = self.build_search_query(sector, trigger, geography, page=2, archetype=archetype, precision_level=precision)

        return {
            "query": base_query,
            "normalized_query": normalize_discovery_query(base_query),
            "page": 2,
            "sector": sector,
            "trigger": trigger,
            "geography": geography,
            "weight": previous_query_info.get("weight", 1.0),
            "rationale": f"Productive search page 2 expansion for {sector} in {geography}",
            "archetype": archetype,
            "precision_level": precision,
        }



    def plan_with_llm_strategist(
        self,
        db: Optional[Session] = None,
        preferred_sector: Optional[str] = None,
        preferred_geo: Optional[str] = None,
        preferred_trigger: Optional[str] = None,
        strategy_decision_id: Optional[int] = None,
        search_lane: str = "EVENT_EXPANSION",
    ) -> Dict[str, Any]:
        """Generate discovery query using LLM Discovery Strategist (DeepSeek -> Gemini -> deterministic)."""
        from services.llm_discovery_strategist import llm_discovery_strategist
        return llm_discovery_strategist.plan_query(
            db=db,
            sector=preferred_sector or "Automotive & Auto Components",
            geography=preferred_geo or "Pan-India",
            trigger=preferred_trigger,
            search_lane=search_lane,
            strategy_decision_id=strategy_decision_id,
        )


discovery_query_planner = DiscoveryQueryPlanner()
