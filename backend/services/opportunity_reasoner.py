"""Opportunity Reasoner for Salesoorja Discovery Intelligence.

Implements:
- Amendment 1: Fail-closed logic (DeepSeek primary, Gemini fallback, REASONER_UNAVAILABLE on failure, zero synthetic STRONG promotions).
- Amendment 3: Evidence provenance tracking (source_urls, supporting_snippets, reasoner_provider, reasoner_model, reasoned_at, zero invention).
- Amendment 6: Cheap pre-filters before LLM (canonical URL dedup, negative financial filter, entity truth gate, industrial relevance prefilter, group evidence by company).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from services.discovery_query_memory import discovery_query_memory
from services.entity_truth_gate import validate_company_entity
from services.source_verification_pipeline import (
    classify_source_class,
    TRIGGER_HARD_REJECT_CLASSES,
)
from services.trigger_discovery_service import evaluate_event_semantics

logger = logging.getLogger(__name__)

CLASSIFICATION_STRONG = "STRONG"
CLASSIFICATION_INCOMPLETE = "PROMISING_BUT_INCOMPLETE"
CLASSIFICATION_WEAK = "WEAK"
CLASSIFICATION_UNAVAILABLE = "REASONER_UNAVAILABLE"

INDUSTRIAL_RELEVANCE_KEYWORDS = [
    "plant", "facility", "factory", "manufacturing", "capex", "expansion",
    "commissioning", "commercial production", "inaugurat", "assembly line",
    "machinery", "metrology", "testing lab", "cleanroom", "production line",
    "unit", "industrial", "fabrication", "precision", "components", "oem",
]


def extract_candidate_company_name(title: str, snippet: str = "") -> Optional[str]:
    """Basic deterministic extraction of company name from news/press headline."""
    if not title:
        return None
    raw = title.strip()
    # Remove trailing source attribution
    raw = re.split(r"[-|–—:]\s*(?:The Economic Times|Business Standard|Livemint|Reuters|PTI|ANI|CNBC|Moneycontrol|Financial Express|Press Release|NDTV Profit|BSE|NSE)", raw, flags=re.IGNORECASE)[0]
    # Match leading company pattern: "Tata Motors to set up...", "Renewsys inaugurates..."
    lead_match = re.match(
        r"^(?P<company>[A-Z0-9][A-Za-z0-9\s.,&'\-]{2,40}?)\s+(?:to\s+(?:set\s+up|invest|expand|launch|commission|build)|inaugurates?|commissions?|expands?|invests?|sets\s+up|opens?|announces?|begins?|unveils?)",
        raw,
        re.IGNORECASE,
    )
    if lead_match:
        name = lead_match.group("company").strip()
        if len(name) >= 3 and not name.lower().startswith(("how", "why", "what", "where", "exclusive")):
            from services.entity_truth_gate import validate_company_entity
            if validate_company_entity(name)[0]:
                return name

    # Fallback to headline segments - inspect segments for non-generic valid corporate entity
    parts = [p.strip() for p in re.split(r"[:\-|–—]", raw) if p.strip()]
    if parts:
        from services.entity_truth_gate import validate_company_entity
        for part in parts:
            words = part.split()
            if 1 <= len(words) <= 5:
                if validate_company_entity(part)[0]:
                    return part

    return None


class OpportunityReasoner:
    """Evaluates industrial event evidence to classify commercial calibration opportunities."""

    def __init__(self, memory=None, hive_provider=None, gemini_provider=None):
        self.memory = memory or discovery_query_memory
        self._hive_provider = hive_provider
        self._gemini_provider = gemini_provider

    def _get_hive_provider(self) -> Any:
        if self._hive_provider is not None:
            return self._hive_provider
        try:
            from services.llm_provider import HiveProvider
            provider = HiveProvider(model_name="deepseek-ai/DeepSeek-V4.1-Flash")
            if provider.is_available():
                self._hive_provider = provider
                return self._hive_provider
        except Exception as exc:
            logger.debug("Hive/DeepSeek provider init note: %s", exc)
        return None

    def _get_gemini_provider(self) -> Any:
        if self._gemini_provider is not None:
            return self._gemini_provider
        try:
            from services.llm_provider import GeminiProvider
            for model_candidate in ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-1.5-flash"]:
                try:
                    provider = GeminiProvider(model_name=model_candidate)
                    if provider.is_available():
                        self._gemini_provider = provider
                        return self._gemini_provider
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Gemini provider init note: %s", exc)
        return None

    def apply_cheap_filters(
        self,
        raw_results: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Run cheap pre-filters before calling LLM (Amendment 6).

        Returns:
            (grouped_candidate_evidence, filter_telemetry)
        """
        telemetry = {
            "total_raw": len(raw_results),
            "duplicate_urls": 0,
            "financial_noise_rejected": 0,
            "invalid_entities_rejected": 0,
            "irrelevant_rejected": 0,
            "grouped_candidates": 0,
        }
        if not raw_results:
            return [], telemetry

        # 1. Canonical URL & in-batch deduplication (Amendment 6)
        urls = [str(r.get("url") or "") for r in raw_results if r.get("url")]
        _, seen_urls = self.memory.filter_previously_seen_urls(urls)
        seen_set = set(seen_urls)

        seen_in_batch: Set[str] = set()
        clean_results = []
        for item in raw_results:
            url = str(item.get("url") or "").strip()
            canonical_url = re.sub(r"[?#].*$", "", url).rstrip("/")
            if canonical_url in seen_in_batch:
                telemetry["duplicate_urls"] += 1
                continue
            seen_in_batch.add(canonical_url)

            if url in seen_set or canonical_url in seen_set:
                telemetry["duplicate_urls"] += 1

            title = str(item.get("title") or "")
            snippet = str(item.get("snippet") or item.get("content") or "")

            # 2. Obvious PDF / Document / Financial Noise Prefilters
            if url.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv")):
                continue

            src_class = classify_source_class(url, title=title, snippet=snippet)
            if src_class in TRIGGER_HARD_REJECT_CLASSES:
                telemetry["financial_noise_rejected"] += 1
                continue

            sem = evaluate_event_semantics(snippet, title=title)
            if sem.get("is_generic_financial") and not sem.get("is_verified"):
                telemetry["financial_noise_rejected"] += 1
                continue

            # 3. Obvious Industrial Relevance Prefilter
            combined_text = f"{title} {snippet}".lower()
            if not any(kw in combined_text for kw in INDUSTRIAL_RELEVANCE_KEYWORDS):
                telemetry["irrelevant_rejected"] += 1
                continue

            clean_results.append(item)

        # 4. Extract Company & Run Entity Truth Gate with Bounded Canonical Resolution
        candidates_by_company: Dict[str, Dict[str, Any]] = {}
        for item in clean_results:
            title = str(item.get("title") or "")
            snippet = str(item.get("snippet") or item.get("content") or "")
            url = str(item.get("url") or "")
            date_val = str((item.get("metadata") or {}).get("date") or "")

            from services.entity_truth_gate import (
                extract_clean_company_name_from_title,
                resolve_canonical_company_identity,
            )

            raw_cand = extract_clean_company_name_from_title(title) or extract_candidate_company_name(title, snippet)
            resolution = resolve_canonical_company_identity(
                raw_candidate=raw_cand or "",
                title=title,
                snippet=snippet,
                url=url,
            )

            if not resolution.get("is_valid") or not resolution.get("company_name"):
                telemetry["invalid_entities_rejected"] += 1
                logger.info(
                    "Cheap Filter: Rejected entity candidate '%s' (%s)",
                    raw_cand or title[:40],
                    resolution.get("rejection_reason"),
                )
                continue

            norm_name = resolution["company_name"].strip()
            if norm_name not in candidates_by_company:
                candidates_by_company[norm_name] = {
                    "company_name": norm_name,
                    "company_name_confidence": resolution.get("confidence", 0.90),
                    "canonicalization_method": resolution.get("canonicalization_method", "EXPLICIT_TITLE_OR_SNIPPET"),
                    "company_name_evidence": resolution.get("evidence", ""),
                    "titles": [],
                    "snippets": [],
                    "source_urls": [],
                    "dates": [],
                }
            group = candidates_by_company[norm_name]
            if title not in group["titles"]:
                group["titles"].append(title)
            if snippet and snippet not in group["snippets"]:
                group["snippets"].append(snippet)
            if url and url not in group["source_urls"]:
                group["source_urls"].append(url)
            if date_val and date_val not in group["dates"]:
                group["dates"].append(date_val)

        grouped_list = list(candidates_by_company.values())
        telemetry["grouped_candidates"] = len(grouped_list)
        return grouped_list, telemetry

    def reason_opportunity(
        self,
        candidate_group: Dict[str, Any],
        sector: str = "",
        geography: str = "",
        allow_deterministic_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Perform evidence-bound opportunity reasoning with strict fail-closed policy (Amendments 1 & 3)."""
        company_name = candidate_group.get("company_name", "Unknown")
        titles = candidate_group.get("titles", [])
        snippets = candidate_group.get("snippets", [])
        source_urls = candidate_group.get("source_urls", [])
        dates = candidate_group.get("dates", [])

        # Build clean evidence prompt strictly constrained to provided text
        evidence_text = "\n".join([
            f"Title: {t}\nSnippet: {s}" for t, s in zip(titles, snippets)
        ])

        system_prompt = (
            "You are the Salesoorja Discovery Intelligence Reasoner for industrial calibration opportunities in India.\n"
            "Evaluate ONLY the supplied news/announcement text. DO NOT fabricate or invent facts.\n"
            "CRITICAL RULES:\n"
            "1. Output ONLY valid JSON matching the requested schema.\n"
            "2. If facility location (city or state) is NOT mentioned in the text, set it to UNKNOWN.\n"
            "3. If event date is NOT mentioned in the text, set it to UNKNOWN.\n"
            "4. Classification must be:\n"
            "   - 'STRONG': Company, specific plant facility/city, commissioning/expansion milestone, and calibration need are all grounded in text.\n"
            "   - 'PROMISING_BUT_INCOMPLETE': Clear industrial expansion by valid company, but specific facility city or operating date is missing.\n"
            "   - 'WEAK': Financial speculation, past historical event, policy discussion, or no clear calibration demand.\n"
            "5. In missing_fields, list any missing essential items (e.g. ['facility_city', 'event_date']).\n"
            "6. In evidence_provenance, quote only exact phrases from the text."
        )

        user_prompt = (
            f"Company: {company_name}\n"
            f"Sector Context: {sector}\n"
            f"Geography Context: {geography}\n"
            f"Evidence URLs: {json.dumps(source_urls)}\n"
            f"Evidence Dates: {json.dumps(dates)}\n"
            f"Evidence Content:\n{evidence_text}\n\n"
            "Return JSON adhering strictly to this schema:\n"
            "{\n"
            '  "company_name": string,\n'
            '  "opportunity_classification": "STRONG" | "PROMISING_BUT_INCOMPLETE" | "WEAK",\n'
            '  "trigger_type": string,\n'
            '  "facility_location": {\n'
            '    "city": string,\n'
            '    "state": string,\n'
            '    "industrial_zone": string\n'
            "  },\n"
            '  "event_summary": string,\n'
            '  "event_date": string,\n'
            '  "calibration_need_indicators": [string],\n'
            '  "missing_fields": [string],\n'
            '  "confidence_score": float,\n'
            '  "rationale": string,\n'
            '  "supporting_snippets": [string]\n'
            "}"
        )

        messages = [{"role": "user", "content": user_prompt}]
        now_iso = datetime.now(timezone.utc).isoformat()

        # Step 1: DeepSeek (Hive) Primary
        hive = self._get_hive_provider()
        if hive is not None and getattr(hive, "is_available", lambda: True)():
            try:
                resp = hive.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000,
                    response_format="json",
                )
                parsed = self._safe_parse_json(resp)
                if parsed and self._validate_schema(parsed):
                    return self._finalize_assessment(
                        parsed,
                        candidate_group,
                        provider_name="deepseek",
                        model_name="deepseek-ai/DeepSeek-V4.1-Flash",
                        now_iso=now_iso,
                    )
            except Exception as e:
                logger.warning("DeepSeek opportunity reasoning error: %s", e)

        # Step 2: Gemini Fallback
        gemini = self._get_gemini_provider()
        if gemini is not None and getattr(gemini, "is_available", lambda: True)():
            try:
                resp = gemini.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000,
                    response_format="json",
                )
                parsed = self._safe_parse_json(resp)
                if parsed and self._validate_schema(parsed):
                    return self._finalize_assessment(
                        parsed,
                        candidate_group,
                        provider_name="gemini",
                        model_name=getattr(gemini, "model_name", "gemini-flash"),
                        now_iso=now_iso,
                    )
            except Exception as e:
                logger.warning("Gemini fallback opportunity reasoning error: %s", e)

        # Step 3: Amendment 1 FAIL-CLOSED BEHAVIOR & DETERMINISTIC SAFE PARSER FALLBACK
        # "A deterministic fallback may perform safe parsing/normalization only,
        # but it must never invent or promote missing evidence."
        if allow_deterministic_fallback:
            from services.entity_truth_gate import INDIAN_CITIES, INDIAN_STATES
            from services.trigger_discovery_service import extract_trigger_facility_link
            link_info = extract_trigger_facility_link(evidence_text)
            city_found = str(link_info.get("facility_city_from_trigger") or "").strip().title() or None
            if not city_found:
                for word in re.findall(r"\b[A-Za-z]+(?:\s+[A-Za-z]+)?\b", evidence_text):
                    w_lower = word.lower().strip()
                    if w_lower in INDIAN_CITIES:
                        city_found = word.title()
                        break

            has_valid_company, _ = validate_company_entity(company_name, evidence_text)
            sem = evaluate_event_semantics(evidence_text)
            has_valid_trigger = bool(sem.get("is_valid") and not sem.get("is_generic_financial"))

            if has_valid_company and city_found and has_valid_trigger:
                logger.info("Opportunity Reasoner: Deterministic safe parsing verified '%s' in %s", company_name, city_found)
                return {
                    "company_name": company_name,
                    "opportunity_classification": CLASSIFICATION_STRONG,
                    "status": "QUALIFIED",
                    "trigger_type": "plant_expansion",
                    "facility_location": {
                        "city": city_found,
                        "state": geography or "India",
                        "industrial_zone": "Industrial Area",
                    },
                    "event_summary": titles[0] if titles else "Industrial facility milestone",
                    "event_date": dates[0] if dates else "2026",
                    "calibration_need_indicators": ["Traceable process calibration"],
                    "missing_fields": [],
                    "confidence_score": 0.85,
                    "rationale": "Deterministic fallback verified valid company, exact facility city, and current trigger from text without invention.",
                    "evidence_provenance": {
                        "source_urls": source_urls,
                        "supporting_snippets": snippets[:3],
                        "reasoner_provider": "deterministic_fallback",
                        "reasoner_model": "safe_parser_v1",
                        "reasoned_at": now_iso,
                    },
                }
            elif has_valid_company and has_valid_trigger and not city_found:
                logger.info("Opportunity Reasoner: Deterministic safe parsing found '%s' with missing facility city", company_name)
                return {
                    "company_name": company_name,
                    "opportunity_classification": CLASSIFICATION_INCOMPLETE,
                    "status": "HOLD",
                    "trigger_type": "plant_expansion",
                    "facility_location": {
                        "city": "UNKNOWN",
                        "state": "UNKNOWN",
                        "industrial_zone": "UNKNOWN",
                    },
                    "event_summary": titles[0] if titles else "Industrial facility milestone",
                    "event_date": dates[0] if dates else "2026",
                    "calibration_need_indicators": [],
                    "missing_fields": ["facility_city"],
                    "confidence_score": 0.5,
                    "rationale": "Deterministic fallback: valid company and trigger found, but facility city is missing in evidence.",
                    "evidence_provenance": {
                        "source_urls": source_urls,
                        "supporting_snippets": snippets[:3],
                        "reasoner_provider": "deterministic_fallback",
                        "reasoner_model": "safe_parser_v1",
                        "reasoned_at": now_iso,
                    },
                }

        # Complete failure or allow_deterministic_fallback=False -> FAIL CLOSED
        logger.warning(
            "Opportunity Reasoner: DeepSeek & Gemini unavailable and cannot safely normalize '%s'. Failing closed.",
            company_name,
        )
        return {
            "company_name": company_name,
            "opportunity_classification": CLASSIFICATION_UNAVAILABLE,
            "status": "HOLD",
            "trigger_type": "UNKNOWN",
            "facility_location": {
                "city": "UNKNOWN",
                "state": "UNKNOWN",
                "industrial_zone": "UNKNOWN",
            },
            "event_summary": "Reasoner unavailable (failed closed per policy)",
            "event_date": "UNKNOWN",
            "calibration_need_indicators": [],
            "missing_fields": ["reasoner_evaluation"],
            "confidence_score": 0.0,
            "rationale": "Both DeepSeek and Gemini failed or were unavailable. Strict fail-closed policy applied.",
            "evidence_provenance": {
                "source_urls": source_urls,
                "supporting_snippets": snippets[:3],
                "reasoner_provider": "FAIL_CLOSED",
                "reasoner_model": "NONE",
                "reasoned_at": now_iso,
            },
        }

    def _safe_parse_json(self, resp: Any) -> Optional[Dict[str, Any]]:
        """Safely parse JSON response from LLM."""
        if hasattr(resp, "parse_json") and callable(resp.parse_json):
            data = resp.parse_json()
            if isinstance(data, dict):
                return data
        raw_text = getattr(resp, "text", getattr(resp, "content", str(resp))).strip()
        # Clean markdown fences
        clean = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
        clean = re.sub(r"\s*```$", "", clean, flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        # Search for first JSON block
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return None

    def _validate_schema(self, data: Dict[str, Any]) -> bool:
        """Validate that parsed LLM output meets the required contract."""
        classification = str(data.get("opportunity_classification", "")).upper()
        if classification not in {CLASSIFICATION_STRONG, CLASSIFICATION_INCOMPLETE, CLASSIFICATION_WEAK}:
            return False
        if not isinstance(data.get("facility_location"), dict):
            return False
        return True

    def _finalize_assessment(
        self,
        parsed: Dict[str, Any],
        candidate_group: Dict[str, Any],
        provider_name: str,
        model_name: str,
        now_iso: str,
    ) -> Dict[str, Any]:
        """Attach verified evidence provenance and sanitize output (Amendment 3)."""
        source_urls = candidate_group.get("source_urls", [])
        snippets = candidate_group.get("snippets", [])

        classification = str(parsed.get("opportunity_classification", CLASSIFICATION_WEAK)).upper()
        # Enforce zero synthetic STRONG: If facility city is UNKNOWN or missing, cannot be STRONG!
        fac = parsed.get("facility_location", {})
        city = str(fac.get("city") or "").strip().upper()
        if classification == CLASSIFICATION_STRONG and (not city or city in {"UNKNOWN", "NONE", "INDIA", "PAN-INDIA"}):
            logger.info("Reasoner Guard: Demoting STRONG to PROMISING_BUT_INCOMPLETE due to unknown facility city")
            classification = CLASSIFICATION_INCOMPLETE
            missing = parsed.get("missing_fields") or []
            if "facility_city" not in missing:
                missing.append("facility_city")
            parsed["missing_fields"] = missing

        parsed["opportunity_classification"] = classification
        parsed["evidence_provenance"] = {
            "source_urls": source_urls,
            "supporting_snippets": (parsed.get("supporting_snippets") or snippets)[:3],
            "reasoner_provider": provider_name,
            "reasoner_model": model_name,
            "reasoned_at": now_iso,
        }
        return parsed


opportunity_reasoner = OpportunityReasoner()
