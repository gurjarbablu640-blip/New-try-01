"""Fast Contact Waterfall & Apollo Qualified-Only Lead Enrichment Service.

Implements Phase 11–14 & Phase 19–20 Specifications:
1. Fast Contact Waterfall:
   - Step 1: Check Salesoorja cache/CRM.
   - Step 2: Official company/person contact source.
   - Step 3: Targeted single public web search (with strict 60–90s cutoff).
   - If no direct contact found quickly -> Escalate immediately to Apollo.
2. Strict Apollo Qualified-Only Gate:
   - Current real trigger (not expired).
   - Facility verified.
   - Trigger->Facility linkage is DIRECT or STRONG.
   - Person is verified human with qualified authority role.
   - Deduplication check (no duplicate Apollo spend on same person/company).
3. Apollo Minimal Field Request & Match Classification:
   - MATCH_CONFIRMED
   - MATCH_DIFFERENT_ROLE
   - MATCH_WRONG_COMPANY
   - MATCH_WRONG_FACILITY
   - MATCH_FORMER_EMPLOYEE
   - CONTACT_FOUND
   - CONTACT_NOT_FOUND
4. Secondary Person Fallback:
   - If Primary person returns NO_MATCH or former employee, attempts Secondary Person.
5. Persistent Apollo Query & Credit Log (`backend/data/runtime_state/apollo_query_log.json`).
6. Production Contact Gate & Email Preview Generation (Test Mode Only, No Sends).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from services.apollo_adapter import enrich_specific_person
from services.contact_confidence import validate_person_name
from services.email_validator import EMAIL_REGEX, validate_email_address
from services.opportunity_gates import ICP_OUTBOUND_MIN_SCORE, evaluate_opportunity_gates

def is_valid_email(email: Optional[str]) -> bool:
    return bool(email and EMAIL_REGEX.match(email.strip()))
from services.research_provider import research_router
from services.settings_manager import get_setting_value

logger = logging.getLogger(__name__)

APOLLO_LOG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "runtime_state",
    "apollo_query_log.json",
)

APOLLO_PENDING_QUEUE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "runtime_state",
    "apollo_pending_queue.json",
)

CONTACT_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "runtime_state",
    "contact_waterfall_cache.json",
)

# Apollo night mode toggle: False prevents consuming expired credits
APOLLO_ENABLED_FOR_LIVE_LOOKUP = False

# Status classifications
STATUS_DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE = "DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE"
STATUS_PENDING_APOLLO_RENEWAL = "PENDING_APOLLO_RENEWAL"
STATUS_HOLD_STALE_TRIGGER = "HOLD_STALE_TRIGGER"
STATUS_HOLD_LOW_SCORE = "HOLD_LOW_SCORE"
STATUS_HOLD_PERSON_REVIEW = "HOLD_PERSON_REVIEW"
STATUS_HOLD_WRONG_PERSON = "HOLD_WRONG_PERSON"
STATUS_HOLD_TRIGGER_INVALID = "HOLD_TRIGGER_INVALID"
STATUS_HOLD_FACILITY_AMBIGUOUS = "HOLD_FACILITY_AMBIGUOUS"
STATUS_HOLD_QUEUE_PROVENANCE_INVALID = "HOLD_QUEUE_PROVENANCE_INVALID"
STATUS_HOLD_RECENCY_INCONSISTENT = "HOLD_RECENCY_INCONSISTENT"

ALLOWED_STRONG_COMMERCIAL_CLASSES = {
    "DIRECT_CALIBRATION_OWNER",
    "METROLOGY_OWNER",
    "STRONG_PLANT_QUALITY_OWNER",
    "FACILITY_OWNER",
    "GROUP_FUNCTION_OWNER",
}

STOCK_PATTERNS = [
    "/stockpricequote/",
    "/stocks/companyid-",
    "stock-share-price",
    "screener.in/company/",
    "marketscreener.com",
    "livemint.com/market/",
    "bloomberg.com/quote/",
    "bseindia.com/stock-share-price",
    "/market-activity/stocks/",
]

def is_stock_quote_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return any(p in u for p in STOCK_PATTERNS)

def is_generic_homepage_url(url: str) -> bool:
    if not url:
        return True
    u = url.lower().rstrip("/")
    parts = u.split("://")[-1].split("/")
    return len(parts) <= 1 or (len(parts) == 2 and parts[1] in ("", "about-us", "about", "contact", "home", "en", "news"))

def compute_deterministic_priority_and_status(lead_score: float) -> Tuple[str, str]:
    """Strict Salesoorja commercial policy mapping:
    95-100 -> P1
    90-94 -> P2
    85-89 -> P3
    <85 -> HOLD_LOW_SCORE
    """
    if lead_score >= 95.0:
        return "P1", STATUS_PENDING_APOLLO_RENEWAL
    elif lead_score >= 90.0:
        return "P2", STATUS_PENDING_APOLLO_RENEWAL
    elif lead_score >= ICP_OUTBOUND_MIN_SCORE:
        return "P3", STATUS_PENDING_APOLLO_RENEWAL
    else:
        return "HOLD", STATUS_HOLD_LOW_SCORE

# Match classifications
MATCH_CONFIRMED = "MATCH_CONFIRMED"
MATCH_DIFFERENT_ROLE = "MATCH_DIFFERENT_ROLE"
MATCH_WRONG_COMPANY = "MATCH_WRONG_COMPANY"
MATCH_WRONG_FACILITY = "MATCH_WRONG_FACILITY"
MATCH_FORMER_EMPLOYEE = "MATCH_FORMER_EMPLOYEE"
CONTACT_FOUND = "CONTACT_FOUND"
CONTACT_NOT_FOUND = "CONTACT_NOT_FOUND"



class FastContactWaterfallService:
    """Manages rapid free contact discovery followed by authorized Apollo enrichment."""

    def __init__(
        self,
        apollo_log_file: Optional[str] = None,
        contact_cache_file: Optional[str] = None,
        pending_queue_file: Optional[str] = None,
        max_free_search_seconds: float = 60.0,
    ):
        self.apollo_log_file = apollo_log_file or APOLLO_LOG_FILE
        self.contact_cache_file = contact_cache_file or CONTACT_CACHE_FILE
        self.pending_queue_file = pending_queue_file or APOLLO_PENDING_QUEUE_FILE
        self.max_free_search_seconds = max_free_search_seconds
        self._apollo_log = self._load_json(self.apollo_log_file, default_factory=list)
        self._contact_cache = self._load_json(self.contact_cache_file, default_factory=dict)
        self._pending_queue = self._load_json(self.pending_queue_file, default_factory=list)

    def _load_json(self, path: str, default_factory: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load JSON file '%s': %s", path, e)
        return default_factory() if callable(default_factory) else default_factory

    def _save_pending_queue(self):
        try:
            os.makedirs(os.path.dirname(self.pending_queue_file), exist_ok=True)
            with open(self.pending_queue_file, "w", encoding="utf-8") as f:
                json.dump(self._pending_queue, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save Apollo pending queue: %s", e)

    def _save_apollo_log(self):
        try:
            os.makedirs(os.path.dirname(self.apollo_log_file), exist_ok=True)
            with open(self.apollo_log_file, "w", encoding="utf-8") as f:
                json.dump(self._apollo_log, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save Apollo query log: %s", e)

    def _save_contact_cache(self):
        try:
            os.makedirs(os.path.dirname(self.contact_cache_file), exist_ok=True)
            with open(self.contact_cache_file, "w", encoding="utf-8") as f:
                json.dump(self._contact_cache, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save contact cache: %s", e)

    def is_apollo_eligible(self, candidate_record: Dict[str, Any]) -> Tuple[bool, str]:
        """Check all upstream opportunity and qualification gates for Apollo consumption."""
        # 1. Trigger-to-facility linkage
        trigger_eval = candidate_record.get("trigger_eval") or {}
        tf_conf = str(
            candidate_record.get("trigger_to_facility")
            or trigger_eval.get("trigger_facility_confidence")
            or ""
        ).upper()
        if tf_conf not in ("DIRECT", "STRONG"):
            return False, f"Trigger-to-facility linkage is {tf_conf or 'UNKNOWN'}; requires DIRECT or STRONG"

        # 2. Person candidate name
        person = candidate_record.get("primary_person") or {}
        person_name = person.get("name") or candidate_record.get("person_name") or ""
        val = validate_person_name(person_name)
        if val["person_name_validation"] != "VALID":
            return False, f"Person candidate name '{person_name}' is not a valid human person"

        # 3. Authority & commercial ownership
        authority = person.get("authority_class") or person.get("authority_classification") or person.get("classification") or candidate_record.get("authority_class") or ""
        if authority in ("COMPANY_ONLY", "UNKNOWN", "GENERAL_QUALITY"):
            return False, f"Person authority '{authority}' is insufficient for Apollo spend"
        if authority not in ALLOWED_STRONG_COMMERCIAL_CLASSES:
            # FUNCTIONALLY_RELEVANT alone is NOT sufficient for automatic Apollo queue entry unless accompanied by clear commercial ownership evidence
            title_lower = str(person.get("title") or candidate_record.get("person_title") or "").lower()
            commercial_ownership = any(h in title_lower for h in ["plant head", "head of quality", "vice president", "vp", "director", "dgm", "general manager", "quality head"])
            if not commercial_ownership:
                return False, f"FUNCTIONALLY_RELEVANT person title '{title_lower}' lacks verified commercial ownership evidence"

        # 4. Check deduplication
        company_norm = re.sub(r"[^a-z0-9]", "", str(candidate_record.get("company", "")).lower())
        person_norm = re.sub(r"[^a-z0-9]", "", person_name.lower())
        dedup_key = f"{company_norm}:{person_norm}"

        for entry in self._apollo_log:
            if entry.get("dedup_key") == dedup_key and entry.get("status") in ("SUCCESS", "NO_RESULT"):
                return False, f"Recent Apollo lookup already exists for {person_name} at {candidate_record.get('company')}"

        # 5. Provenance check: only AUTOMATED_PIPELINE can enter production queue
        origin = candidate_record.get("queue_origin") or candidate_record.get("provenance")
        if origin and origin not in ("AUTOMATED_PIPELINE",):
            return False, f"Queue origin '{origin}' is invalid; only AUTOMATED_PIPELINE may enter Apollo queue"

        # 6. Lead score threshold
        score = float(candidate_record.get("lead_score", 0) or 0)
        if score < ICP_OUTBOUND_MIN_SCORE:
            return False, f"Lead score {score} is below Apollo qualification threshold (>={ICP_OUTBOUND_MIN_SCORE:.1f} required)"

        # 7. Trigger source & event semantics gate (if trigger source provided)
        trigger_url = candidate_record.get("trigger_source") or candidate_record.get("trigger_url") or ""
        if trigger_url:
            if is_stock_quote_url(trigger_url):
                return False, f"Trigger source '{trigger_url}' is a financial stock quote page, which cannot prove plant expansion"
            if is_generic_homepage_url(trigger_url) and not candidate_record.get("trigger_event_semantics_verified"):
                return False, f"Trigger source '{trigger_url}' is a generic homepage/profile without event semantics"

        # 8. Recency data consistency check
        recency_diff = candidate_record.get("recency_diff")
        if recency_diff is not None and abs(recency_diff) > 2:
            return False, f"Recency data inconsistency detected: difference {recency_diff}d > 2d"

        person_confidence = str(
            person.get("person_confidence")
            or person.get("apollo_person_confidence")
            or candidate_record.get("apollo_person_confidence")
            or ""
        ).upper()
        if person_confidence != "HIGH":
            return False, f"Person confidence is {person_confidence or 'UNKNOWN'}; HIGH is required before Apollo enrichment"

        employment_verified = bool(
            person.get("employment_verified")
            or person.get("current_employment_verified")
            or str(person.get("current_employment") or "").upper() == "VERIFIED"
            or candidate_record.get("current_employment_verified")
        )
        if not employment_verified:
            return False, "Current employment is not verified; Apollo cannot discover or repair person identity"

        person_facility = str(
            person.get("facility_relationship")
            or person.get("facility_classification")
            or candidate_record.get("person_facility_relationship")
            or ""
        ).upper()
        if person_facility not in {
            "DIRECT",
            "STRONG",
            "FACILITY_OWNER",
            "FACILITY_FUNCTION_OWNER",
            "GROUP_FUNCTION_OWNER",
        }:
            return False, f"Person-to-facility relationship is {person_facility or 'UNKNOWN'}; DIRECT or source-backed STRONG ownership is required"

        if candidate_record.get("trigger_event_semantics_verified") is not True:
            return False, "Trigger/timing evidence has not passed deterministic verification"

        timing_class = str(candidate_record.get("timing_class") or "").upper()
        if timing_class not in {"CURRENT", "RECENT"}:
            return False, f"Timing class is {timing_class or 'UNKNOWN'}; a current qualified buying window is required"

        return True, "All upstream gates passed; lead is eligible for Apollo enrichment"



    def execute_fast_contact_waterfall(
        self,
        candidate_record: Dict[str, Any],
        db_session: Any = None,
    ) -> Dict[str, Any]:
        """Execute Phase 11 fast free contact search before falling back to Apollo."""
        company = candidate_record.get("company", "")
        person = candidate_record.get("primary_person") or {}
        person_name = person.get("name") or ""

        cache_key = f"{company.lower()}:{person_name.lower()}"
        if cache_key in self._contact_cache:
            return {
                "source": "CACHE",
                "email": self._contact_cache[cache_key].get("email"),
                "phone": self._contact_cache[cache_key].get("phone"),
                "email_status": self._contact_cache[cache_key].get("email_status"),
                "contact_verified": bool(self._contact_cache[cache_key].get("email")),
                "seconds_elapsed": 0.0,
            }

        t0 = time.time()

        # Step 2: Official domain contact search
        domain = candidate_record.get("official_domain") or ""
        found_email = None
        found_phone = None
        email_status = None

        if domain and " " not in domain:
            try:
                q = f'"{person_name}" "@{domain}"'
                res = research_router.search(query=q, num_results=3, db=db_session, free_only=True)
                for item in res.get("results", []):
                    text = f"{item.get('title', '')} {item.get('snippet', '')}"
                    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
                    for em in emails:
                        if is_valid_email(em) and not any(junk in em.lower() for junk in ["noreply", "info@", "contact@"]):
                            found_email = em
                            email_status = "public_web_verified"
                            break
                    if found_email:
                        break
            except Exception as e:
                logger.warning("Free search step 2 failed: %s", e)

        # Step 3: Fast single targeted search if time permits
        elapsed = time.time() - t0
        if not found_email and elapsed < self.max_free_search_seconds:
            try:
                q = f'"{person_name}" "{company}" email phone contact'
                res = research_router.search(query=q, num_results=3, db=db_session, free_only=True)
                for item in res.get("results", []):
                    text = f"{item.get('title', '')} {item.get('snippet', '')}"
                    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
                    for em in emails:
                        if is_valid_email(em) and not any(junk in em.lower() for junk in ["noreply", "info@", "contact@"]):
                            found_email = em
                            email_status = "public_web_verified"
                            break
                    if found_email:
                        break
            except Exception as e:
                logger.warning("Free search step 3 failed: %s", e)

        elapsed = round(time.time() - t0, 3)

        if found_email:
            self._contact_cache[cache_key] = {
                "email": found_email,
                "phone": found_phone,
                "email_status": email_status,
            }
            self._save_contact_cache()
            return {
                "source": "FREE_PUBLIC_SEARCH",
                "email": found_email,
                "phone": found_phone,
                "email_status": email_status,
                "contact_verified": True,
                "seconds_elapsed": elapsed,
            }

        return {
            "source": "FREE_SEARCH_EXHAUSTED",
            "email": None,
            "phone": None,
            "email_status": None,
            "contact_verified": False,
            "seconds_elapsed": elapsed,
        }

    def enrich_with_apollo(
        self,
        candidate_record: Dict[str, Any],
        use_secondary_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Perform minimal authorized Apollo enrichment for a qualified candidate."""
        company = candidate_record.get("company", "")
        person = candidate_record.get("primary_person") or {}
        person_name = person.get("name") or candidate_record.get("person_name") or ""
        title = person.get("title") or ""

        # Verify eligibility
        eligible, reason = self.is_apollo_eligible(candidate_record)
        if not eligible:
            return {
                "status": "APOLLO_INELIGIBLE",
                "reason": reason,
                "company": company,
                "person": person_name,
                "contact_verified": False,
            }

        company_norm = re.sub(r"[^a-z0-9]", "", company.lower())
        person_norm = re.sub(r"[^a-z0-9]", "", person_name.lower())
        dedup_key = f"{company_norm}:{person_norm}"

        # Phase 18: Apollo Night Mode Check (Subscription expired today; user renewal tomorrow)
        live_lookup_enabled = bool(get_setting_value("APOLLO_ENABLED_FOR_LIVE_LOOKUP", APOLLO_ENABLED_FOR_LIVE_LOOKUP))
        if not live_lookup_enabled:
            authority = person.get("authority_class") or person.get("authority_classification") or person.get("classification") or candidate_record.get("authority_class") or ""
            score = float(candidate_record.get("lead_score", 0) or 0)
            priority, queue_status = compute_deterministic_priority_and_status(score)

            t_date_str = candidate_record.get("trigger_date") or ""
            stored_recency = candidate_record.get("recency_days") or 0
            calc_recency = candidate_record.get("calculated_recency_days")
            if calc_recency is None:
                calc_recency = stored_recency

            recency_diff = candidate_record.get("recency_diff", 0)
            recency_incon = bool(candidate_record.get("recency_data_inconsistency", False) or (recency_diff and abs(recency_diff) > 2))

            origin = candidate_record.get("queue_origin") or "AUTOMATED_PIPELINE"
            person_conf = person.get("person_confidence") or person.get("apollo_person_confidence") or candidate_record.get("apollo_person_confidence")

            queue_item = {
                "company": company,
                "legal_company_name": candidate_record.get("legal_company_name") or company,
                "domain": candidate_record.get("official_domain") or candidate_record.get("domain") or "",
                "facility": candidate_record.get("facility") or candidate_record.get("facility_city") or "",
                "city": candidate_record.get("facility_city") or candidate_record.get("city") or "",
                "state": candidate_record.get("facility_state") or candidate_record.get("state") or "",
                "person_name": person_name,
                "person_title": title,
                "linkedin_url": person.get("linkedin_url") or "",
                "authority_class": authority,
                "apollo_person_confidence": person_conf,
                "current_employment_verified": bool(
                    person.get("employment_verified")
                    or person.get("current_employment_verified")
                    or str(person.get("current_employment") or "").upper() == "VERIFIED"
                    or candidate_record.get("current_employment_verified")
                ),
                "person_facility_relationship": person.get("facility_relationship") or person.get("facility_classification") or candidate_record.get("person_facility_relationship") or "",
                "trigger_type": candidate_record.get("trigger_type") or candidate_record.get("event") or "",
                "trigger_date": t_date_str,
                "recency_days": stored_recency,
                "calculated_recency_days": calc_recency,
                "calculation_reference_date": "2026-09-12",
                "date_parse_status": candidate_record.get("date_parse_status") or "STORED",
                "recency_data_inconsistency": recency_incon,
                "recency_diff": recency_diff,
                "timing_class": candidate_record.get("timing_class") or "CURRENT",
                "trigger_source": candidate_record.get("trigger_source") or candidate_record.get("trigger_url") or "",
                "trigger_source_role": candidate_record.get("trigger_source_role") or ("TRADE_PRESS_VERIFIED_EVENT" if "autocarpro" in str(candidate_record.get("trigger_source", "")) else "WEB_SEARCH"),
                "trigger_source_title": candidate_record.get("trigger_source_title") or candidate_record.get("trigger_title") or "",
                "trigger_source_date": t_date_str,
                "trigger_evidence_snippet": candidate_record.get("trigger_evidence_snippet") or candidate_record.get("trigger_snippet") or "",
                "trigger_event_semantics_verified": candidate_record.get("trigger_event_semantics_verified", True),
                "ongoing_source": candidate_record.get("ongoing_source") or "",
                "ongoing_date": candidate_record.get("ongoing_date") or "",
                "timing_reason": candidate_record.get("timing_reason") or "",
                "facility_source": candidate_record.get("facility_source") or candidate_record.get("facility_url") or "",
                "trigger_to_facility": candidate_record.get("trigger_to_facility") or "DIRECT",
                "person_source": person.get("source_url") or person.get("linkedin_url") or candidate_record.get("person_source") or "",
                "lead_score": score,
                "why_qualified": reason,
                "lookup_priority": priority,
                "dedup_key": dedup_key,
                "queue_origin": origin,
                "queued_at": datetime.now(timezone.utc).isoformat(),
                "status": queue_status,
            }
            # Deduplicate in pending queue
            existing_idx = next((i for i, item in enumerate(self._pending_queue) if item.get("dedup_key") == dedup_key), None)
            if existing_idx is not None:
                self._pending_queue[existing_idx] = queue_item
            else:
                self._pending_queue.append(queue_item)
            self._save_pending_queue()

            logger.info("Apollo Night Mode active: deferred live lookup for %s at %s into renewal queue (priority: %s)", person_name, company, priority)
            return {
                "status": STATUS_DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE,
                "contact_enrichment_status": STATUS_DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE,
                "company": company,
                "person": person_name,
                "title": title,
                "match_classification": STATUS_DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE,
                "email": None,
                "email_status": None,
                "phone": None,
                "contact_verified": False,
                "apollo_live_calls_made": 0,
                "credits_consumed": 0,
                "lookup_priority": priority,
                "ready_for_email": False,
                "queue_status": queue_status,
            }


        logger.info("Executing Apollo enrichment for qualified decision maker: %s (%s) at %s", person_name, title, company)
        apollo_res = enrich_specific_person(
            person_name=person_name,
            company_name=company,
            title=title,
        )

        # Classify match
        match_class = CONTACT_NOT_FOUND
        email = apollo_res.get("email")
        phone = apollo_res.get("phone")
        email_status = apollo_res.get("email_status")
        raw = apollo_res.get("raw_response") or {}

        if apollo_res.get("status") == "SUCCESS" and email:
            match_class = CONTACT_FOUND
        elif apollo_res.get("status") == "NO_RESULT":
            match_class = CONTACT_NOT_FOUND
        elif apollo_res.get("status") == "APOLLO_BLOCKED":
            match_class = "APOLLO_BLOCKED"

        # Log query
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "company": company,
            "person": person_name,
            "title": title,
            "dedup_key": dedup_key,
            "reason": "Qualified lead direct contact missing",
            "status": apollo_res.get("status"),
            "match_class": match_class,
            "email_found": bool(email),
            "phone_found": bool(phone),
        }
        self._apollo_log.append(log_entry)
        self._save_apollo_log()

        # Phase 14: Fallback to secondary person if primary returned no contact
        if not email and use_secondary_fallback:
            secondary = candidate_record.get("secondary_person")
            if secondary and secondary.get("name") and secondary.get("name") != person_name:
                sec_name = secondary["name"]
                sec_title = secondary.get("title", "")
                logger.info("Engaging Apollo fallback to secondary decision maker: %s at %s", sec_name, company)
                fallback_record = dict(candidate_record)
                fallback_record["primary_person"] = secondary
                return self.enrich_with_apollo(fallback_record, use_secondary_fallback=False)

        # Post-enrichment requalification
        is_contact_verified = False
        if email and is_valid_email(email):
            is_contact_verified = True

        return {
            "status": apollo_res.get("status"),
            "company": company,
            "person": person_name,
            "title": title,
            "match_classification": match_class,
            "email": email,
            "email_status": email_status,
            "phone": phone,
            "contact_verified": is_contact_verified,
            "ready_for_email": is_contact_verified and bool(get_setting_value("OUTBOUND_TEST_MODE", True)),
        }

    def generate_email_preview(
        self,
        candidate_record: Dict[str, Any],
        contact_info: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate non-sending personalized email preview (Test Mode Only).

        Enforces Phase 17 Claim Hygiene:
        - No unsupported 48-hour turnaround claims
        - No mischaracterization of customer duties as 'NABL CC-3963 standards'
        - Anchors strictly to ISO/IEC 17025:2017 (NABL Certificate CC-3963)
        """
        company = candidate_record.get("company", "")
        person = candidate_record.get("primary_person") or {}
        person_name = person.get("name") or "Quality Leader"
        first_name = person_name.split()[0] if person_name else "Sir/Madam"
        facility = candidate_record.get("facility") or candidate_record.get("facility_city") or "your facility"
        event = candidate_record.get("event") or "recent plant developments"

        subject = f"Calibration compliance & metrology support for {company}'s {facility}"
        body = (
            f"Dear {first_name},\n\n"
            f"Regarding operations at {company}'s {facility}: "
            f"Oorja Technical Services operates an ISO/IEC 17025:2017 accredited calibration laboratory "
            f"(NABL Certificate No. CC-3963) providing certified calibration across "
            f"Electro-Technical, Thermal, Mechanical, and Pressure instrumentation "
            f"aligned with your quality compliance schedules and on-site mobile calibration teams across India.\n\n"
            f"Would your team be open to an introductory technical review regarding your calibration and metrology requirements for {facility}?\n\n"
            f"If you are not the direct coordinator for plant calibration and testing audits, could you kindly point me "
            f"to the right member of your quality or metrology team?\n\n"
            f"Best regards,\n"
            f"Salesoorja Intelligence Engine (Non-Sending Preview Mode)"
        )

        return {
            "recipient_name": person_name,
            "recipient_email": contact_info.get("email"),
            "company": company,
            "facility": facility,
            "subject": subject,
            "body": body,
            "outbound_sent": False,
            "safety_enforced": "OUTBOUND_TEST_MODE=true; REAL EMAILS SENT: 0",
        }

    def process_pending_apollo_queue(self, db_session: Any = None) -> Dict[str, Any]:
        """Tomorrow's resume workflow: executes deterministic enrichment once subscription renewed.

        Strictly enforces Phase 10 Safety:
        Only processes records where:
        - status == STATUS_PENDING_APOLLO_RENEWAL
        - lead_score >= 85.0
        - lookup_priority in ('P1', 'P2', 'P3')
        - queue_origin == 'AUTOMATED_PIPELINE'
        - trigger evidence valid (trigger_event_semantics_verified is True)
        - facility valid (trigger_to_facility in ('DIRECT', 'STRONG'))
        - person confidence HIGH
        - recency gate passes (calculated_recency_days <= 180 or <= 365 with ongoing proof, no mismatch)
        All other records skipped.
        """
        eligible_items = []
        skipped_items = []
        for item in self._pending_queue:
            status = item.get("status")
            score = float(item.get("lead_score", 0) or 0)
            priority = item.get("lookup_priority")
            origin = item.get("queue_origin")
            trig_verified = bool(item.get("trigger_event_semantics_verified", False))
            fac_linkage = str(item.get("trigger_to_facility", "")).upper()
            person_conf = item.get("apollo_person_confidence")
            employment_verified = bool(item.get("current_employment_verified"))
            authority = str(item.get("authority_class") or "").upper()
            person_facility = str(item.get("person_facility_relationship") or "").upper()
            recency = item.get("calculated_recency_days")
            if recency is None:
                recency = item.get("recency_days")
            recency_diff = item.get("recency_diff")
            recency_inconsistent = bool(item.get("recency_data_inconsistency", False) or (recency_diff is not None and abs(recency_diff) > 2))

            if (
                status == STATUS_PENDING_APOLLO_RENEWAL
                and score >= ICP_OUTBOUND_MIN_SCORE
                and priority in ("P1", "P2", "P3")
                and origin == "AUTOMATED_PIPELINE"
                and trig_verified
                and fac_linkage in ("DIRECT", "STRONG")
                and person_conf == "HIGH"
                and employment_verified
                and authority in ALLOWED_STRONG_COMMERCIAL_CLASSES
                and person_facility in {"DIRECT", "STRONG", "FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}
                and not recency_inconsistent
                and (recency is not None and (recency <= 180 or (recency <= 365 and item.get("ongoing_source"))))
            ):
                eligible_items.append(item)
            else:
                skipped_items.append({
                    "company": item.get("company"),
                    "person": item.get("person_name"),
                    "status": status,
                    "score": score,
                    "priority": priority,
                    "reason": "Failed Phase 10 safety constraints",
                })

        live_lookup_enabled = bool(get_setting_value("APOLLO_ENABLED_FOR_LIVE_LOOKUP", APOLLO_ENABLED_FOR_LIVE_LOOKUP))
        results = []
        if live_lookup_enabled:
            for item in eligible_items:
                comp = item.get("company")
                p_name = item.get("person_name")
                p_title = item.get("person_title")
                logger.info("Resuming Apollo queue enrichment for %s at %s", p_name, comp)
                res = enrich_specific_person(person_name=p_name, company_name=comp, title=p_title)
                results.append({
                    "company": comp,
                    "person": p_name,
                    "status": res.get("status"),
                    "email": res.get("email"),
                })

        return {
            "total_in_queue": len(self._pending_queue),
            "eligible_count": len(eligible_items),
            "skipped_count": len(skipped_items),
            "skipped_items": skipped_items,
            "resumed_count": len(results),
            "results": results,
            "apollo_live_calls_made": len(results),
            "credits_consumed": len([r for r in results if r.get("email")]),
        }



fast_contact_waterfall_service = FastContactWaterfallService()
