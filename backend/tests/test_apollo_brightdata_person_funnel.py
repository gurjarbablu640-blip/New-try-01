from types import SimpleNamespace
from unittest.mock import MagicMock

from services.apollo_adapter import search_apollo_people_candidates
from services.brightdata_linkedin_provider import normalize_linkedin_record
from services.person_intelligence_service import (
    PersonEvidencePacket,
    classify_current_employment,
    classify_facility_relationship,
    discover_people_with_apollo,
    run_contact_fallback_ladder,
    verify_apollo_candidates_with_brightdata,
)
from services.decision_maker_discovery import is_apollo_eligible_lead


TARGET_COMPANY = "Ramkrishna Forgings Limited"


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeProfileProvider:
    def __init__(self, profiles):
        self.profiles = profiles
        self.calls = []

    def get_person_profile(self, linkedin_url):
        self.calls.append(linkedin_url)
        record = self.profiles.get(linkedin_url)
        return {"status": "WORKING" if record else "EMPTY", "record": record}

    def telemetry(self):
        return {"BRIGHTDATA_PROFILE_FETCHES": len(self.calls)}


def verified_candidate(name="Candidate One"):
    return {
        "name": name,
        "funnel_state": "PERSON_VERIFIED_CONTACT_MISSING",
        "bright_profile_verified": True,
        "ready_for_contact_enrichment": True,
        "current_employment": "VERIFIED",
        "facility_relationship": "FACILITY_FUNCTION_OWNER",
        "function_ownership": "STRONG_PLANT_QUALITY_OWNER",
        "authority": "DECISION_MAKER",
        "person_confidence": "HIGH",
        "person_score": 95,
    }


def test_explicit_plant_viii_overrides_same_city_for_plant_v_target():
    result = classify_facility_relationship(
        "Production Manager at RKFL-Plant VIII",
        "Currently at Ramkrishna Forgings in Jamshedpur, Jharkhand.",
        "Plant V / Baliguma",
        "Jamshedpur",
        target_state="Jharkhand",
    )

    assert result == "OTHER_FACILITY_OWNER"


def test_present_target_company_beats_ambiguous_headline():
    result = classify_current_employment(
        "Currently working at Ramkrishna Forgings Limited. Experience: Ramkrishna Forgings Limited | Production Manager | Sep 2024 - Present.",
        "Production Manager at RKFL-Plant VIII",
        TARGET_COMPANY,
    )

    assert result == "VERIFIED"


def test_newer_explicit_other_employer_contradicts_target_present_evidence():
    packet = PersonEvidencePacket(
        candidate_name="Candidate One",
        current_title="Quality Head",
        target_company=TARGET_COMPANY,
    )
    packet.add_source(
        url="https://www.linkedin.com/in/candidate-one",
        title="Quality Head",
        snippet="Experience: Ramkrishna Forgings Limited | Quality Head | 2024 - Present.",
        source_type="LINKEDIN_SEARCH_SNIPPET",
        source_date="2025-01-01",
    )
    packet.add_source(
        url="https://www.linkedin.com/in/candidate-one",
        title="Quality Director",
        snippet="Currently working at Other Manufacturing Limited as Quality Director.",
        source_type="LINKEDIN_PROFILE",
        source_date="2026-09-14",
    )

    packet.derive()

    assert packet.current_employment == "CONTRADICTED"


def test_incomplete_profile_stays_unknown():
    packet = PersonEvidencePacket(
        candidate_name="Candidate One",
        current_title="",
        target_company=TARGET_COMPANY,
    )
    packet.add_source(
        url="https://www.linkedin.com/in/candidate-one",
        title="",
        snippet="",
        source_type="LINKEDIN_PROFILE",
    )

    packet.derive()

    assert packet.current_employment == "UNKNOWN"


