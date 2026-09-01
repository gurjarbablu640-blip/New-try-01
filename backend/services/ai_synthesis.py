"""
Module 10: AI Synthesis - Sales Psychology Outreach Engine
==========================================================
Uses Claude to generate hyper-personalized outreach across all channels.
Sales psychology principles embedded as instructions to Claude.

Every outreach must:
1. Reference something SPECIFIC to that company
2. Open with pain, not your features
3. Include social proof (nearby customer)
4. Have exactly ONE CTA
5. Offer free value before asking for anything
"""
import json
import logging
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.company import Company
from models.outreach_draft import OutreachDraft
from services.personalizationEngine import build_personalization_context
from services.llm_provider import get_orchestrator_provider

logger = logging.getLogger(__name__)


# ============================================================
# CLAUDE SYSTEM PROMPT - Expert B2B Sales Writer
# ============================================================

SALES_SYSTEM_PROMPT = """You are an expert B2B sales writer for Indian industrial markets.
You understand how Plant Heads, Quality Managers, and Purchase Managers think.
Your emails are concise, specific, and trigger immediate replies.
You NEVER write generic emails.

Apply these principles:
1. SPECIFICITY: Always mention a specific instrument, machine, or certification
   found on their website. Generic = trash folder.
2. PAIN BEFORE SOLUTION: Open with their likely problem, not your service features.
3. SOCIAL PROOF: Reference a real or plausible nearby customer.
4. ONE CTA: End with exactly one question or action. Never two.
5. RECIPROCITY: Offer something free (audit, checklist, report) before asking for a meeting.
6. URGENCY: If a trigger exists, reference it naturally.
7. SUBJECT LINE: Must be specific. 'Calibration for your Mitutoyo CMM' beats
   'Our calibration services'.

FORBIDDEN phrases (never use):
  - 'I hope this email finds you well'
  - 'We are a leading provider'
  - 'Please find attached'
  - 'Kindly revert'
  - 'As per our conversation'
  - Any generic opening about your company
  - 'Dear Sir/Madam'
  - 'To whom it may concern'
  - 'I am writing to inform you'
  - 'We would like to introduce'

WHATSAPP RULES:
  - Max 3 sentences
  - Start with their company name or city
  - End with a yes/no question
  - No formal greetings
  - Write like a peer, not a vendor
  - Use casual Hindi-English mix if appropriate for the market

TONE:
  - Confident, not pushy
  - Knowledgeable, not preachy
  - Peer-level, not vendor-level
  - Concise — every word earns its place

Return JSON (strict format, no markdown):
{
  "email_subject_variants": ["5 different subject lines for A/B testing"],
  "email_body": "max 120 words, pain-led, specific, ends with one clear CTA",
  "email_ps": "one PS line offering free value (audit report, checklist, instrument list)",
  "whatsapp_3line": "max 3 sentences, conversational, ends with yes/no question",
  "linkedin_connection_note": "max 300 chars, mention their specific work or certification",
  "call_opener": "2 sentences to say when they pick up the phone — specific and confident",
  "objection_responses": {
    "we_already_have_vendor": "2-sentence response acknowledging, then differentiating",
    "not_interested": "2-sentence pattern interrupt using their specific trigger",
    "send_brochure": "2-sentence redirect to meeting with value offer",
    "call_later": "2-sentence specific callback ask with urgency"
  },
  "followup_day3_whatsapp": "soft follow-up referencing first message, add new data point",
  "followup_day7_email": "value-add email — send free resource related to their instruments",
  "followup_day14_breakup": "breakup email — high reply rate pattern, short, permission-based"
}"""


# ============================================================
# FREE VALUE OFFER PROMPT
# ============================================================

FREE_VALUE_PROMPT = """Based on this company's detected instruments and certifications,
generate a personalized "Calibration Risk Report" outline (1-page PDF concept).

Include:
1. List their detected instruments (from context)
2. Standard calibration intervals for each instrument type
3. Estimated number of instruments likely due for calibration
4. Compliance risk flags if any certification (ISO/NABL) detected
5. A compelling 1-line summary the salesperson can use as the email hook

Format as a structured outline the salesperson can use as their reason to get a reply:
"I've prepared a quick Calibration Risk Report for {company} based on your listed instruments — want me to share it?"

Return JSON:
{
  "report_title": "Calibration Risk Assessment for {Company}",
  "instruments_listed": ["instrument1 - interval", "instrument2 - interval"],
  "estimated_due_count": "X instruments likely due in next 90 days",
  "compliance_risk": "summary of risk based on their certifications",
  "hook_line": "1 sentence the salesperson says to offer the report",
  "full_outline": "Complete 1-page report outline text"
}"""


# ============================================================
# MAIN GENERATION FUNCTION
# ============================================================

