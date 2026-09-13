"""Targeted unit tests for Two-Stage Person Verification and Multi-Source Evidence Packet.

Tasks 2, 3, 4, 5 verification:
- Stage A: candidate discovery without expected name knowledge.
- Stage B: targeted exact-name verification searches (max 3 per serious candidate).
- PersonEvidencePacket multi-source aggregation across employment, facility, function, authority.
- Source priority and restriction: directory sources alone must NOT create HIGH plant-specific confidence.
"""
from unittest.mock import MagicMock
import pytest

from services.person_intelligence_service import (
    classify_person_source,
    compute_deterministic_person_score,
    create_person_evidence_packet,
    verify_candidate_stage_b,
    PersonEvidencePacket,
)


class TestSourcePriorityAndClassification:
    def test_classify_person_source_professional_directory(self):
        """Directory domains must be classified as PROFESSIONAL_DIRECTORY."""
        dir_urls = [
            "https://in.kompass.com/c/aia-engineering-limited/in771761/",
            "https://www.zaubacorp.com/company/ACME-INDIA/U12345",
            "https://www.indiamart.com/prodfind/company.html",
            "https://www.tofler.in/company/123",
            "https://www.justdial.com/Ahmedabad/Acme/079P",
            "https://www.tradeindia.com/Seller-123",
            "https://rocketreach.co/john-doe-email",
            "https://www.zoominfo.com/c/acme/123",
        ]
        for url in dir_urls:
            stype = classify_person_source(url, company_domain="acme.com")
            assert stype == "PROFESSIONAL_DIRECTORY", f"URL {url} expected PROFESSIONAL_DIRECTORY, got {stype}"

    def test_classify_person_source_official_and_linkedin(self):
        """Official company domain and LinkedIn must receive high-priority source classes."""
        assert classify_person_source("https://acme.com/about-us", company_domain="acme.com") == "OFFICIAL_COMPANY_PAGE"
        assert classify_person_source("https://acme.com/press-releases/new-head", company_domain="acme.com") == "COMPANY_PUBLIC_POST"
        assert classify_person_source("https://in.linkedin.com/in/ravi-sharma-123", company_domain="acme.com") == "LINKEDIN_SEARCH_SNIPPET"

    def test_directory_only_evidence_cannot_create_high_confidence(self):
        """Directory sources alone must NOT create HIGH plant-specific confidence."""
        packet = create_person_evidence_packet(
            candidate_name="Ramesh Patel",
            current_title="Plant Head",
            target_company="Acme Forgings",
            target_facility="Sanand Plant",
            target_city="Sanand",
            initial_source={
                "url": "https://in.kompass.com/c/acme-forgings/123",
                "title": "Acme Forgings Sanand - Ramesh Patel Plant Head",
                "snippet": "Contact Ramesh Patel, Plant Head at Acme Forgings Sanand facility.",
                "source_type": "PROFESSIONAL_DIRECTORY",
            },
        )
        assert packet.confidence != "HIGH", f"Directory alone must never create HIGH confidence, got {packet.confidence}"
        assert packet.confidence in ("LOW", "MEDIUM")
        # Direct plant ownership cannot be awarded from a directory alone
        assert packet.facility_relationship != "FACILITY_OWNER"
        assert packet.facility_relationship == "FUNCTIONALLY_RELEVANT"


