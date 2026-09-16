"""Structured Evidence Extraction Service for Page Content.

Extracts grounded factual entities from article text:
- Company and canonical company name
- Facility name, facility type, city, state, industrial cluster
- Event type (plant expansion, commissioning, capex, lab setup, etc.)
- Dates: Publication date, actual event date, expected commissioning date
- Investment amount (e.g. ₹X Cr, million, crore)
- Calibration and metrology relevance indicators
- Supporting text snippets and confidence scores
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from services.entity_truth_gate import INDIAN_CITIES, INDIAN_STATES, validate_company_entity
from services.trigger_discovery_service import extract_event_date, evaluate_event_semantics

logger = logging.getLogger(__name__)

# Industrial and Manufacturing Equipment Keywords for Calibration Relevance
CALIBRATION_INDICATORS = {
    "cmm": "Coordinate Measuring Machine (CMM) dimensional verification",
    "cnc": "High-precision multi-axis CNC machining accuracy",
    "metrology": "Dimensional metrology and surface roughness inspection",
    "cleanroom": "Cleanroom particulate and laminar flow validation",
    "calibration": "Mandatory periodic instrument calibration",
    "load cell": "Tensile load cell and universal testing calibration",
    "pressure transmitter": "High-pressure transmitter and sensor calibration",
    "environmental chamber": "Thermal / humidity environmental chamber mapping",
    "spectrometer": "Optical emission spectrometer chemical composition testing",
    "torque": "Digital torque wrench and transducer calibration",
    "hardness": "Rockwell / Brinell / Vickers hardness tester verification",
}

INVESTMENT_PATTERNS = [
    r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(?:cr(?:ore)?s?)",
    r"([\d,]+(?:\.\d+)?)\s*(?:crore|cr)\s*(?:rupees|investment|capex|project)",
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(?:million|billion|mn|bn)",
]


def extract_investment_amount(text: str) -> Optional[str]:
    """Extract investment or capex figure from text."""
    for pat in INVESTMENT_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if "million" in m.group(0).lower() or "$" in m.group(0):
                return f"${val} Million"
            return f"₹{val} crore"
    return None


def extract_facility_and_geography(text: str, candidate_company: str = "") -> Dict[str, Any]:
    """Extract physical facility name, city, and state from article body."""
    found_city = None
    found_state = None
    facility_name = None

    # Search for Indian cities
    for city in sorted(INDIAN_CITIES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(city) + r"\b", text, re.IGNORECASE) and not found_city:
            found_city = city.title()
            break

    # Search for Indian states
    for state in INDIAN_STATES:
        if re.search(r"\b" + re.escape(state) + r"\b", text, re.IGNORECASE) and not found_state:
            found_state = state.title()
            break

    # Extract facility name pattern
    fac_match = re.search(
        r"([A-Za-z0-9\s]+(?:facility|plant|manufacturing unit|assembly line|fab|works|park))",
        text,
        re.IGNORECASE,
    )
    if fac_match:
        cand_fac = fac_match.group(1).strip()
        if len(cand_fac) < 60 and not any(w in cand_fac.lower() for w in ("new", "the", "a", "this")):
            facility_name = cand_fac

    return {
        "facility_name": facility_name or (f"{candidate_company} {found_city} Facility" if (candidate_company and found_city) else "UNKNOWN"),
        "city": found_city or "UNKNOWN",
        "state": found_state or "UNKNOWN",
        "linkage_confidence": "DIRECT" if (found_city and facility_name) else ("STRONG" if found_city else "UNKNOWN"),
    }


def extract_calibration_relevance(text: str) -> List[Dict[str, str]]:
    """Identify equipment, processes, and measurement systems requiring calibration."""
    indicators = []
    text_lower = text.lower()
    for kw, description in CALIBRATION_INDICATORS.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
            # Find surrounding snippet
            match = re.search(r"([^.\n]*?" + re.escape(kw) + r"[^.\n]*)", text_lower)
            snippet = match.group(1).strip() if match else description
            indicators.append({
                "keyword": kw,
                "demand_type": description,
                "supporting_text": snippet[:150],
            })
    return indicators


def is_valid_event_date(date_str: str) -> bool:
    """Validate that a date string is not a footer, copyright, or generic crawl year."""
    if not date_str:
        return False
    lower = date_str.lower().strip()
    if any(bp in lower for bp in ("copyright", "all rights reserved", "updated", "terms", "privacy", "crawl")):
        return False
    # Check for YYYY-MM-DD
    if re.search(r"\b202[0-9]-[01][0-9]-[0-3][0-9]\b", date_str):
        return True
    # Check for Month YYYY or DD Month YYYY
    if re.search(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+202[0-9]\b", lower):
        return True
    return False


def extract_structured_evidence(
    text: str = "",
    title: str = "",
    url: str = "",
    publication_date: str = "",
    candidate_company: str = "",
    source_type: str = "SECONDARY",
    article_text: str = "",
) -> Dict[str, Any]:
    """Extract complete structured factual evidence from fetched article text."""
    body_text = text or article_text or ""
    # 1. Geographic & Facility extraction
    geo_fac = extract_facility_and_geography(body_text, candidate_company=candidate_company)

    # 2. Date extraction: distinguish publication date, event date, future date
    event_date_res = extract_event_date(body_text, title=title, url=url)
    event_date = event_date_res.get("event_date", "UNKNOWN_DATE")
    is_future = event_date_res.get("is_future_planned_milestone", False)
    recency_tier = event_date_res.get("recency_tier", "DATE_UNKNOWN")

    # 3. Semantics and Event Type
    semantics = evaluate_event_semantics(body_text[:2000], title=title)
    event_type = semantics.get("trigger_type", "UNKNOWN")

    # 4. Investment Amount
    investment = extract_investment_amount(body_text)

    # 5. Calibration Relevance Indicators
    cal_indicators = extract_calibration_relevance(body_text)

    # 6. Company validation - Check action verbs first so subject entity precedes the verb
    company_name = candidate_company
    if not company_name and title:
        m = re.split(
            r"\b(commences|commenced|announces|announced|to invest|invests|inaugurates|inaugurated|signs|signed|sets up|sets|expands|expanded|commissions|commissioned|starts|started|plans|planned)\b",
            title,
            flags=re.I,
        )
        if m and len(m) > 1:
            cand = m[0].strip()
            if not cand.lower().startswith(("rs", "inr", "₹", "in ")):
                is_valid, _ = validate_company_entity(cand, title)
                if is_valid:
                    company_name = cand

        if not company_name:
            from services.entity_truth_gate import extract_clean_company_name_from_title
            extracted_cand = extract_clean_company_name_from_title(title)
            if extracted_cand and not extracted_cand.lower().startswith(("rs", "inr", "₹")):
                is_valid, _ = validate_company_entity(extracted_cand, title)
                if is_valid:
                    company_name = extracted_cand

    # Minimal Task 3B: If title did not resolve company, use page body leading text
    if not company_name and body_text:
        lead_text = body_text[:2000]
        # Match leading organization subject preceding action verbs in article body
        body_match = re.search(
            r"(?:^|\.\s+|\n+)(?:In\s+[A-Za-z]+,\s*)?([A-Z0-9][A-Za-z0-9\s.,&'\-]{2,40}?)\s+(?:today\s+)?(?:has\s+)?(?:announced|announces|inaugurated|inaugurates|commissioned|commissions|invested|invests|set\s+up|sets\s+up|expanded|expands|signed|signs|unveiled|unveils)\b",
            lead_text,
        )
        if body_match:
            cand = body_match.group(1).strip()
            cand = re.sub(r"[,;:-]+$", "", cand).strip()
            cand_lower = cand.lower()
            generic_endings = (
                " index", " sector", " growth", " market", " quarter", " jobs",
                " line", " plant", " facility", " unit", " state", " states",
                " government", " policy", " scheme", " minister", " crore", " crores",
                " plants", " expansion", " capex", " segment", " segments", " output",
                " production", " manufacturing", " industry", " hub", " park"
            )
            if (
                not cand_lower.startswith(("rs", "inr", "₹", "in ", "the ", "to "))
                and not any(cand_lower.endswith(ge) for ge in generic_endings)
                and len(cand.split()) <= 4
            ):
                is_valid, _ = validate_company_entity(cand, lead_text[:300])
                if is_valid:
                    company_name = cand

    confidence = 0.5
    if geo_fac["city"] != "UNKNOWN":
        confidence += 0.2
    if event_date != "UNKNOWN_DATE":
        confidence += 0.2
    if cal_indicators:
        confidence += 0.1

    cal_rel = "HIGH" if len(cal_indicators) >= 2 else ("MEDIUM" if cal_indicators else "LOW")

    evidence_packet = {
        "company": company_name or "UNKNOWN",
        "facility_name": geo_fac["facility_name"],
        "city": geo_fac["city"],
        "state": geo_fac["state"],
        "facility_linkage_confidence": geo_fac["linkage_confidence"],
        "event_type": event_type,
        "publication_date": publication_date or "UNKNOWN",
        "event_date": event_date,
        "is_future_planned": is_future,
        "recency_tier": recency_tier,
        "investment_amount": investment or "UNKNOWN",
        "calibration_relevance": cal_rel,
        "calibration_indicators": cal_indicators,
        "source_url": url,
        "source_title": title,
        "source_type": source_type,
        "confidence": round(min(1.0, confidence), 2),
        "supporting_snippets": [
            s.strip() for s in body_text.split("\n\n")
            if any(k in s.lower() for k in ("plant", "facility", "crores", "commission", "inaugurate", "manufactur", "expansion"))
        ][:5],
    }

    logger.info(
        "[EVIDENCE_EXTRACTED] Company: %s | Facility: %s in %s, %s | Date: %s | Inv: %s | Conf: %.2f",
        evidence_packet["company"],
        evidence_packet["facility_name"],
        evidence_packet["city"],
        evidence_packet["state"],
        evidence_packet["event_date"],
        evidence_packet["investment_amount"],
        evidence_packet["confidence"],
    )

    return evidence_packet
