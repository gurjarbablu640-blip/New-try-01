"""Document Intelligence Engine for Technical Brochures, Directories, and Public PDFs.

Routing:
- Simple/fast PDFs -> lightweight pypdf parser
- Complex/structured PDFs -> Docling parser (if enabled/injected)

Extracts:
- Person name & designation
- Email
- Phone (classified)
- Company name & exact facility/location
- Calibration-relevant evidence & triggers

Results are cached by SHA256 and deduplicated against CRM.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from services.contact_confidence import classify_phone_number
from services.document_extraction import (
    extract_local_pdf_with_docling,
    extract_pdf_bytes,
    ExtractionResult,
)
from services.email_validator import EMAIL_REGEX, ROLE_PREFIXES

logger = logging.getLogger(__name__)

_DOCUMENT_CACHE: Dict[str, Dict[str, Any]] = {}

CALIBRATION_TRIGGER_KEYWORDS = [
    "expansion", "commissioning", "new plant", "machining bay", "modernization",
    "iso/iec 17025", "iso 9001", "iatf 16949", "audit", "nabl renewal",
    "tender", "procurement", "annual maintenance", "amc", "quality assurance",
    "metrology lab", "testing laboratory", "calibration scope", "uncertainty",
]

CALIBRATION_INSTRUMENT_KEYWORDS = [
    "cmm", "coordinate measuring machine", "pressure gauge", "caliper", "micrometer",
    "dial gauge", "multimeter", "oscilloscope", "thermocouple", "rtd",
    "dead weight tester", "torque wrench", "optical comparator", "profile projector",
    "surface roughness tester", "hardness tester", "weighing balance",
]

INDIAN_INDUSTRIAL_CITIES = [
    "Dahej", "Hazira", "Sanand", "Vadodara", "Ahmedabad", "Surat", "Ankleshwar", "Bharuch",
    "Pune", "Chakan", "Bhosari", "Talegaon", "Aurangabad", "Nashik", "Nagpur", "Mumbai",
    "Chennai", "Coimbatore", "Hosur", "Sriperumbudur", "Oragadam",
    "Bengaluru", "Bangalore", "Peenya", "Bommasandra",
    "Indore", "Pithampur", "Dewas", "Bhopal", "Gwalior",
    "Gurugram", "Gurgaon", "Manesar", "Faridabad", "Noida", "Greater Noida", "Baddi", "Pantnagar",
    "Jamshedpur", "Kolkata", "Howrah", "Rourkela", "Visakhapatnam", "Hyderabad"
]


def hash_document_bytes(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def extract_entities_from_text(text: str, filename: str = "") -> Dict[str, Any]:
    """Extract structured sales intelligence entities from extracted text."""
    clean_text = text or ""
    lines = clean_text.splitlines()

    # 1. Emails
    raw_emails = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", clean_text))
    valid_emails = [e.lower() for e in raw_emails if EMAIL_REGEX.fullmatch(e.lower()) and not e.lower().endswith((".invalid", ".test"))]

    # 2. Phones
    raw_phones = set(re.findall(r"(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}|\b0\d{2,4}[\s-]?\d{6,8}\b", clean_text))
    phones = [classify_phone_number(p, clean_text) for p in raw_phones]

    # 3. Person Names and Designations
    persons = []
    role_pattern = re.compile(
        r"\b(quality|metrology|calibration|qa|qc|plant|maintenance|operations|purchase|procurement|technical|engineering|lab)\s+"
        r"(head|manager|director|lead|coordinator|in-charge|incharge|officer|engineer|vp|general manager)\b",
        re.I,
    )
    for line in lines:
        line_clean = line.strip()
        if not line_clean or len(line_clean) > 200:
            continue
        role_match = role_pattern.search(line_clean)
        if role_match:
            # Check for name nearby in the line or prefix
            name_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", line_clean)
            name = name_match.group(1) if name_match else None
            role = role_match.group(0).title()
            if name and not any(w.lower() in name.lower() for w in ["limited", "company", "private", "directorate", "department"]):
                persons.append({
                    "name": name,
                    "designation": role,
                    "line_context": line_clean,
                })

    # 4. Facilities and Locations
    locations = []
    for city in INDIAN_INDUSTRIAL_CITIES:
        if re.search(r"(?<!\w)" + re.escape(city) + r"(?!\w)", clean_text, re.I):
            locations.append(city)

    # 5. Plant / Unit references
    plants = []
    plant_matches = re.finditer(r"\b(?:plant|unit|works|facility)\s*[-:]?\s*(\d+|[A-Z]+|[A-Za-z]+)\b", clean_text, re.I)
    for m in plant_matches:
        plants.append(m.group(0))

    # 6. Triggers and Project Events
    triggers_found = []
    for trig in CALIBRATION_TRIGGER_KEYWORDS:
        if re.search(r"(?<!\w)" + re.escape(trig) + r"(?!\w)", clean_text, re.I):
            triggers_found.append(trig)

    # 7. Calibration Evidence
    instruments_found = []
    for inst in CALIBRATION_INSTRUMENT_KEYWORDS:
        if re.search(r"(?<!\w)" + re.escape(inst) + r"(?!\w)", clean_text, re.I):
            instruments_found.append(inst)

    return {
        "persons": persons,
        "emails": valid_emails,
        "phones": phones,
        "locations": list(dict.fromkeys(locations)),
        "plants": list(dict.fromkeys(plants)),
        "triggers": triggers_found,
        "instruments": instruments_found,
        "has_calibration_demand": bool(triggers_found or instruments_found),
    }


def analyze_document(
    file_bytes: bytes,
    filename: str = "document.pdf",
    *,
    force_docling: bool = False,
    docling_converter: Any = None,
    db: Any = None,
) -> Dict[str, Any]:
    """Analyze a document using adaptive fast-pypdf or structured Docling extraction.

    Results are cached in memory by SHA-256 and deduplicated against CRM if db is supplied.
    """
    doc_hash = hash_document_bytes(file_bytes)
    if doc_hash in _DOCUMENT_CACHE and not force_docling:
        cached = _DOCUMENT_CACHE[doc_hash]
        return {**cached, "cache_hit": True}

    # Step 1: Decision on Parser
    # If force_docling is False, run fast lightweight parser first
    extraction: Optional[ExtractionResult] = None
    adapter_used = "pypdf"

    if not force_docling and (filename.lower().endswith(".pdf") or file_bytes.startswith(b"%PDF")):
        lightweight_res = extract_pdf_bytes(file_bytes, filename)
        # If extraction produced adequate text without uncertainty, use it
        if lightweight_res.status == "SUCCESS" and len(lightweight_res.text.strip()) > 100:
            extraction = lightweight_res
            adapter_used = "pypdf"

    # Step 2: If lightweight failed, was uncertain, or force_docling requested:
    if extraction is None:
        # Write to temporary file to pass to Docling
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        try:
            docling_res = extract_local_pdf_with_docling(
                tmp_path,
                enabled=True,
                converter=docling_converter,
            )
            if docling_res.status == "SUCCESS":
                extraction = docling_res
                adapter_used = "docling"
            else:
                # Fallback to lightweight parser if docling is disabled or unavailable
                extraction = extract_pdf_bytes(file_bytes, filename)
                adapter_used = f"pypdf_fallback_after_{docling_res.status.lower()}"
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    extracted_text = extraction.text if extraction else ""
    entities = extract_entities_from_text(extracted_text, filename)

    # Step 3: Deduplicate findings against existing CRM
    crm_matches = []
    if db:
        try:
            from models.person import Person
            from models.company import Company

            for email in entities["emails"]:
                p = db.query(Person).filter(Person.normalized_email == email.lower()).first()
                if p:
                    crm_matches.append({"type": "PERSON", "email": email, "id": p.id, "name": p.full_name, "company_id": p.company_id})

            for loc in entities["locations"]:
                companies_in_loc = db.query(Company).filter(Company.city.ilike(f"%{loc}%")).limit(3).all()
                for co in companies_in_loc:
                    crm_matches.append({"type": "COMPANY_FACILITY", "city": loc, "company_id": co.id, "company_name": co.name})
        except Exception as e:
            logger.warning("CRM deduplication check error: %s", e)

    result = {
        "document_hash": doc_hash,
        "filename": filename,
        "adapter_used": adapter_used,
        "status": extraction.status if extraction else "FAILED",
        "text_length": len(extracted_text),
        "entities": entities,
        "crm_dedup_matches": crm_matches,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "cache_hit": False,
    }

    _DOCUMENT_CACHE[doc_hash] = result
    return result