class TestPersonEvidencePacketMultiSourceDerivation:
    def test_multi_source_grounding_achieves_high_confidence(self):
        """Independent employment and facility proof from LinkedIn and official sources creates HIGH confidence."""
        packet = PersonEvidencePacket(
            candidate_name="Krishna Kumar Jha",
            current_title="Head Quality",
            target_company="Ramkrishna Forgings Limited",
            target_facility="Plant V Jamshedpur",
            target_city="Jamshedpur",
            target_state="jharkhand",
        )
        # Source 1: LinkedIn profile proving current tenure
        packet.add_source(
            url="https://in.linkedin.com/in/krishna-kumar-jha",
            title="Krishna Kumar Jha - Head Quality - Ramkrishna Forgings | LinkedIn",
            snippet="Head Quality at Ramkrishna Forgings Limited. Jan 2021 - Present · 5 yrs 9 mos. Jamshedpur, Jharkhand.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
        )
        # Source 2: Official press release referencing Plant V
        packet.add_source(
            url="https://ramkrishnaforgings.com/press/plant-v-inauguration",
            title="Ramkrishna Forgings inaugurates Plant V in Jamshedpur",
            snippet="Krishna Kumar Jha, Head of Quality at Plant V Jamshedpur facility, confirmed complete metrology readiness.",
            source_type="OFFICIAL_COMPANY_PAGE",
            company_domain="ramkrishnaforgings.com",
        )
        packet.derive()

        assert packet.current_employment == "VERIFIED"
        assert packet.facility_relationship in ("FACILITY_FUNCTION_OWNER", "FACILITY_OWNER")
        assert packet.confidence == "HIGH"
        assert packet.authority == "DECISION_MAKER"
        assert packet.score >= 85.0

    def test_past_tenure_contradiction_in_evidence_packet(self):
        """Closed historical date range at target company yields CONTRADICTED and LOW confidence."""
        packet = PersonEvidencePacket(
            candidate_name="Himanshu Sharma",
            current_title="Head Electrical Quality",
            target_company="Schneider Electric",
            target_facility="Vadodara Plant",
            target_city="Vadodara",
        )
        packet.add_source(
            url="https://in.linkedin.com/in/himanshu-sharma",
            title="Himanshu Sharma - ABB India | LinkedIn",
            snippet="Head of Electrical Quality at ABB India. Experience: Schneider Electric (Jan 2007 - Nov 2009 · 2 yrs 11 mos) QA Lead.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
        )
        packet.derive()

        assert packet.current_employment == "CONTRADICTED"
        assert packet.confidence == "LOW"
        assert packet.score < 60.0

    def test_conflicting_facility_location_in_evidence_packet(self):
        """Candidate at Dharwad when target plant is Sanand yields OTHER_FACILITY_OWNER."""
        packet = PersonEvidencePacket(
            candidate_name="Avijit Sen",
            current_title="Quality Head",
            target_company="Tata Motors",
            target_facility="Sanand Plant",
            target_city="Sanand",
            target_state="gujarat",
        )
        packet.add_source(
            url="https://in.linkedin.com/in/avijit-sen",
            title="Avijit Sen - Quality Head - Tata Motors | LinkedIn",
            snippet="Quality Head at Tata Motors Dharwad Plant, Karnataka. Dec 2018 - Present.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
        )
        packet.derive()

        assert packet.current_employment == "VERIFIED"
        assert packet.facility_relationship in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED")
        assert packet.confidence == "LOW"


class TestStageBTargetedVerification:
    def test_stage_b_executes_targeted_searches_and_enriches_candidate(self):
        """Stage B searches exact name + company + city up to 3 queries and grounds location."""
        candidate = {
            "name": "Dhiraj Shrivastav",
            "title": "Manager Quality",
            "company": "Tube Investments of India Limited",
            "facility_relationship": "COMPANY_ONLY",
            "current_employment": "PROBABLE",
            "person_confidence": "LOW",
            "person_score": 60.0,
            "source_url": "https://in.linkedin.com/in/dhiraj-s",
            "evidence_snippet": "Sr.Manager Quality at TUBE Investment Of India LTD.",
        }

        # Mock search router that returns Nashik facility proof for targeted query
        mock_router = MagicMock()
        mock_router.search.side_effect = [
            # Query 1: "Dhiraj Shrivastav" "Tube Investments of India Limited"
            {
                "results": [
                    {
                        "url": "https://in.linkedin.com/in/dhiraj-shrivastav-nashik",
                        "title": "Dhiraj Shrivastav - Quality Head - Tube Investments of India Limited | LinkedIn",
                        "snippet": "Head Quality at Tube Investments of India Limited, Nashik Plant, Maharashtra. Jan 2020 - Present.",
                    }
                ]
            },
            # Query 2: "Dhiraj Shrivastav" "Tube Investments of India Limited" "Nashik"
            {
                "results": [
                    {
                        "url": "https://tiindia.com/media/nashik-quality-team",
                        "title": "Tube Investments Nashik Plant Quality Operations",
                        "snippet": "Dhiraj Shrivastav leads the Nashik plant metrology and quality inspection unit.",
                    }
                ]
            },
            # Query 3: site:linkedin.com/in "Dhiraj Shrivastav" "Tube Investments of India Limited"
            {
                "results": []
            },
        ]

        telemetry = {}
        enriched = verify_candidate_stage_b(
            candidate=candidate,
            company_name="Tube Investments of India Limited",
            facility_name="In Nashik Plant",
            city="Nashik",
            search_router=mock_router,
            max_searches=3,
            telemetry=telemetry,
        )

        assert mock_router.search.call_count == 3
        assert telemetry.get("stage_b_queries_run") == 3

        # Candidate should now be verified at Nashik plant!
        assert enriched["current_employment"] == "VERIFIED"
        assert enriched["facility_relationship"] in ("FACILITY_FUNCTION_OWNER", "FACILITY_OWNER")
        assert enriched["person_confidence"] == "HIGH"
        assert enriched["person_score"] >= 85.0
        assert "evidence_packet" in enriched
        assert enriched["evidence_packet"]["employment_sources_count"] >= 1
        assert enriched["evidence_packet"]["facility_sources_count"] >= 1

    def test_stage_b_respects_max_searches_cap(self):
        """Stage B must never exceed max_searches parameter."""
        candidate = {
            "name": "Ravi Kumar Meka",
            "title": "Head QA",
            "company": "Premier Energies Limited",
            "facility_relationship": "COMPANY_ONLY",
            "current_employment": "PROBABLE",
            "person_confidence": "MEDIUM",
            "person_score": 70.0,
            "source_url": "https://in.linkedin.com/in/ravi-kumar-meka",
            "evidence_snippet": "Head QA at Premier Energies Limited.",
        }

        mock_router = MagicMock()
        mock_router.search.return_value = {"results": []}

        enriched = verify_candidate_stage_b(
            candidate=candidate,
            company_name="Premier Energies Limited",
            facility_name="Hyderabad Plant",
            city="Hyderabad",
            search_router=mock_router,
            max_searches=2,  # Strict cap of 2
        )

        assert mock_router.search.call_count == 2


