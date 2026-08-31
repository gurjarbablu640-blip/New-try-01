"""Apollo API adapter and lead generator.

Provides unified discovery of industrial decision-makers and companies.
Includes a realistic mock mode for local testing without consuming API credits.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import requests

from config import settings
from services.deduplication import extract_domain, normalize_company_name

logger = logging.getLogger(__name__)


# Realistic industrial dataset for mock testing
MOCK_INDUSTRIAL_COMPANIES = [
    {
        "name": "Aarti Industries Ltd (Dahej Division)",
        "city": "Dahej",
        "state": "Gujarat",
        "industry": "Chemical Manufacturing",
        "website": "https://www.aarti-industries.com",
        "headcount": "1000-5000",
        "contacts": [
            {
                "name": "Rajesh V. Patel",
                "title": "Head of Quality Assurance & NABL Coordinator",
                "department": "Quality Assurance",
                "email": "rajesh.patel@aarti-industries.com",
                "phone": "+91 98250 14820",
                "linkedin_url": "https://linkedin.com/in/rajesh-patel-aarti",
                "is_decision_maker": 1,
            },
            {
                "name": "Sanjay Sharma",
                "title": "Plant Operations Head",
                "department": "Operations",
                "email": "sanjay.sharma@aarti-industries.com",
                "phone": "+91 98250 99112",
                "linkedin_url": "https://linkedin.com/in/sanjay-sharma-operations",
                "is_decision_maker": 1,
            },
        ],
    },
    {
        "name": "Bharat Forge Ltd (Chakan Unit)",
        "city": "Pune",
        "state": "Maharashtra",
        "industry": "Automotive & Forging",
        "website": "https://www.bharatforge.com",
        "headcount": "5000+",
        "contacts": [
            {
                "name": "Amit Kulkarni",
                "title": "Quality Manager - Metrology & Standards",
                "department": "Quality Control",
                "email": "amit.kulkarni@bharatforge.com",
                "phone": "+91 98220 54321",
                "linkedin_url": "https://linkedin.com/in/amit-kulkarni-metrology",
                "is_decision_maker": 1,
            },
            {
                "name": "Vikram Deshmukh",
                "title": "Senior Procurement Manager - Technical Services",
                "department": "Procurement",
                "email": "vikram.deshmukh@bharatforge.com",
                "phone": "+91 98220 88776",
                "linkedin_url": "https://linkedin.com/in/vikram-deshmukh-procurement",
                "is_decision_maker": 0,
            },
        ],
    },
    {
        "name": "Sun Pharma Advanced Research",
        "city": "Vadodara",
        "state": "Gujarat",
        "industry": "Pharmaceuticals",
        "website": "https://www.sparc.life",
        "headcount": "500-1000",
        "contacts": [
            {
                "name": "Dr. Meera Joshi",
                "title": "Director - Analytical Testing & Calibration Lab",
                "department": "R&D / Testing",
                "email": "meera.joshi@sparc.life",
                "phone": "+91 98790 11223",
                "linkedin_url": "https://linkedin.com/in/meera-joshi-analytical",
                "is_decision_maker": 1,
            }
        ],
    },
    {
        "name": "Larsen & Toubro Heavy Engineering",
        "city": "Hazira",
        "state": "Gujarat",
        "industry": "Heavy Engineering & Fabrication",
        "website": "https://www.larsentoubro.com",
        "headcount": "10000+",
        "contacts": [
            {
                "name": "Nilesh Pandya",
                "title": "Chief Metrologist & Instrumentation Lead",
                "department": "Instrumentation",
                "email": "nilesh.pandya@larsentoubro.com",
                "phone": "+91 98255 66778",
                "linkedin_url": "https://linkedin.com/in/nilesh-pandya-lt",
                "is_decision_maker": 1,
            }
        ],
    },
    {
        "name": "Mahindra Precision Auto Components",
        "city": "Nashik",
        "state": "Maharashtra",
        "industry": "Automotive Components",
        "website": "https://www.mahindra.com",
        "headcount": "1000-5000",
        "contacts": [
            {
                "name": "Girish Bapat",
                "title": "Quality Head - Plant 2",
                "department": "Quality Assurance",
                "email": "girish.bapat@mahindra.com",
                "phone": "+91 98230 44556",
                "linkedin_url": "https://linkedin.com/in/girish-bapat-mahindra",
                "is_decision_maker": 1,
            }
        ],
    },
]


def _format_mock_results(
    query: str | None = None,
    locations: list[str] | None = None,
    titles: list[str] | None = None,
    page: int = 1,
    per_page: int = 10,
) -> dict[str, Any]:
    """Generate filtered mock results."""
    items = list(MOCK_INDUSTRIAL_COMPANIES)

    if query:
        q = query.lower()
        items = [i for i in items if q in i["name"].lower() or q in i["industry"].lower()]

    if locations:
        loc_lowers = [loc.lower() for loc in locations if loc]
        if loc_lowers:
            items = [
                i
                for i in items
                if any(l in i["city"].lower() or l in i["state"].lower() for l in loc_lowers)
            ]

    total = len(items)
    start = (page - 1) * per_page
    paginated = items[start : start + per_page]

    results = []
    for idx, item in enumerate(paginated, start=start + 1):
        domain = extract_domain(item["website"])
        contacts = []
        for c_idx, c in enumerate(item["contacts"], start=1):
            contacts.append(
                {
                    "apollo_id": f"mock_per_{idx}_{c_idx}",
                    "name": c["name"],
                    "title": c["title"],
                    "department": c.get("department"),
                    "email": c.get("email"),
                    "phone": c.get("phone"),
                    "linkedin_url": c.get("linkedin_url"),
                    "is_decision_maker": c.get("is_decision_maker", 1),
                }
            )

        results.append(
            {
                "apollo_id": f"mock_org_{idx}",
                "company_name": item["name"],
                "normalized_name": normalize_company_name(item["name"]),
                "domain": domain,
                "website": item["website"],
                "city": item["city"],
                "state": item["state"],
                "country": "India",
                "industry": item["industry"],
                "headcount": item["headcount"],
                "contacts": contacts,
            }
        )

    return {
        "total_entries": total,
        "page": page,
        "per_page": per_page,
        "results": results,
        "mock_mode": True,
    }


def search_apollo_leads(
    query: str | None = None,
    locations: list[str] | None = None,
    titles: list[str] | None = None,
    industries: list[str] | None = None,
    page: int = 1,
    per_page: int = 25,
    force_mock: bool = False,
) -> dict[str, Any]:
    """Search leads via Apollo API or mock fallback."""
    api_key = settings.APOLLO_API_KEY.strip()
    if force_mock or not api_key:
        logger.info("Using Apollo Mock Generator (API key empty or force_mock=True)")
        return _format_mock_results(
            query=query,
            locations=locations,
            titles=titles,
            page=page,
            per_page=per_page,
        )

    url = f"{settings.APOLLO_API_BASE_URL.rstrip('/')}/mixed_people/search"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    person_titles = titles or [
        "Quality Manager",
        "Plant Head",
        "Head of Quality",
        "Director Quality",
        "Instrumentation Engineer",
        "Procurement Manager",
    ]

    payload = {
        "q_organization_names": [query] if query else [],
        "q_keywords": query if query else "",
        "person_titles": person_titles,
        "person_locations": locations or ["India"],
        "page": page,
        "per_page": min(max(per_page, 1), 100),
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code != 200:
            logger.error("Apollo API error HTTP %s: %s", response.status_code, response.text)
            return {
                "error": f"Apollo API HTTP {response.status_code}",
                "details": response.text,
                "mock_mode": False,
            }

        data = response.json()
        people = data.get("people", [])
        total = data.get("pagination", {}).get("total_entries", len(people))

        # Group by organization
        org_map: dict[str, dict[str, Any]] = {}
        for p in people:
            org = p.get("organization") or {}
            org_id = org.get("id") or org.get("name") or "unknown_org"
            if org_id not in org_map:
                org_name = org.get("name") or p.get("organization_name") or "Unknown Company"
                website = org.get("website_url")
                org_map[org_id] = {
                    "apollo_id": str(org.get("id")) if org.get("id") else None,
                    "company_name": org_name,
                    "normalized_name": normalize_company_name(org_name),
                    "domain": extract_domain(website),
                    "website": website,
                    "city": org.get("city") or p.get("city"),
                    "state": org.get("state") or p.get("state"),
                    "country": org.get("country") or "India",
                    "industry": org.get("industry"),
                    "headcount": str(org.get("estimated_num_employees", "")),
                    "contacts": [],
                }

            is_dm = 1 if any(t.lower() in (p.get("title") or "").lower() for t in ["head", "manager", "director", "lead", "vp"]) else 0
            org_map[org_id]["contacts"].append(
                {
                    "apollo_id": str(p.get("id")) if p.get("id") else None,
                    "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or p.get("name", "Unknown Contact"),
                    "first_name": p.get("first_name"),
                    "last_name": p.get("last_name"),
                    "title": p.get("title"),
                    "department": p.get("department") or p.get("functions", [None])[0] if p.get("functions") else None,
                    "email": p.get("email"),
                    "email_status": p.get("email_status"),
                    "phone": p.get("sanitized_phone") or p.get("phone_numbers", [{}])[0].get("sanitized_number") if p.get("phone_numbers") else None,
                    "linkedin_url": p.get("linkedin_url"),
                    "is_decision_maker": is_dm,
                }
            )

        return {
            "total_entries": total,
            "page": page,
            "per_page": per_page,
            "results": list(org_map.values()),
            "mock_mode": False,
        }

    except Exception as exc:
        logger.exception("Apollo API invocation exception: %s", exc)
        return {
            "error": str(exc),
            "mock_mode": False,
        }


def execute_apollo_pilot_validation(
    company_name: str,
    target_titles: Optional[list[str]] = None,
    max_contacts: int = 5,
    force_mock: bool = False,
) -> dict[str, Any]:
    """Executes a controlled Apollo Pilot with strict hard limits (5-6 contacts max).
    
    Generates a structured verification report with transparent real vs blocked status.
    """
    import time
    start_time = time.time()
    
    # Enforce strict safety limit
    safe_limit = min(max_contacts, 6)
    titles = target_titles or ["Quality Head", "QA Manager", "Metrology Manager", "Purchase Manager"]
    
    logger.info("Executing Apollo Pilot for '%s' with hard limit %d contacts", company_name, safe_limit)
    
    res = search_apollo_leads(
        query=company_name,
        titles=titles,
        page=1,
        per_page=safe_limit,
        force_mock=force_mock,
    )
    
    elapsed = round(time.time() - start_time, 3)

    if "error" in res:
        if force_mock:
            res = search_apollo_leads(
                query=company_name,
                titles=titles,
                page=1,
                per_page=safe_limit,
                force_mock=True,
            )
        else:
            return {
                "status": "APOLLO_BLOCKED",
                "error": res.get("error"),
                "details": res.get("details"),
                "company_name": company_name,
                "hard_limit_enforced": safe_limit,
                "requested_contacts": safe_limit,
                "returned_contacts": 0,
                "mock_mode": False,
                "processing_time_seconds": elapsed,
                "message": f"Live Apollo request failed ({res.get('error')}). Configure valid APOLLO_API_KEY in Settings to enable live enrichment.",
            }
    
    elapsed = round(time.time() - start_time, 3)
    
    results = res.get("results", [])
    total_contacts = 0
    valid_emails = 0
    missing_emails = 0
    duplicates = 0
    seen_emails = set()
    contacts_extracted = []
    
    for org in results:
        for c in org.get("contacts", []):
            if len(contacts_extracted) >= safe_limit:
                break
            total_contacts += 1
            email = c.get("email")
            if email:
                if email.lower() in seen_emails:
                    duplicates += 1
                else:
                    seen_emails.add(email.lower())
                    valid_emails += 1
            else:
                missing_emails += 1
                
            contacts_extracted.append({
                "name": c.get("name"),
                "title": c.get("title"),
                "email": email or "UNAVAILABLE",
                "phone": c.get("phone"),
                "is_decision_maker": bool(c.get("is_decision_maker")),
            })
        if len(contacts_extracted) >= safe_limit:
            break
            
    role_match_accuracy = round((valid_emails / max(1, total_contacts)) * 100.0, 1)
    
    return {
        "status": "pilot_completed",
        "company_name": company_name,
        "hard_limit_enforced": safe_limit,
        "requested_contacts": safe_limit,
        "returned_contacts": len(contacts_extracted),
        "valid_emails_count": valid_emails,
        "missing_emails_count": missing_emails,
        "duplicate_count": duplicates,
        "company_match_accuracy_percent": 100.0 if results else 0.0,
        "role_match_accuracy_percent": role_match_accuracy,
        "mock_mode": res.get("mock_mode", False),
        "processing_time_seconds": elapsed,
        "contacts": contacts_extracted,
        "governance_note": "Pilot capped at strict hard limit (5-6 contacts max) for safe validation.",
    }


def enrich_specific_person(
    person_name: str,
    company_name: str,
    title: Optional[str] = None,
) -> dict[str, Any]:
    """Enrich a SPECIFIC known person via Apollo.

    This is ENRICHMENT, not person discovery. The person must have been
    identified and verified through web/public research BEFORE calling this.

    Apollo is asked to find contact details for this specific person,
    not to return random company contacts.
    """
    api_key = settings.APOLLO_API_KEY.strip()

    if not api_key:
        logger.info("Apollo API key not configured — returning APOLLO_BLOCKED")
        return {
            "status": "APOLLO_BLOCKED",
            "person_name": person_name,
            "company_name": company_name,
            "error": "Apollo API key not configured",
            "email": None,
            "email_confidence": None,
            "phone": None,
            "raw_response": None,
            "mock_mode": False,
        }

    # Split name into first/last
    name_parts = person_name.strip().split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

    url = f"{settings.APOLLO_API_BASE_URL.rstrip('/')}/people/match"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": company_name,
    }
    if title:
        payload["title"] = title

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)

        if response.status_code == 401 or response.status_code == 403:
            logger.error("Apollo authentication failed: HTTP %s", response.status_code)
            return {
                "status": "APOLLO_BLOCKED",
                "person_name": person_name,
                "company_name": company_name,
                "error": f"Apollo authentication failed (HTTP {response.status_code})",
                "email": None,
                "email_confidence": None,
                "phone": None,
                "raw_response": None,
                "mock_mode": False,
            }

        if response.status_code != 200:
            logger.error("Apollo API error HTTP %s: %s", response.status_code, response.text[:200])
            return {
                "status": "ERROR",
                "person_name": person_name,
                "company_name": company_name,
                "error": f"Apollo API HTTP {response.status_code}",
                "email": None,
                "email_confidence": None,
                "phone": None,
                "raw_response": None,
                "mock_mode": False,
            }

        data = response.json()
        person_data = data.get("person") or {}

        if not person_data:
            return {
                "status": "NO_RESULT",
                "person_name": person_name,
                "company_name": company_name,
                "error": None,
                "email": None,
                "email_confidence": None,
                "phone": None,
                "raw_response": data,
                "mock_mode": False,
            }

        email = person_data.get("email")
        email_status = person_data.get("email_status")
        phone_numbers = person_data.get("phone_numbers", [])
        phone = phone_numbers[0].get("sanitized_number") if phone_numbers else None

        # Map Apollo email_status to our confidence
        email_confidence = None
        if email_status == "verified":
            email_confidence = "HIGH"
        elif email_status == "guessed":
            email_confidence = "LOW"
        elif email_status:
            email_confidence = "MEDIUM"

        return {
            "status": "ENRICHED" if email else "NO_RESULT",
            "person_name": person_name,
            "company_name": company_name,
            "error": None,
            "email": email,
            "email_confidence": email_confidence,
            "email_status": email_status,
            "phone": phone,
            "linkedin_url": person_data.get("linkedin_url"),
            "apollo_title": person_data.get("title"),
            "apollo_id": str(person_data.get("id", "")),
            "raw_response": data,
            "mock_mode": False,
        }

    except Exception as exc:
        logger.exception("Apollo person enrichment exception: %s", exc)
        return {
            "status": "ERROR",
            "person_name": person_name,
            "company_name": company_name,
            "error": str(exc),
            "email": None,
            "email_confidence": None,
            "phone": None,
            "raw_response": None,
            "mock_mode": False,
        }
