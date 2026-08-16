"""Email validation service.

Provides deterministic multi-tier email deliverability and syntax checks:
1. Syntax validation (RFC 5322 regex)
2. Disposable domain detection
3. Role-based address detection (e.g. info@, sales@)
4. DNS MX record resolution (passive, non-intrusive)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

ROLE_PREFIXES = {
    "admin",
    "info",
    "support",
    "sales",
    "contact",
    "help",
    "marketing",
    "office",
    "inquiry",
    "enquiry",
    "general",
    "careers",
    "hr",
    "billing",
    "accounts",
    "service",
    "team",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "tempmail.com",
    "10minutemail.com",
    "guerrillamail.com",
    "sharklasers.com",
    "getairmail.com",
    "throwawaymail.com",
    "yopmail.com",
    "trashmail.com",
    "mytemp.email",
    "dispostable.com",
    "burnermail.io",
    "temp-mail.org",
    "fakeinbox.com",
    "inboxkitten.com",
    "mailnesia.com",
    "emailondeck.com",
}


def _load_extra_disposable_domains() -> set[str]:
    path = settings.DISPOSABLE_DOMAINS_FILE
    if not os.path.isabs(path):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        path = os.path.join(base_dir, path)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(d.strip().lower() for d in data if d)
        except Exception as e:
            logger.warning("Could not load disposable email domains from %s: %s", path, e)
    return set()


ALL_DISPOSABLE_DOMAINS = DISPOSABLE_DOMAINS.union(_load_extra_disposable_domains())


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower()


def check_mx_records(domain: str) -> tuple[bool, list[str], str]:
    """Check DNS MX records for a domain without sending emails."""
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(domain, "MX", lifetime=4.0)
        mx_hosts = [str(r.exchange).rstrip(".") for r in answers]
        if mx_hosts:
            return True, mx_hosts, "MX records found"
        return False, [], "No MX records returned"
    except ImportError:
        # Fallback to basic socket hostname lookup if dnspython is not loaded
        import socket

        try:
            socket.gethostbyname(domain)
            return True, [domain], "Domain resolves via A record (fallback)"
        except socket.error as e:
            return False, [], f"Domain host resolution failed: {e}"
    except Exception as exc:
        return False, [], f"DNS lookup failed: {exc}"


def validate_email_address(email: str | None) -> dict[str, Any]:
    """Validate a single email address."""
    clean = normalize_email(email)
    if not clean:
        return {
            "email": email,
            "normalized_email": None,
            "status": "invalid",
            "reason": "Email address is empty",
            "is_valid": False,
            "is_disposable": False,
            "is_role_account": False,
            "has_mx_records": False,
            "mx_hosts": [],
            "verified_at": datetime.utcnow().isoformat(),
        }

    if not EMAIL_REGEX.match(clean):
        return {
            "email": email,
            "normalized_email": clean,
            "status": "invalid",
            "reason": "Malformed email syntax",
            "is_valid": False,
            "is_disposable": False,
            "is_role_account": False,
            "has_mx_records": False,
            "mx_hosts": [],
            "verified_at": datetime.utcnow().isoformat(),
        }

    user_part, domain_part = clean.split("@", 1)

    is_role = user_part.lower() in ROLE_PREFIXES
    is_disposable = domain_part.lower() in ALL_DISPOSABLE_DOMAINS

    if is_disposable:
        return {
            "email": email,
            "normalized_email": clean,
            "status": "invalid",
            "reason": "Disposable email provider detected",
            "is_valid": False,
            "is_disposable": True,
            "is_role_account": is_role,
            "has_mx_records": False,
            "mx_hosts": [],
            "verified_at": datetime.utcnow().isoformat(),
        }

    has_mx, mx_hosts, mx_reason = check_mx_records(domain_part)

    if not has_mx:
        return {
            "email": email,
            "normalized_email": clean,
            "status": "invalid",
            "reason": f"No valid mail server: {mx_reason}",
            "is_valid": False,
            "is_disposable": False,
            "is_role_account": is_role,
            "has_mx_records": False,
            "mx_hosts": [],
            "verified_at": datetime.utcnow().isoformat(),
        }

    status = "risky" if is_role else "valid"
    reason = "Role-based address on active domain" if is_role else "Valid format and active MX records"

    return {
        "email": email,
        "normalized_email": clean,
        "status": status,
        "reason": reason,
        "is_valid": status in {"valid", "risky"},
        "is_disposable": False,
        "is_role_account": is_role,
        "has_mx_records": True,
        "mx_hosts": mx_hosts,
        "verified_at": datetime.utcnow().isoformat(),
    }


def validate_email_batch(emails: list[str]) -> list[dict[str, Any]]:
    """Validate a batch of emails."""
    return [validate_email_address(e) for e in emails]
