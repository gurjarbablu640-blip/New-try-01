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
    classify_person_source_recency,
    compute_deterministic_person_score,
    create_person_evidence_packet,
    verify_candidate_stage_b,
    is_human_person_candidate,
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

        assert mock_router.search.call_count >= 1
        assert telemetry.get("stage_b_queries_run") >= 1

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


class TestSourceCoverageExpansionAndGroupFallback:
    def test_classify_company_post_and_pdf_documents(self):
        """LinkedIn company posts and PDF reports are classified accurately."""
        assert classify_person_source("https://www.linkedin.com/posts/acme-corp_quality-awards-activity-123") == "COMPANY_PUBLIC_POST"
        assert classify_person_source("https://acme.com/reports/Annual-Report-2025.pdf") == "ANNUAL_REPORT"

    def test_multi_source_evidence_fusion_and_provenance(self):
        """Packet fuses LinkedIn tenure, company post award at plant, and document authority with full provenance."""
        packet = PersonEvidencePacket(
            candidate_name="Ramesh Joshi",
            current_title="Plant Quality Head",
            target_company="Acme Forgings Limited",
            target_facility="Sanand Plant",
            target_city="Sanand",
            target_state="gujarat",
        )
        # Source 1: LinkedIn profile snippet proving current tenure
        packet.add_source(
            url="https://in.linkedin.com/in/ramesh-joshi",
            title="Ramesh Joshi - Plant Quality Head - Acme Forgings | LinkedIn",
            snippet="Plant Quality Head at Acme Forgings Limited. Present. Gujarat, India.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
        )
        # Source 2: Company public post tying person to Sanand plant award
        packet.add_source(
            url="https://www.linkedin.com/posts/acme-forgings_sanand-plant-tpm-award-activity-456",
            title="Acme Forgings honors Sanand facility team",
            snippet="Congratulations to Ramesh Joshi, Quality Lead at our Sanand plant, on achieving TPM Excellence.",
            source_type="COMPANY_PUBLIC_POST",
        )
        packet.derive()

        assert packet.current_employment == "VERIFIED"
        assert packet.facility_relationship in ("FACILITY_FUNCTION_OWNER", "FACILITY_OWNER")
        assert packet.contact_route == "PLANT_SPECIFIC_CONTACT"
        assert len(packet.post_sources) == 1
        assert len(packet.facility_sources) >= 1

    def test_group_level_contact_fallback_classification(self):
        """When plant-specific contact is absent, verified Group Quality Head is assigned GROUP_LEVEL_CONTACT."""
        packet = PersonEvidencePacket(
            candidate_name="P Shankar",
            current_title="Corporate Quality Head",
            target_company="Tube Investments of India Limited",
            target_facility="In Nashik Plant",
            target_city="Nashik",
            target_state="maharashtra",
        )
        packet.add_source(
            url="https://in.linkedin.com/in/p-shankar-479513238",
            title="P Shankar - Head - Quality and NPD - Tube Investments of India Limited | LinkedIn",
            snippet="Head - Quality and NPD at Tube Investments of India Limited. Jan 2018 - Present.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
        )
        packet.derive()

        assert packet.current_employment == "VERIFIED"
        assert packet.facility_relationship == "GROUP_FUNCTION_OWNER"
        assert packet.contact_route == "GROUP_LEVEL_CONTACT"
        # Must NOT be labeled plant-specific contact
        assert packet.contact_route != "PLANT_SPECIFIC_CONTACT"
        assert packet.facility_relationship != "FACILITY_OWNER"

    def test_reject_facility_acronym_with_city(self):
        """Rejects branch/facility acronyms with city names like 'TPI CRSS Nashik'."""
        is_h, reason = is_human_person_candidate("TPI CRSS Nashik", "Tube Investments of India Limited")
        assert not is_h
        assert "acronym" in reason.lower() or "facility" in reason.lower()

    def test_classify_person_source_recency_tiers(self):
        """Classify source recency into CURRENT (<=180d), RECENT (181-365d), OLDER (>365d), UNDATED."""
        tier, days = classify_person_source_recency(source_date="2026-08-15")
        assert tier == "CURRENT"
        assert days is not None and days <= 180

        tier, days = classify_person_source_recency(source_date="2025-11-10")
        assert tier == "RECENT"
        assert days is not None and 181 <= days <= 365

        tier, days = classify_person_source_recency(source_date="2024-03-20")
        assert tier == "OLDER"
        assert days is not None and days > 365

        tier, days = classify_person_source_recency(source_date="")
        assert tier == "UNDATED"
        assert days is None

    def test_old_company_post_alone_cannot_verify_current_employment(self):
        """Old company post (e.g. 2024) alone must NOT create VERIFIED current employment today."""
        packet = PersonEvidencePacket(
            candidate_name="Surendra Gupta",
            current_title="Plant Head",
            target_company="Tube Investments of India Limited",
            target_facility="In Nashik Plant",
            target_city="Nashik",
            target_state="maharashtra",
        )
        packet.add_source(
            url="https://www.linkedin.com/posts/tube-investments_nashik-plant-anniversary-activity-789",
            title="Tube Investments honors Nashik team",
            snippet="Mr. Surendra Gupta, Plant Head at our Nashik plant, addresses the team.",
            source_type="COMPANY_PUBLIC_POST",
            source_date="2024-04-15",
        )
        packet.derive()

        # Facility relationship is recognized from the post
        assert packet.facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
        # BUT current employment must NOT be VERIFIED from old company post alone
        assert packet.current_employment != "VERIFIED"
        assert packet.current_employment in ("UNKNOWN", "PROBABLE")
        # Confidence CANNOT be HIGH (False Ready = 0)
        assert packet.confidence != "HIGH"

    def test_cross_source_current_employment_corroboration(self):
        """Historical company post + fresh LinkedIn profile snippet together verify current employment and facility ownership."""
        packet = PersonEvidencePacket(
            candidate_name="Surendra Gupta",
            current_title="Plant Head",
            target_company="Tube Investments of India Limited",
            target_facility="In Nashik Plant",
            target_city="Nashik",
            target_state="maharashtra",
        )
        # Source A: 2024 company post establishing facility ownership
        packet.add_source(
            url="https://www.linkedin.com/posts/tube-investments_nashik-plant-activity-123",
            title="Tube Investments plant milestones",
            snippet="Surendra Gupta leads operations as Plant Head at the Nashik manufacturing works.",
            source_type="COMPANY_PUBLIC_POST",
            source_date="2024-05-10",
        )
        # Source B: 2026 LinkedIn profile snippet establishing active current tenure
        packet.add_source(
            url="https://in.linkedin.com/in/surendra-gupta-plant-head",
            title="Surendra Gupta - Plant Head - Tube Investments of India Limited | LinkedIn",
            snippet="Plant Head at Tube Investments of India Limited. Jan 2021 - Present · 5 yrs 8 mos. Maharashtra, India.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
            source_date="2026-08-01",
        )
        packet.derive()

        # Both dimensions verified and corroborated
        assert packet.current_employment == "VERIFIED"
        assert packet.facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
        assert packet.cross_source_corroborated is True
        assert packet.contact_route == "PLANT_SPECIFIC_CONTACT"
        assert packet.confidence == "HIGH"
        assert packet.score >= 85.0


