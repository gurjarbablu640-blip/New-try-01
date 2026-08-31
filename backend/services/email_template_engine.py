"""Oorja HTML Email Composition Engine with Dynamic Metrology Templates.

Provides structured, responsive HTML email rendering with dynamic token substitution
and role-specific value propositions (Quality, Purchase, Maintenance, Management).

Strictly enforces separation of CONTENT from PRESENTATION and embeds compliant
unsubscribe and governance footers.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import html


BASE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{subject}}</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; line-height: 1.6; }
    .container { max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; overflow: hidden; }
    .header { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 24px 32px; color: #ffffff; }
    .header-logo { font-size: 20px; font-weight: 700; color: #38bdf8; letter-spacing: 0.5px; }
    .header-sub { font-size: 13px; color: #94a3b8; margin-top: 4px; }
    .body-content { padding: 32px; font-size: 15px; color: #334155; }
    .highlight-box { background-color: #f0fdf4; border-left: 4px solid #22c55e; padding: 16px; margin: 20px 0; border-radius: 4px; font-size: 14px; color: #166534; }
    .parameter-tag { display: inline-block; background-color: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; margin-right: 6px; margin-bottom: 6px; }
    .cta-button { display: inline-block; background-color: #0284c7; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; font-size: 14px; margin-top: 20px; }
    .footer { background-color: #f1f5f9; padding: 20px 32px; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; text-align: center; }
    .footer a { color: #64748b; text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="header-logo">OORJA TECHNICAL SERVICES</div>
      <div class="header-sub">ISO/IEC 17025:2017 NABL Accredited Calibration Laboratory (CC-3498)</div>
    </div>
    <div class="body-content">
      <p>Dear {{contact_name}},</p>
      
      <p>{{opening_paragraph}}</p>
      
      <div class="highlight-box">
        <strong>Accredited Capabilities for {{company_name}}:</strong><br>
        <div style="margin-top: 8px;">
          {{parameter_tags}}
        </div>
        <p style="margin: 8px 0 0 0; font-size: 13px;">{{value_proposition}}</p>
      </div>

      <p>{{supporting_paragraph}}</p>

      <p style="margin-top: 24px;">
        <a href="{{cta_url}}" class="cta-button">{{cta_text}}</a>
      </p>

      <p style="margin-top: 32px; font-size: 14px; color: #64748b;">
        Best regards,<br>
        <strong>Oorja Technical Services</strong><br>
        Engineering & Industrial Metrology Division<br>
        Pune & Dahej Regional Facilities
      </p>
    </div>
    <div class="footer">
      <p>This message was intended for {{contact_name}} at {{company_name}} regarding industrial calibration and testing compliance.</p>
      <p><a href="{{unsubscribe_url}}">Unsubscribe / Update Preferences</a> | <a href="https://oorja.local/nabl-scope">View NABL Scope</a></p>
    </div>
  </div>
</body>
</html>
"""


def render_html_email(
    company_name: str,
    contact_name: str = "Sir/Madam",
    target_role: str = "Quality",
    trigger_context: str = "Industrial Precision Operations",
    likely_parameters: Optional[list[str]] = None,
    cta_text: str = "Review Our Accredited Scope",
    cta_url: str = "https://oorja.local/contact",
    unsubscribe_url: str = "https://oorja.local/unsubscribe",
) -> Dict[str, str]:
    """Renders customized HTML and plain-text email with role-specific copy."""
    parameters = likely_parameters or ["Dimensional", "Thermal", "Pressure", "Torque"]
    param_html = "".join([f'<span class="parameter-tag">{html.escape(p)}</span>' for p in parameters])
    role_lower = target_role.lower()

    if "quality" in role_lower or "metrology" in role_lower:
        subject = f"NABL Calibration Traceability & Audit Readiness for {company_name}"
        opening = (
            f"As your quality assurance team maintains precision standards at {company_name}, "
            f"ensuring complete measurement traceability and audit readiness across your equipment is vital."
        )
        val_prop = (
            "We provide full ISO/IEC 17025:2017 accredited calibration certificates with documented "
            "measurement uncertainty budgets and CMC values required by IATF 16949 and FDA audits."
        )
        supporting = (
            "Our certified metrology engineers provide fast on-site turnaround to minimize production hold-ups. "
            "Would it be helpful to share our NABL scope of accreditation and schedule a technical review?"
        )

    elif "purchase" in role_lower or "procurement" in role_lower:
        subject = f"Consolidated Calibration Vendor Efficiency for {company_name}"
        opening = (
            f"Managing multiple calibration vendors across separate parameters often introduces "
            f"procurement overhead and scheduling delays for {company_name}."
        )
        val_prop = (
            "Consolidate your mechanical, thermal, electrical, and pressure calibration under a single "
            "accredited SLA with fixed annual rate cards and predictable turnarounds."
        )
        supporting = (
            "We help procurement teams streamline vendor management and lower total calibration spend. "
            "Could we share a comparative commercial rate card for your review?"
        )

    elif "maintenance" in role_lower or "plant" in role_lower:
        subject = f"On-Site Calibration Support & Downtime Reduction for {company_name}"
        opening = (
            f"Minimizing unplanned machine downtime and sensor drift is critical for ongoing plant operations at {company_name}."
        )
        val_prop = (
            "Our mobile calibration units perform on-site parameter verification during your scheduled maintenance "
            "windows, eliminating the need to ship critical equipment off-site."
        )
        supporting = (
            "We offer 48-hour emergency dispatch for production-critical gauges and sensors. "
            "Would you like to explore scheduling an on-site calibration audit?"
        )

    else:  # Management / Executive
        subject = f"Mitigating Measurement Uncertainty & Audit Risk at {company_name}"
        opening = (
            f"Precision measurement and regulatory compliance are essential pillars of operational governance at {company_name}."
        )
        val_prop = (
            "Partnering with an accredited calibration provider safeguards against expensive batch rework, "
            "audit non-conformities, and OEM customer dispute risks."
        )
        supporting = (
            "We work with leading industrial leaders to establish flawless measurement governance. "
            "Would you be open to a brief executive discussion on our SLA guarantees?"
        )

    # Render template
    rendered_html = (
        BASE_HTML_TEMPLATE.replace("{{subject}}", html.escape(subject))
        .replace("{{contact_name}}", html.escape(contact_name))
        .replace("{{company_name}}", html.escape(company_name))
        .replace("{{opening_paragraph}}", opening)
        .replace("{{parameter_tags}}", param_html)
        .replace("{{value_proposition}}", val_prop)
        .replace("{{supporting_paragraph}}", supporting)
        .replace("{{cta_text}}", html.escape(cta_text))
        .replace("{{cta_url}}", cta_url)
        .replace("{{unsubscribe_url}}", unsubscribe_url)
    )

    plain_text = (
        f"Subject: {subject}\n\n"
        f"Dear {contact_name},\n\n"
        f"{opening}\n\n"
        f"Capabilities for {company_name}: {', '.join(parameters)}\n"
        f"{val_prop}\n\n"
        f"{supporting}\n\n"
        f"Best regards,\n"
        f"Oorja Technical Services\n"
        f"ISO/IEC 17025:2017 NABL Accredited Laboratory"
    )

    return {
        "subject": subject,
        "html_content": rendered_html,
        "plain_text_content": plain_text,
        "target_role": target_role,
    }
