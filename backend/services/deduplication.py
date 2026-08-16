"""Multi-vector deduplication and lead normalization engine.

Provides deterministic matching across:
1. Apollo Organization ID
2. Canonical Root Domain (e.g. aarti-industries.com)
3. Contact Email (existing person record)
4. Normalized Company Name + City
"""
from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

import tldextract
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from services.email_validator import normalize_email, validate_email_address

LEGAL_SUFFIXES = [
    r"\bpvt\.?\s*ltd\.?\b",
    r"\bprivate\s+limited\b",
    r"\bltd\.?\b",
    r"\blimited\b",
    r"\bllp\b",
    r"\binc\.?\b",
    r"\bcorp\.?\b",
    r"\bcorporation\b",
    r"\bco\.?\b",
    r"\bcompany\b",
    r"\bindia\b",
]


def normalize_company_name(name: str | None) -> str:
    """Normalize company name by stripping legal suffixes, punctuation, and extra whitespace."""
    if not name:
        return ""
    text = name.strip().lower()
    for suffix in LEGAL_SUFFIXES:
        text = re.sub(suffix, " ", text, flags=re.IGNORECASE)
    # Replace & with and
    text = re.sub(r"&", " and ", text)
    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_domain(website_or_url: str | None) -> str | None:
    """Extract canonical root domain from website URL or email."""
    if not website_or_url:
        return None
    raw = website_or_url.strip()
    if "@" in raw:
        raw = raw.split("@")[-1]
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    try:
        extracted = tldextract.extract(raw)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain.lower()}.{extracted.suffix.lower()}"
    except Exception:
        pass
    try:
        parsed = urlparse(raw)
        hostname = parsed.hostname or ""
        hostname = hostname.removeprefix("www.")
        return hostname.lower() if hostname else None
    except Exception:
        return None