def generate_outreach(company_id: int, db: Session = None) -> Dict[str, Any]:
    """
    Generate complete multi-channel outreach for a company.
    Uses personalization context + Claude to create sales-psychology-based messages.

    Returns:
        Dict with all outreach variants and free value offer
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Build personalization context (Module 9)
        context = build_personalization_context(company_id, db)
        if not context:
            logger.error(f"No personalization context for company {company_id}")
            return {"error": "Could not build personalization context"}

        # Generate outreach via LLM / Fallback
        outreach = _call_llm_outreach(context)
        if not outreach:
            outreach = _fallback_outreach(context)

        # Generate free value offer
        free_value = _call_llm_free_value(context)
        if not free_value:
            free_value = _fallback_free_value(context)

        # Save to database
        _save_outreach_draft(company_id, outreach, free_value, context, db)

        # Update company buying window
        company = db.query(Company).filter(Company.id == company_id).first()
        if company and context.get("buying_window"):
            company.buying_window = context["buying_window"]
            db.commit()

        return {
            "outreach": outreach,
            "free_value": free_value,
            "personalization_context": context,
        }

    except Exception as e:
        logger.error(f"Error generating outreach for company {company_id}: {e}")
        return {"error": str(e)}

    finally:
        if close_db:
            db.close()


def _call_llm_outreach(context: dict) -> Optional[dict]:
    """Call configured LLM Provider (Gemini / OpenAI) to generate outreach content."""
    provider = get_orchestrator_provider()
    if not provider or not provider.is_available():
        logger.info("No active LLM provider configured, using deterministic fallback outreach generation")
        return _fallback_outreach(context)

    try:
        user_message = _build_outreach_prompt(context)
        resp = provider.complete(
            system_prompt=SALES_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.2,
            max_tokens=2000,
        )
        parsed = resp.parse_json()
        if parsed:
            return parsed
        return _fallback_outreach(context)
    except Exception as e:
        logger.error(f"LLM outreach generation error: {e}")
        return _fallback_outreach(context)


def _call_llm_free_value(context: dict) -> Optional[dict]:
    """Call configured LLM Provider (Gemini / OpenAI) to generate the free value offer."""
    provider = get_orchestrator_provider()
    if not provider or not provider.is_available():
        return _fallback_free_value(context)

    try:
        user_message = f"""Company: {context.get('company_name', 'Unknown')}
Instruments detected: {', '.join(context.get('specific_instruments', ['general instruments']))}
OEM Brands: {', '.join(context.get('oem_brands', []))}
Certifications: {', '.join(context.get('certifications', []))}
Industry: {context.get('company_industry', 'manufacturing')}
Has NABL: {context.get('has_nabl', False)}

{FREE_VALUE_PROMPT}"""

        resp = provider.complete(
            system_prompt="You are a senior calibration and metrology specialist.",
            messages=[{"role": "user", "content": user_message}],
            temperature=0.2,
            max_tokens=1500,
        )
        parsed = resp.parse_json()
        if parsed:
            return parsed
        return _fallback_free_value(context)
    except Exception as e:
        logger.error(f"LLM free value generation error: {e}")
        return _fallback_free_value(context)


def _build_outreach_prompt(context: Dict) -> str:
    """Build the user prompt with all personalization data."""
    instruments = ", ".join(context.get("specific_instruments", [])) or "not detected"
    brands = ", ".join(context.get("oem_brands", [])) or "not detected"
    certs = ", ".join(context.get("certifications", [])) or "none detected"

    trigger_info = ""
    if context.get("urgency_trigger"):
        trigger = context["urgency_trigger"]
        trigger_info = f"""
ACTIVE BUYING TRIGGER (use this!):
  Type: {trigger.get('type')}
  Reason: {trigger.get('reason')}
  Opportunity: {trigger.get('note')}
  Detected: {trigger.get('detected_at')}"""

    reference = context.get("local_reference") or "a similar company in the region"
    pain = context.get("pain_hook", "")
    dm_name = context.get("decision_maker_name", "")
    dm_title = context.get("decision_maker_designation", "")

    prompt = f"""Generate complete outreach for this company. Make it SPECIFIC — reference their actual instruments/certs.

COMPANY: {context.get('company_name', 'Unknown Company')}
CITY: {context.get('company_city', 'India')}
STATE: {context.get('company_state', '')}
INDUSTRY: {context.get('company_industry', 'manufacturing')}
TIER: {context.get('company_tier', 'Unknown')}
ICP SCORE: {context.get('icp_score', 0)}/100

INSTRUMENTS ON WEBSITE: {instruments}
OEM BRANDS: {brands}
CERTIFICATIONS: {certs}
HAS NABL: {context.get('has_nabl', False)}
EXPORTS: {context.get('export_active', False)}
COMPANY SIZE: {context.get('company_size_signal', 'unknown')}