def test_apollo_discovery_excludes_contact_fields(monkeypatch):
    monkeypatch.setattr(
        "services.apollo_adapter.settings",
        SimpleNamespace(APOLLO_API_KEY="test-key", APOLLO_API_BASE_URL="https://api.apollo.io/v1"),
    )
    captured = {}

    def request_fn(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return FakeResponse({"people": [{
            "id": "person-1",
            "first_name": "Asha",
            "last_name": "Rao",
            "title": "Plant Quality Head",
            "seniority": "head",
            "city": "Jamshedpur",
            "state": "Jharkhand",
            "linkedin_url": "https://www.linkedin.com/in/asha-rao",
            "email": "must-not-leak@example.com",
            "phone_numbers": [{"sanitized_number": "+910000000000"}],
            "organization": {"name": TARGET_COMPANY},
        }]})

    result = search_apollo_people_candidates(
        TARGET_COMPANY,
        locations=["Jamshedpur", "Jharkhand"],
        max_results=10,
        request_fn=request_fn,
    )

    assert result["status"] == "READY"
    assert result["telemetry"] == {"APOLLO_SEARCH_CALLS": 1, "CONTACT_REVEAL_CALLS": 0}
    assert "email" not in result["candidates"][0]
    assert "phone" not in result["candidates"][0]
    assert captured["json"]["q_organization_names"] == [TARGET_COMPANY]
    assert len(captured["json"]["person_titles"]) > 1
    assert "reveal_personal_emails" not in captured["json"]


def test_apollo_discovery_candidates_are_not_automatically_verified():
    def search_fn(*args, **kwargs):
        return {
            "status": "READY",
            "candidates": [{
                "apollo_id": "person-1",
                "name": "Asha Rao",
                "title": "Plant Quality Head",
                "seniority": "head",
                "company": TARGET_COMPANY,
                "location": "Jamshedpur, Jharkhand",
                "linkedin_url": "https://www.linkedin.com/in/asha-rao",
            }],
            "telemetry": {"APOLLO_SEARCH_CALLS": 1, "CONTACT_REVEAL_CALLS": 0},
        }

    result = discover_people_with_apollo(
        company_name=TARGET_COMPANY,
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        search_fn=search_fn,
    )

    candidate = result["candidates"][0]
    assert candidate["verification_status"] == "PERSON_CANDIDATE"
    assert candidate["ready_for_contact_enrichment"] is False
    assert "current_employment" not in candidate


def test_brightdata_profile_verification_is_bounded_to_three():
    candidates = [
        {
            "name": f"Candidate {index}",
            "title": "Plant Quality Head",
            "company": TARGET_COMPANY,
            "linkedin_url": f"https://www.linkedin.com/in/candidate-{index}",
        }
        for index in range(1, 6)
    ]
    profiles = {
        candidate["linkedin_url"]: normalize_linkedin_record(
            {
                "name": candidate["name"],
                "url": candidate["linkedin_url"],
                "position": "Plant Quality Head",
                "current_company": {"name": TARGET_COMPANY},
                "experience": [{
                    "title": "Plant Quality Head",
                    "company": TARGET_COMPANY,
                    "location": "Plant V, Baliguma",
                    "end_date": "Present",
                }],
            },
            evidence_kind="PROFILE_LOOKUP",
            retrieved_at="2026-09-14T00:00:00+00:00",
        )
        for candidate in candidates
    }
    provider = FakeProfileProvider(profiles)

    result = verify_apollo_candidates_with_brightdata(
        candidates,
        company_name=TARGET_COMPANY,
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        provider=provider,
        max_attempts=5,
    )

    assert result["profile_fetches"] == 3
    assert len(provider.calls) == 3
    assert all(candidate["bright_profile_verified"] for candidate in result["candidates"])


def test_wrong_facility_profile_moves_to_next_candidate():
    first_url = "https://www.linkedin.com/in/wrong-plant"
    second_url = "https://www.linkedin.com/in/right-plant"

    def profile(name, url, location):
        return normalize_linkedin_record(
            {
                "name": name,
                "url": url,
                "position": "Plant Quality Head",
                "current_company": {"name": TARGET_COMPANY},
                "experience": [{
                    "title": "Plant Quality Head",
                    "company": TARGET_COMPANY,
                    "location": location,
                    "end_date": "Present",
                }],
            },
            evidence_kind="PROFILE_LOOKUP",
            retrieved_at="2026-09-14T00:00:00+00:00",
        )

    provider = FakeProfileProvider({
        first_url: profile("Arun Sharma", first_url, "Plant VIII, Jamshedpur"),
        second_url: profile("Asha Rao", second_url, "Plant V, Baliguma"),
    })
    result = verify_apollo_candidates_with_brightdata(
        [
            {"name": "Arun Sharma", "linkedin_url": first_url},
            {"name": "Asha Rao", "linkedin_url": second_url},
        ],
        company_name=TARGET_COMPANY,
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        provider=provider,
    )

    assert [attempt["state"] for attempt in result["attempts"]] == [
        "WRONG_FACILITY",
        "PERSON_VERIFIED_CONTACT_MISSING",
    ]
    assert provider.calls == [first_url, second_url]
    assert result["status"] == "READY"


def test_brightdata_verification_precedes_apollo_enrichment():
    order = []
    linkedin_url = "https://www.linkedin.com/in/asha-rao"
    profile = normalize_linkedin_record(
        {
            "name": "Asha Rao",
            "url": linkedin_url,
            "position": "Plant Quality Head",
            "current_company": {"name": TARGET_COMPANY},
            "experience": [{
                "title": "Plant Quality Head",
                "company": TARGET_COMPANY,
                "location": "Plant V, Baliguma",
                "end_date": "Present",
            }],
        },
        evidence_kind="PROFILE_LOOKUP",
        retrieved_at="2026-09-14T00:00:00+00:00",
    )

    class OrderedProvider(FakeProfileProvider):
        def get_person_profile(self, profile_url):
            order.append("BRIGHT_DATA_VERIFY")
            return super().get_person_profile(profile_url)

    verification = verify_apollo_candidates_with_brightdata(
        [{"name": "Asha Rao", "linkedin_url": linkedin_url}],
        company_name=TARGET_COMPANY,
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        provider=OrderedProvider({linkedin_url: profile}),
    )
    candidate = verification["candidates"][0]
    candidate["ready_for_contact_enrichment"] = True

    run_contact_fallback_ladder(
        [candidate],
        enrich_fn=lambda _: order.append("APOLLO_ENRICH") or {"email": "asha@example.com"},
    )

    assert order == ["BRIGHT_DATA_VERIFY", "APOLLO_ENRICH"]


def test_wrong_candidate_moves_to_next_without_enrichment():
    wrong = verified_candidate("Wrong Plant")
    wrong["funnel_state"] = "WRONG_FACILITY"
    right = verified_candidate("Right Plant")
    calls = []

    result = run_contact_fallback_ladder(
        [wrong, right],
        enrich_fn=lambda candidate: calls.append(candidate["name"]) or {"email": "right@example.com"},
    )

    assert calls == ["Right Plant"]
    assert result["status"] == "CONTACT_FOUND"


def test_verified_contact_missing_moves_to_next_candidate():
    calls = []

    def enrich(candidate):
        calls.append(candidate["name"])
        return {"email": None} if len(calls) == 1 else {"email": "second@example.com"}

    result = run_contact_fallback_ladder(
        [verified_candidate("First"), verified_candidate("Second")],
        enrich_fn=enrich,
    )

    assert calls == ["First", "Second"]
    assert result["attempts"][0]["state"] == "PERSON_VERIFIED_CONTACT_MISSING"
    assert result["status"] == "CONTACT_FOUND"


def test_enrichment_cannot_run_before_all_person_gates():
    candidate = verified_candidate()
    candidate["ready_for_contact_enrichment"] = False
    enrich = MagicMock()

    result = run_contact_fallback_ladder([candidate], enrich_fn=enrich)

    enrich.assert_not_called()
    assert result["status"] == "HOLD_CONTACT_NOT_FOUND"


def test_apollo_gate_requires_opportunity_icp_85():
    eligible, reason = is_apollo_eligible_lead(
        {
            "composite_score": 0.95,
            "current_employment": "VERIFIED",
            "facility_relationship": "FACILITY_FUNCTION_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
        },
        {"linkage_confidence": "DIRECT", "facility_verified": True},
        {"valid_trigger": True},
        {"evidence_level": "NOT_FOUND"},
        opportunity_icp_score=84,
    )

    assert eligible is False
    assert "below 85.0" in reason


def test_no_contact_after_three_candidates_holds():
    enrich = MagicMock(return_value={"email": None, "phone": None})

    result = run_contact_fallback_ladder(
        [verified_candidate(f"Candidate {index}") for index in range(1, 6)],
        enrich_fn=enrich,
        max_attempts=5,
    )

    assert enrich.call_count == 3
    assert result["enrichment_calls"] == 3
    assert result["status"] == "HOLD_CONTACT_NOT_FOUND"
    assert all(attempt["state"] == "PERSON_VERIFIED_CONTACT_MISSING" for attempt in result["attempts"])