def normalize_phone_number(phone: str | None) -> str | None:
    """Normalize phone numbers to standard 10-digit or E.164 format."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("91") and len(digits) == 12:
        return f"+91{digits[2:]}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+91{digits[1:]}"
    if len(digits) == 10:
        return f"+91{digits}"
    if digits:
        return f"+{digits}" if not phone.startswith("+") else phone.strip()
    return phone.strip()


def find_company_duplicate(
    db: Session,
    name: str,
    domain: str | None = None,
    city: str | None = None,
    email: str | None = None,
    apollo_id: str | None = None,
) -> tuple[Optional[Company], str, float]:
    """Search for existing company duplicate across multiple match vectors.

    Returns:
        (matching_company, match_reason, confidence_percentage)
    """
    # Vector 1: Apollo ID
    if apollo_id:
        match = db.query(Company).filter(Company.apollo_id == apollo_id).first()
        if match:
            return match, "apollo_id_match", 100.0

    # Vector 2: Canonical Domain
    clean_domain = domain or extract_domain(name) if "@" in name or "." in name else domain
    if clean_domain:
        match = db.query(Company).filter(func.lower(Company.domain) == clean_domain.lower()).first()
        if match:
            return match, "domain_match", 95.0

    # Vector 3: Contact Email
    clean_email = normalize_email(email)
    if clean_email:
        person_match = (
            db.query(Person)
            .filter(
                or_(
                    func.lower(Person.email) == clean_email,
                    func.lower(Person.normalized_email) == clean_email,
                )
            )
            .first()
        )
        if person_match and person_match.company_id:
            company = db.query(Company).filter(Company.id == person_match.company_id).first()
            if company:
                return company, "contact_email_match", 90.0

    # Vector 4: Normalized Name + City
    norm_name = normalize_company_name(name)
    if norm_name:
        query = db.query(Company).filter(
            or_(
                func.lower(Company.normalized_name) == norm_name,
                func.lower(Company.name) == name.strip().lower(),
            )
        )
        if city:
            city_query = query.filter(func.lower(Company.city) == city.strip().lower())
            match = city_query.first()
            if match:
                return match, "name_and_city_match", 85.0
        match = query.first()
        if match:
            return match, "name_match", 75.0

    return None, "no_match", 0.0


def ingest_or_merge_lead(
    db: Session,
    company_data: dict[str, Any],
    contacts_data: list[dict[str, Any]] | None = None,
    auto_validate_emails: bool = True,
) -> tuple[Company, list[Person], str]:
    """Ingest a new lead or merge/enrich into an existing company record.

    Returns:
        (company, list_of_attached_persons, action_taken)
        action_taken is one of: 'CREATED', 'MERGED'
    """
    raw_name = (company_data.get("name") or company_data.get("company_name") or "Unknown Company").strip()
    norm_name = normalize_company_name(raw_name)
    domain = company_data.get("domain") or extract_domain(company_data.get("website"))
    city = company_data.get("city")
    state = company_data.get("state")
    country = company_data.get("country", "India")
    industry = company_data.get("industry")
    source = company_data.get("source", "manual")
    apollo_id = company_data.get("apollo_id")
    primary_email = company_data.get("email")

    existing_company, reason, confidence = find_company_duplicate(
        db,
        name=raw_name,
        domain=domain,
        city=city,
        email=primary_email,
        apollo_id=apollo_id,
    )

    action = "CREATED"
    if existing_company:
        action = "MERGED"
        company = existing_company
        # Non-destructive enrichment
        if not company.domain and domain:
            company.domain = domain
        if not company.normalized_name and norm_name:
            company.normalized_name = norm_name
        if not company.city and city:
            company.city = city
        if not company.state and state:
            company.state = state
        if not company.industry and industry:
            company.industry = industry
        if not company.website and company_data.get("website"):
            company.website = company_data.get("website")
        if not company.phone and company_data.get("phone"):
            company.phone = normalize_phone_number(company_data.get("phone"))
        if not company.apollo_id and apollo_id:
            company.apollo_id = apollo_id
    else:
        company = Company(
            name=raw_name,
            normalized_name=norm_name,
            domain=domain,
            city=city,
            state=state,
            country=country,
            industry=industry,
            website=company_data.get("website"),
            phone=normalize_phone_number(company_data.get("phone")),
            email=normalize_email(primary_email),
            address=company_data.get("address"),
            source=source,
            apollo_id=apollo_id,
            qualification_status=company_data.get("qualification_status", "RAW"),
            lead_status="New",
        )
        db.add(company)
        db.flush()

    attached_persons: list[Person] = []
    if contacts_data:
        for c in contacts_data:
            contact_email = normalize_email(c.get("email"))
            contact_phone = normalize_phone_number(c.get("phone"))
            contact_name = (c.get("name") or c.get("full_name") or "").strip()

            # Deduplicate person within this company
            existing_person = None
            if contact_email:
                existing_person = (
                    db.query(Person)
                    .filter(
                        Person.company_id == company.id,
                        or_(
                            func.lower(Person.email) == contact_email,
                            func.lower(Person.normalized_email) == contact_email,
                        ),
                    )
                    .first()
                )
            elif contact_name:
                existing_person = (
                    db.query(Person)
                    .filter(
                        Person.company_id == company.id,
                        func.lower(Person.full_name) == contact_name.lower(),
                    )
                    .first()
                )

            if existing_person:
                # Update missing fields
                if not existing_person.phone and contact_phone:
                    existing_person.phone = contact_phone
                    existing_person.normalized_phone = contact_phone
                if not existing_person.designation and c.get("designation"):
                    existing_person.designation = c.get("designation")
                if not existing_person.linkedin_url and c.get("linkedin_url"):
                    existing_person.linkedin_url = c.get("linkedin_url")
                attached_persons.append(existing_person)
            else:
                ver_status = "unverified"
                ver_reason = None
                if auto_validate_emails and contact_email:
                    v_res = validate_email_address(contact_email)
                    ver_status = v_res["status"]
                    ver_reason = v_res["reason"]

                person = Person(
                    company_id=company.id,
                    full_name=contact_name or "Unknown Contact",
                    designation=c.get("designation") or c.get("title"),
                    department=c.get("department"),
                    seniority_level=c.get("seniority_level") or c.get("seniority"),
                    email=contact_email,
                    normalized_email=contact_email,
                    phone=contact_phone,
                    normalized_phone=contact_phone,
                    linkedin_url=c.get("linkedin_url"),
                    apollo_id=c.get("apollo_id"),
                    email_verification_status=ver_status,
                    email_verification_reason=ver_reason,
                    is_decision_maker=int(c.get("is_decision_maker", 0)),
                )
                db.add(person)
                db.flush()
                attached_persons.append(person)

    return company, attached_persons, action
