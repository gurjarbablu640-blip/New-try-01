"""AI & Rule-based Reply Intent Classifier for incoming prospect responses and delivery bounces."""
import re
from typing import Any, Dict, Optional


def classify_reply_intent(
    subject: Optional[str] = "",
    body: Optional[str] = "",
    from_email: Optional[str] = "",
) -> Dict[str, Any]:
    """
    Classifies incoming prospect email into intent categories:
    - BOUNCE
    - OUT_OF_OFFICE
    - NOT_INTERESTED
    - REQUESTING_QUOTE
    - INTERESTED
    - OBJECTION
    - GENERAL_INQUIRY
    """
    sub = (subject or "").lower()
    content = (body or "").lower()
    combined = f"{sub} \n {content}"

    # 1. Delivery Failure / Bounce Check
    bounce_patterns = [
        r"delivery status notification",
        r"mail delivery failed",
        r"undelivered mail",
        r"550\s+",
        r"554\s+",
        r"user unknown",
        r"recipient address rejected",
        r"mailbox unavailable",
        r"host or domain name not found",
        r"relay access denied",
    ]
    for pat in bounce_patterns:
        if re.search(pat, combined):
            return {
                "category": "BOUNCE",
                "sentiment": "Negative",
                "confidence": 0.98,
                "is_actionable": True,
                "suggested_action": "Mark contact as bounced / invalid email and seek alternate decision maker.",
                "summary": "Automated delivery failure or non-existent mailbox rejection.",
            }

    # 2. Out of Office / Auto-responder
    ooo_patterns = [
        r"out of office",
        r"automatic reply",
        r"auto-reply",
        r"on leave",
        r"away from (the )?office",
        r"will return on",
        r"limited access to email",
        r"contact .* in my absence",
    ]
    for pat in ooo_patterns:
        if re.search(pat, combined):
            return {
                "category": "OUT_OF_OFFICE",
                "sentiment": "Neutral",
                "confidence": 0.95,
                "is_actionable": False,
                "suggested_action": "Pause sequence and retry after prospect returns to office.",
                "summary": "Automated out-of-office vacation or leave notice.",
            }

    # 3. Unsubscribe / Not Interested
    not_interested_patterns = [
        r"unsubscribe",
        r"remove (me|us)",
        r"do not (email|contact|message)",
        r"not interested",
        r"stop (sending|emailing)",
        r"please don't contact",
        r"take (me|us) off (your|the) list",
    ]
    for pat in not_interested_patterns:
        if re.search(pat, combined):
            return {
                "category": "NOT_INTERESTED",
                "sentiment": "Negative",
                "confidence": 0.92,
                "is_actionable": True,
                "suggested_action": "Suppress contact from all future outbound campaigns.",
                "summary": "Prospect explicitly requested removal or stated no interest.",
            }

    # 4. Requesting Quote / RFQ / Commercials
    quote_patterns = [
        r"(send|share|provide|forward|give|email)\s+(us\s+|the\s+)*(quotation|quote|pricing|rates|commercials|proposal|rate card|price list|scope)",
        r"(quotation|quote|pricing|rates|commercials)\s+for",
        r"\brfq\b",
        r"rate per (instrument|sample|calibration|tag|job)",
        r"scope of (work|calibration|testing)",
        r"what is (the |your )?(cost|price|fee|rate)",
        r"send (the )?quote",
    ]
    for pat in quote_patterns:
        if re.search(pat, combined):
            return {
                "category": "REQUESTING_QUOTE",
                "sentiment": "Positive",
                "confidence": 0.90,
                "is_actionable": True,
                "suggested_action": "Draft calibration quotation & commercial proposal in Quotation Intelligence.",
                "summary": "Prospect requested quotation, rate card, or scope pricing.",
            }

    # 5. Interested / Meeting / Call
    interested_patterns = [
        r"interested",
        r"let('s| us) (talk|speak|discuss|connect|meet)",
        r"call (me|us)",
        r"schedule a (call|meeting|demo)",
        r"available (tomorrow|this week|on|next week)",
        r"share (more |further )?details",
        r"send (more |further )?info",
        r"contact (our|my) purchase team",
        r"contact (our|my) quality head",
    ]
    for pat in interested_patterns:
        if re.search(pat, combined):
            return {
                "category": "INTERESTED",
                "sentiment": "Positive",
                "confidence": 0.88,
                "is_actionable": True,
                "suggested_action": "Initiate direct phone call / schedule technical discovery meeting.",
                "summary": "Positive interest indicated; prospect open to discussion or discovery.",
            }

    # 6. Objection / Current Vendor
    objection_patterns = [
        r"already have a vendor",
        r"existing vendor",
        r"under contract",
        r"currently (working|tied up) with",
        r"too expensive",
        r"no requirement currently",
        r"no requirement right now",
        r"contact (us )?next (quarter|year)",
    ]
    for pat in objection_patterns:
        if re.search(pat, combined):
            return {
                "category": "OBJECTION",
                "sentiment": "Neutral",
                "confidence": 0.85,
                "is_actionable": True,
                "suggested_action": "Log existing vendor intel and schedule contract expiry renewal follow-up.",
                "summary": "Prospect raised objection or cited existing calibration vendor contract.",
            }

    # Default fallback
    return {
        "category": "GENERAL_INQUIRY",
        "sentiment": "Neutral",
        "confidence": 0.70,
        "is_actionable": True,
        "suggested_action": "Review email reply in CRM timeline and assign manual follow-up.",
        "summary": "General inquiry or ambiguous response requiring review.",
    }