DECISION MAKER: {dm_name} ({dm_title})
{trigger_info}

PAIN HOOK TO USE: {pain}
NEARBY REFERENCE: {reference}
BUYING WINDOW: {context.get('buying_window', 'unknown')}

Generate the complete outreach JSON now. Remember:
- Subject lines must mention specific instrument or certification
- Email max 120 words, pain-led
- WhatsApp max 3 sentences, casual
- Every message must feel personally written for THIS company"""

    return prompt


# ============================================================
# RESPONSE PARSING
# ============================================================

def _parse_json_response(text: str) -> Optional[Dict]:
    """Parse JSON from Claude's response, handling various formats."""
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in response
    try:
        # Look for ```json ... ```
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
            return json.loads(json_str)
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
            return json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        pass

    # Try to find { ... } block
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        json_str = text[start:end]
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError):
        pass

    logger.warning(f"Could not parse JSON from Claude response: {text[:200]}")
    return None


# ============================================================
# FALLBACK GENERATION (when API key not available)
# ============================================================

def _fallback_outreach(context: Dict) -> Dict:
    """Generate outreach without Claude API (template-based fallback)."""
    company = context.get("company_name", "your company")
    city = context.get("company_city", "your city")
    instruments = context.get("specific_instruments", [])
    certs = context.get("certifications", [])
    pain = context.get("pain_hook", "Instrument accuracy impacts quality outcomes")
    reference = context.get("local_reference", "companies in your area")
    dm_name = context.get("decision_maker_name", "")
    trigger = context.get("urgency_trigger")

    # Build specific subject lines
    instrument_mention = instruments[0] if instruments else "instruments"
    cert_mention = certs[0] if certs else "quality systems"

    subjects = [
        f"Calibration schedule for your {instrument_mention}",
        f"{company} — {cert_mention} compliance check",
        f"Quick question about {company}'s calibration setup",
        f"{instrument_mention} calibration due? Free assessment for {company}",
        f"{city} calibration partner — specialised in {cert_mention}",
    ]

    # Build email body
    email_body = f"""{pain}

We recently helped {reference} streamline their calibration program — reduced turnaround by 40% while keeping full NABL traceability.

For {company}, I've identified {len(instruments) if instruments else 'several'} instrument categories that likely need attention. I've put together a quick Calibration Risk Report specific to your setup.

Would it be useful if I shared it?"""

    # Build WhatsApp
    whatsapp = f"{company}, {city} — saw your {cert_mention} setup. Quick question: do you handle calibration in-house or outsource? — Ravi"

    return {
        "email_subject_variants": subjects,
        "email_body": email_body.strip(),
        "email_ps": f"PS: I have a free Calibration Interval Checklist for {cert_mention} certified labs — happy to share regardless.",
        "whatsapp_3line": whatsapp,
        "linkedin_connection_note": f"Hi{' ' + dm_name.split()[0] if dm_name else ''}, noticed {company}'s {cert_mention} work. We help similar companies in {city} with calibration compliance. Would love to connect.",
        "call_opener": f"Hi, this is Ravi — I was looking at {company}'s instrument list and noticed a few that are likely overdue for calibration. Do you manage that internally or have an AMC partner?",
        "objection_responses": {
            "we_already_have_vendor": f"Understood — many of our clients in {city} started the same way. What made them switch was our 5-day turnaround with doorstep pickup. Worth a comparison quote?",
            "not_interested": f"Fair enough. Just so you know — we identified {len(instruments) if instruments else 'several'} instruments on your site that may be approaching interval. Happy to share the list with no obligation.",
            "send_brochure": f"Sure, but a brochure won't tell you which of your instruments are overdue. Can I share a 1-page risk report specific to {company} instead? Takes 2 minutes to review.",
            "call_later": f"Of course. When specifically works — I want to share the {cert_mention} compliance update before your next audit window. Tuesday or Thursday better?"
        },
        "followup_day3_whatsapp": f"Hi — shared a note about {company}'s calibration setup earlier. Also noticed your {instrument_mention} might need attention. Worth a quick look?",
        "followup_day7_email": f"Following up with something useful — attached is our {cert_mention} Calibration Interval Reference Guide. Shows recommended intervals for all major instrument types. No strings attached.",
        "followup_day14_breakup": f"Last note from me — I'll assume calibration is sorted at {company}. If it ever becomes a priority, I'll be here. Deleting from my follow-up list unless you say otherwise."
    }