class TestCurrentEmploymentCorroborationAndHardening:
    """Rigorous regression tests for current employment evidence corroboration and gates."""

    def test_older_plant_evidence_plus_current_profile_yields_verified(self):
        """Older plant post (facility) + fresh profile with Present (employment) -> VERIFIED + plant link."""
        packet = PersonEvidencePacket(
            candidate_name="Rajesh Patil",
            current_title="Plant Quality Head",
            target_company="Bharat Forge Limited",
            target_facility="Mundhwa Plant",
            target_city="Pune",
            target_state="maharashtra",
        )
        # 2024 company post establishing plant link
        packet.add_source(
            url="https://www.linkedin.com/posts/bharatforge_mundhwa-plant-milestone-111",
            title="Bharat Forge Mundhwa Plant Operational Update",
            snippet="Rajesh Patil, Plant Quality Head at the Mundhwa Pune manufacturing unit, confirmed CMM metrology readiness.",
            source_type="COMPANY_PUBLIC_POST",
            source_date="2024-03-20",
        )
        # 2026 public profile confirming active employment
        packet.add_source(
            url="https://in.linkedin.com/in/rajesh-patil-bf",
            title="Rajesh Patil - Plant Quality Head - Bharat Forge Limited | LinkedIn",
            snippet="Plant Quality Head at Bharat Forge Limited. Jan 2021 - Present · 5 yrs 8 mos. Pune, Maharashtra.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
            source_date="2026-07-15",
        )
        packet.derive()

        assert packet.current_employment == "VERIFIED"
        assert packet.facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
        assert packet.cross_source_corroborated is True
        assert packet.confidence == "HIGH"
        assert packet.score >= 85.0

    def test_older_plant_evidence_alone_yields_not_verified(self):
        """Older plant evidence without a current source remains PROBABLE/UNKNOWN and NOT VERIFIED."""
        packet = PersonEvidencePacket(
            candidate_name="Rajesh Patil",
            current_title="Plant Quality Head",
            target_company="Bharat Forge Limited",
            target_facility="Mundhwa Plant",
            target_city="Pune",
            target_state="maharashtra",
        )
        # Only older 2024 post
        packet.add_source(
            url="https://www.linkedin.com/posts/bharatforge_mundhwa-plant-milestone-111",
            title="Bharat Forge Mundhwa Plant Operational Update",
            snippet="Rajesh Patil, Plant Quality Head at the Mundhwa Pune manufacturing unit, confirmed CMM metrology readiness.",
            source_type="COMPANY_PUBLIC_POST",
            source_date="2024-03-20",
        )
        packet.derive()

        assert packet.current_employment != "VERIFIED"
        assert packet.current_employment in ("UNKNOWN", "PROBABLE")
        assert packet.confidence != "HIGH"

    def test_current_profile_at_another_employer_yields_contradicted(self):
        """Current profile showing another employer yields CONTRADICTED and LOW confidence."""
        packet = PersonEvidencePacket(
            candidate_name="Vikas Sharma",
            current_title="Head Quality",
            target_company="Thermax Limited",
            target_facility="Chinchwad Plant",
            target_city="Pune",
            target_state="maharashtra",
        )
        packet.add_source(
            url="https://in.linkedin.com/in/vikas-sharma-qa",
            title="Vikas Sharma - Head Quality - Crompton Greaves | LinkedIn",
            snippet="Head Quality at Crompton Greaves Consumer Electricals. Experience: Thermax Limited (2015 - 2020 · 5 yrs).",
            source_type="LINKEDIN_SEARCH_SNIPPET",
            source_date="2026-06-10",
        )
        packet.derive()

        assert packet.current_employment == "CONTRADICTED"
        assert packet.confidence == "LOW"

    def test_contradiction_overrides_corroboration(self):
        """Correction 2: Newer conflicting employer strictly overrides older target-company plant evidence."""
        packet = PersonEvidencePacket(
            candidate_name="Nitin Joshi",
            current_title="Plant Head",
            target_company="Endurance Technologies Limited",
            target_facility="Waluj Plant",
            target_city="Aurangabad",
            target_state="maharashtra",
        )
        # Older 2023 plant post mentioning candidate at target facility
        packet.add_source(
            url="https://www.linkedin.com/posts/endurance-tech_waluj-plant-milestone",
            title="Endurance Technologies Waluj Plant Recognition",
            snippet="Nitin Joshi, Plant Head at Waluj Plant Aurangabad, receives excellence award.",
            source_type="COMPANY_PUBLIC_POST",
            source_date="2023-08-15",
        )
        # Newer 2026 profile showing candidate at another company
        packet.add_source(
            url="https://in.linkedin.com/in/nitin-joshi-operations",
            title="Nitin Joshi - Vice President Operations - Varroc Engineering | LinkedIn",
            snippet="Vice President Operations at Varroc Engineering. Jan 2024 - Present · 2 yrs 8 mos. Pune, India.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
            source_date="2026-08-01",
        )
        packet.derive()

        # Contradiction MUST override corroboration
        assert packet.current_employment == "CONTRADICTED"
        assert packet.confidence == "LOW"
        assert packet.cross_source_corroborated is False

    def test_present_marker_at_target_company_yields_verified(self):
        """Explicit 'Present' marker for target company creates VERIFIED current employment."""
        packet = PersonEvidencePacket(
            candidate_name="Sanjay Kulkarni",
            current_title="DGM Quality",
            target_company="Bharat Forge Limited",
            target_facility="Pune Plant",
            target_city="Pune",
        )
        packet.add_source(
            url="https://in.linkedin.com/in/sanjay-kulkarni-bf",
            title="Sanjay Kulkarni - DGM Quality - Bharat Forge Limited | LinkedIn",
            snippet="DGM Quality at Bharat Forge Limited. Nov 2019 – Present · 6 yrs 10 mos. Pune Area, India.",
            source_type="LINKEDIN_SEARCH_SNIPPET",
            source_date="2026-09-01",
        )
        packet.derive()

        assert packet.current_employment == "VERIFIED"

    def test_page_retrieval_date_alone_does_not_verify_employment(self):
        """Correction 3: Fresh page/retrieval date alone without explicit current/present signal is NOT VERIFIED."""
        packet = PersonEvidencePacket(
            candidate_name="Anil Deshmukh",
            current_title="General Manager Quality",
            target_company="Thermax Limited",
            target_facility="Chinchwad Plant",
            target_city="Pune",
        )
        # Retrieved today in 2026, but content is an undated/historical bio without present/currently
        packet.add_source(
            url="https://thermaxglobal.com/news/engineering-symposium-overview",
            title="Thermax Engineering Symposium",
            snippet="Anil Deshmukh, General Manager Quality at Thermax Limited, spoke about industrial boiler fabrication standards.",
            source_type="OFFICIAL_COMPANY_PAGE",
            source_date="2026-09-12",
        )
        packet.derive()

        # Page date alone cannot create VERIFIED
        assert packet.current_employment != "VERIFIED"
        assert packet.current_employment in ("UNKNOWN", "PROBABLE")

    def test_directory_only_evidence_does_not_verify_employment(self):
        """Correction 4: Directory-only sources alone must NOT create VERIFIED current employment."""
        packet = PersonEvidencePacket(
            candidate_name="Mahesh Shinde",
            current_title="Quality Manager",
            target_company="Endurance Technologies Limited",
            target_facility="Waluj Plant",
            target_city="Aurangabad",
        )
        packet.add_source(
            url="https://www.zaubacorp.com/company-officers/ENDURANCE-TECHNOLOGIES/123",
            title="Endurance Technologies Key Officers Directory",
            snippet="Mahesh Shinde is listed as Quality Manager at Endurance Technologies Limited Waluj Unit.",
            source_type="PROFESSIONAL_DIRECTORY",
            source_date="2026-01-10",
        )
        packet.derive()

        assert packet.current_employment != "VERIFIED"
        assert packet.current_employment in ("UNKNOWN", "PROBABLE")
        assert packet.confidence != "HIGH"



