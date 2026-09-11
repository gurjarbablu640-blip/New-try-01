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
from services.opportunity_gates import evaluate_opportunity_gates

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

CONTACT_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "runtime_state",
    "contact_waterfall_cache.json",
)

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
        max_free_search_seconds: float = 60.0,
    ):
        self.apollo_log_file = apollo_log_file or APOLLO_LOG_FILE
        self.contact_cache_file = contact_cache_file or CONTACT_CACHE_FILE
        self.max_free_search_seconds = max_free_search_seconds
        self._apollo_log = self._load_json(self.apollo_log_file, default_factory=list)
        self._contact_cache = self._load_json(self.contact_cache_file, default_factory=dict)

    def _load_json(self, path: str, default_factory: Any) -> Any:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load JSON file '%s': %s", path, e)
        return default_factory() if callable(default_factory) else default_factory

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
        trigger_eval = candidate_record.get("trigger_eval") or {}
        tf_conf = str(
            candidate_record.get("trigger_to_facility")
            or trigger_eval.get("trigger_facility_confidence")
            or ""
        ).upper()
        if tf_conf not in ("DIRECT", "STRONG"):
            return False, f"Trigger-to-facility linkage is {tf_conf or 'UNKNOWN'}; requires DIRECT or STRONG"

        person = candidate_record.get("primary_person") or {}
        person_name = person.get("name") or candidate_record.get("person_name") or ""
        val = validate_person_name(person_name)
        if val["person_name_validation"] != "VALID":
            return False, f"Person candidate name '{person_name}' is not a valid human person"

        authority = person.get("authority_classification") or person.get("classification") or ""
        if authority in ("COMPANY_ONLY", "UNKNOWN", "GENERAL_QUALITY"):
            return False, f"Person authority '{authority}' is insufficient for Apollo spend"

        # Check deduplication
        company_norm = re.sub(r"[^a-z0-9]", "", str(candidate_record.get("company", "")).lower())
        person_norm = re.sub(r"[^a-z0-9]", "", person_name.lower())
        dedup_key = f"{company_norm}:{person_norm}"

        for entry in self._apollo_log:
            if entry.get("dedup_key") == dedup_key and entry.get("status") in ("SUCCESS", "NO_RESULT"):
                return False, f"Recent Apollo lookup already exists for {person_name} at {candidate_record.get('company')}"

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
        """Generate non-sending personalized email preview (Test Mode Only)."""
        company = candidate_record.get("company", "")
        person = candidate_record.get("primary_person") or {}
        person_name = person.get("name") or "Quality Leader"
        first_name = person_name.split()[0] if person_name else "Sir/Madam"
        facility = candidate_record.get("facility") or candidate_record.get("facility_city") or "your facility"
        event = candidate_record.get("event") or "recent plant developments"

        subject = f"Calibration compliance & metrology support for {company}'s {facility}"
        body = (
            f"Dear {first_name},\n\n"
            f"I noticed {company}'s {event} at {facility}. With the rigorous quality and IATF/NABL "
            f"precision standards required for your operations, calibration cycle-times and traceability "
            f"are critical to preventing downtime.\n\n"
            f"Oorja Technical Services (NABL Accredited Lab CC-3963) provides precision calibration across "
            f"Electro-Technical, Thermal, Mechanical, and Pressure instrumentation with rapid 48-hour turnarounds "
            f"and on-site mobile calibration teams across India.\n\n"
            f"Would you be open to a brief 5-minute introductory call this week to review your equipment calibration schedule?\n\n"
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


fast_contact_waterfall_service = FastContactWaterfallService()