def _fallback_free_value(context: Dict) -> Dict:
    """Generate free value offer without Claude API."""
    company = context.get("company_name", "Company")
    instruments = context.get("specific_instruments", ["General instruments"])
    certs = context.get("certifications", [])

    instrument_lines = []
    intervals = {
        "CMM": "6 months",
        "micrometer": "12 months",
        "caliper": "12 months",
        "gauge": "12 months",
        "thermometer": "6 months",
        "pressure": "12 months",
        "multimeter": "12 months",
        "balance": "6 months",
        "hardness": "12 months",
    }

    for inst in instruments[:8]:
        interval = "12 months"
        for key, val in intervals.items():
            if key.lower() in inst.lower():
                interval = val
                break
        instrument_lines.append(f"{inst} — recommended interval: {interval}")

    return {
        "report_title": f"Calibration Risk Assessment for {company}",
        "instruments_listed": instrument_lines,
        "estimated_due_count": f"{max(len(instruments), 3)} instruments likely due in next 90 days",
        "compliance_risk": f"{'NABL/ISO compliance requires documented calibration' if certs else 'Quality system benefit from traceable calibration'}",
        "hook_line": f"I've prepared a quick Calibration Risk Report for {company} based on your listed instruments — want me to share it?",
        "full_outline": f"""CALIBRATION RISK ASSESSMENT — {company}
{'='*50}

1. INSTRUMENTS DETECTED ({len(instruments)} categories):
{chr(10).join('   • ' + line for line in instrument_lines)}

2. RECOMMENDED INTERVALS:
   Based on ISO/IEC 17025 and manufacturer guidelines

3. ESTIMATED DUE COUNT:
   {max(len(instruments), 3)} instruments likely approaching or past calibration interval

4. COMPLIANCE IMPACT:
   {'Certifications: ' + ', '.join(certs) + ' — all require documented calibration proof' if certs else 'Traceable calibration improves quality metrics and audit readiness'}

5. RECOMMENDATION:
   Conduct a baseline calibration audit to identify gaps before next audit cycle.
   Estimated time: 1-2 days on-site.
"""
    }


# ============================================================
# DATABASE SAVE
# ============================================================

def _save_outreach_draft(
    company_id: int,
    outreach: Dict,
    free_value: Optional[Dict],
    context: Dict,
    db: Session
):
    """Save generated outreach to the database."""
    try:
        # Check for existing draft
        existing = db.query(OutreachDraft).filter(
            OutreachDraft.company_id == company_id
        ).first()

        if existing:
            # Update existing
            existing.email_subject = outreach.get("email_subject_variants", [""])[0]
            existing.email_body = outreach.get("email_body", "")
            existing.whatsapp_message = outreach.get("whatsapp_3line", "")
            existing.email_subject_variants = outreach.get("email_subject_variants", [])
            existing.email_ps = outreach.get("email_ps", "")
            existing.call_opener = outreach.get("call_opener", "")
            existing.objection_responses = outreach.get("objection_responses", {})
            existing.linkedin_connection_note = outreach.get("linkedin_connection_note", "")
            existing.followup_day3_whatsapp = outreach.get("followup_day3_whatsapp", "")
            existing.followup_day7_email = outreach.get("followup_day7_email", "")
            existing.followup_day14_breakup = outreach.get("followup_day14_breakup", "")
            existing.free_value_offer_outline = (
                free_value.get("full_outline", "") if free_value else ""
            )
            existing.generation_context = context
        else:
            # Create new
            draft = OutreachDraft(
                company_id=company_id,
                email_subject=outreach.get("email_subject_variants", [""])[0],
                email_body=outreach.get("email_body", ""),
                whatsapp_message=outreach.get("whatsapp_3line", ""),
                email_subject_variants=outreach.get("email_subject_variants", []),
                email_ps=outreach.get("email_ps", ""),
                call_opener=outreach.get("call_opener", ""),
                objection_responses=outreach.get("objection_responses", {}),
                linkedin_connection_note=outreach.get("linkedin_connection_note", ""),
                followup_day3_whatsapp=outreach.get("followup_day3_whatsapp", ""),
                followup_day7_email=outreach.get("followup_day7_email", ""),
                followup_day14_breakup=outreach.get("followup_day14_breakup", ""),
                free_value_offer_outline=(
                    free_value.get("full_outline", "") if free_value else ""
                ),
                generated_by="claude",
                generation_context=context,
            )
            db.add(draft)

        db.commit()
        logger.info(f"Outreach draft saved for company {company_id}")

    except Exception as e:
        logger.error(f"Error saving outreach draft: {e}")
        db.rollback()


# ============================================================
# BATCH GENERATION
# ============================================================

def generate_outreach_batch(company_ids: list, db: Session = None) -> Dict:
    """Generate outreach for multiple companies."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    results = {"success": 0, "failed": 0, "errors": []}

    try:
        for company_id in company_ids:
            try:
                result = generate_outreach(company_id, db)
                if "error" not in result:
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "company_id": company_id,
                        "error": result["error"]
                    })
            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "company_id": company_id,
                    "error": str(e)
                })

        return results

    finally:
        if close_db:
            db.close()
