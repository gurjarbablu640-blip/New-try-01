"""Rerank Dixon Candidates following Forensic Audit.
Compares:
- Rakesh Sharma (disqualified due to ambiguous/former/location mismatch)
- Abhinav Tiwaari (Head of Quality)
- Kamal Nayan Chaturvedi (Quality Manager)
- Lakshmipathy Karanam Natarajan (Manufacturing Operations - Chennai, Tamil Nadu)
- Sanjay Kumar Sharma (AGM Operations / Quality)
- Lalit Kumar (Plant Head & GM Operations)
"""
import json
from services.decision_maker_discovery import rank_calibration_candidates, classify_company_evidence

facility_info = {
    "city": "Chennai",
    "address": "Oragadam Industrial Corridor, Near Chennai, Tamil Nadu",
    "state": "Tamil Nadu",
}

trigger_info = {
    "title": "MoU with Tamil Nadu Government to establish new Laptop & PC Manufacturing Plant in Oragadam, Chennai",
    "date": "2026-01-02",
    "confidence": "DIRECT",
}

candidates = [
    {
        "candidate_name": "Rakesh Sharma",
        "candidate_title": "AVP Operations (Plant Head)",
        "company_name": "Dixon Technologies India Limited",
        "location": "Noida, Uttar Pradesh",
        "source_url": "https://in.linkedin.com/in/rakesh-sharma-b82767166",
        "evidence_snippet": "My past experiences are: 1). Dixon technologies (GM Plant head) 2). Pacific cyber technology. Bajaj Auto elevates Rakesh Sharma.",
        "recency": "Jul 2019 - Present",
    },
    {
        "candidate_name": "Abhinav Tiwaari",
        "candidate_title": "Head of Quality",
        "company_name": "Dixon Technologies India Limited",
        "location": "India",
        "source_url": "https://in.linkedin.com/in/abhinav-tiwaari-6a714b1a",
        "evidence_snippet": "Six Sigma Green Belt & SCRUM Master Certified, Quality Head Dixon Technologies. Head of Quality. Dixon Technologies India Limited. Aug 2025 - Present. Measurement systems, QA/QC, testing standards.",
        "recency": "Aug 2025 - Present",
    },
    {
        "candidate_name": "Kamal Nayan Chaturvedi",
        "candidate_title": "Quality Manager",
        "company_name": "Dixon Technologies India Limited",
        "location": "India",
        "source_url": "https://in.linkedin.com/in/kamal-nayan-chaturvedi-483b02130",
        "evidence_snippet": "Quality Manager at Dixon Technologies || Six Sigma Yellow Belt & Green Belt || ex Vivo Mobile || ex Hafele. Dixon Technologies India Limited. Inspection and testing standards.",
        "recency": "2024-2026",
    },
    {
        "candidate_name": "Lakshmipathy Karanam Natarajan",
        "candidate_title": "Senior Management Professional in Manufacturing Operations",
        "company_name": "Dixon Technologies India Limited",
        "location": "Chennai, Tamil Nadu",
        "source_url": "https://in.linkedin.com/in/lakshmipathy-karanam-natarajan-a7099535",
        "evidence_snippet": "Senior Management Professional in Manufacturing Operations. Dixon Technologies India Limited National Institute of Technology Calicut. Chennai, Tamil Nadu. Plant operations, SMT lines, facility ramp.",
        "recency": "2025-2026",
    },
    {
        "candidate_name": "Sanjay Kumar Sharma",
        "candidate_title": "AGM Operations",
        "company_name": "Dixon Technologies India Limited",
        "location": "India",
        "source_url": "https://in.linkedin.com/in/sanjay-kumar-sharma-88840237",
        "evidence_snippet": "AGM Operations at Dixon Technologies India Limited. A competent professional with 20 years experience in Quality Department in Manufacturing.",
        "recency": "2024-2026",
    },
    {
        "candidate_name": "Lalit Kumar",
        "candidate_title": "Plant Head & General Manager - Operations",
        "company_name": "Dixon Technologies India Limited",
        "location": "India",
        "source_url": "https://in.linkedin.com/in/lalit-kumar-988856154",
        "evidence_snippet": "Plant Head & General Manager Operations. Dixon Technologies India Limited. 5 years 7 months. Plant Head.",
        "recency": "2024-2026",
    }
]

print("=== COMPANY EVIDENCE CLASSIFICATION CHECK ===")
for c in candidates:
    ev = classify_company_evidence(c["candidate_name"], c["evidence_snippet"], "Dixon Technologies")
    print(f"Candidate: {c['candidate_name']}")
    print(f"  Status: {ev['company_evidence_status']} | Current: {ev['is_current_employee']} | Reason: {ev['reason']}")

print("\n=== CANDIDATE RANKING ===")
ranked = rank_calibration_candidates(candidates, facility_info, trigger_info, target_company_name="Dixon Technologies")
for i, r in enumerate(ranked, 1):
    print(f"[{i}] {r['candidate_name']} ({r['candidate_title']})")
    print(f"    Function: {r['function']} | Class: {r['hierarchy_class']}")
    print(f"    Company Verified: {r['current_company_verified']} ({r['company_evidence_status']})")
    print(f"    Facility Link: {r['facility_link']}")
    print(f"    Score: {r['functional_ownership_score']}/100")
    print(f"    Breakdown: {r['score_breakdown']}")
    print()