class TestFacilityAliasGenerationAndFallback:
    def test_generate_facility_aliases_precision_and_no_state_only(self):
        """Facility aliases generate precise industrial estate and cluster names, excluding state-only."""
        from services.person_intelligence_service import generate_facility_aliases

        # Case 1: Hosur Plant
        aliases_hosur = generate_facility_aliases("Hosur Plant", "Hosur", "tamil nadu")
        assert "Hosur" in aliases_hosur
        assert "Krishnagiri" in aliases_hosur or "Dharmapuri" in aliases_hosur
        assert "tamil nadu" not in [a.lower() for a in aliases_hosur]
        assert "Tamil Nadu" not in aliases_hosur

        # Case 2: Kongara Kalan Facility Hyderabad
        aliases_hyd = generate_facility_aliases("Kongara Kalan Facility", "Hyderabad", "telangana")
        assert "Kongara Kalan" in aliases_hyd
        assert "Hyderabad" in aliases_hyd
        assert "Rangareddy" in aliases_hyd
        assert "telangana" not in [a.lower() for a in aliases_hyd]

        # Case 3: In Nashik Plant
        aliases_nashik = generate_facility_aliases("In Nashik Plant", "Nashik", "maharashtra")
        assert "Nashik" in aliases_nashik
        assert "Nashik MIDC" in aliases_nashik
        assert "maharashtra" not in [a.lower() for a in aliases_nashik]

    def test_multi_candidate_fallback_skips_contradicted_candidate(self):
        """When candidate 1 is contradicted, multi-candidate fallback selects candidate 2 with facility proof."""
        from services.person_intelligence_service import discover_and_rank_decision_makers

        mock_router = MagicMock()
        mock_router.search.side_effect = [
            # Initial search queries return 2 candidates
            {
                "results": [
                    {
                        "url": "https://in.linkedin.com/in/dhiraj-s",
                        "title": "Dhiraj Shrivastav - Sr.Manager Quality - Tube Investments | LinkedIn",
                        "snippet": "Sr.Manager Quality at TUBE Investment Of India LTD. Located in Ahmedabad.",
                    },
                    {
                        "url": "https://in.linkedin.com/in/sachin-k",
                        "title": "Sachin Kumar - Head Quality - Tube Investments | LinkedIn",
                        "snippet": "Head Quality at Tube Investments of India Limited, Nashik Plant, Maharashtra.",
                    },
                ]
            },
            # Stage B Query 1 for candidate 1 (Dhiraj) -> returns Ahmedabad (contradicted)
            {
                "results": [
                    {
                        "url": "https://in.linkedin.com/in/dhiraj-s",
                        "title": "Dhiraj Shrivastav - Tube Investments Ahmedabad",
                        "snippet": "Dhiraj Shrivastav is Quality Head at Ahmedabad unit.",
                    }
                ]
            },
            # Stage B Query 1 for candidate 2 (Sachin) -> returns Nashik (verified)
            {
                "results": [
                    {
                        "url": "https://in.linkedin.com/in/sachin-k",
                        "title": "Sachin Kumar - Tube Investments Nashik Plant",
                        "snippet": "Sachin Kumar is Head Quality at Nashik Plant, MIDC Sinnar.",
                    }
                ]
            },
        ]

        result = discover_and_rank_decision_makers(
            company_name="Tube Investments of India Limited",
            facility_name="In Nashik Plant",
            city="Nashik",
            search_router=mock_router,
            max_candidates=5,
            use_deepseek=False,
        )

        primary = result.get("primary_person")
        assert primary is not None
        # Candidate 2 (Sachin Kumar) should be chosen as primary because Candidate 1 was contradicted!
        assert "Sachin" in primary["name"]
        assert primary["facility_relationship"] in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")

