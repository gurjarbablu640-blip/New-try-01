import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.brightdata_linkedin_provider import (
    BrightDataLinkedInProvider,
    normalize_linkedin_record,
)
from services.decision_maker_discovery import enrich_candidate_via_apollo
from services.person_intelligence_service import (
    discover_people_with_brightdata,
    qualify_brightdata_person_records,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)


def provider_settings(credential):
    return SimpleNamespace(
        BRIGHTDATA_API_TOKEN=credential,
        BRIGHTDATA_LINKEDIN_PEOPLE_SEARCH_DATASET_ID="people_dataset",
        BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID="profile_dataset",
        BRIGHTDATA_API_BASE_URL="https://api.brightdata.test",
        BRIGHTDATA_TIMEOUT_SECONDS=5,
        BRIGHTDATA_POLL_TIMEOUT_SECONDS=5,
        BRIGHTDATA_CACHE_TTL_SECONDS=3600,
    )


def normalized_record(
    *,
    name="Amit Kulkarni",
    title="Plant Quality Head",
    company="Ramkrishna Forgings Limited",
    location="Jamshedpur, Jharkhand",
    experience_location="Plant V, Baliguma",
    evidence_kind="PEOPLE_SEARCH",
):
    return normalize_linkedin_record(
        {
            "id": name.casefold().replace(" ", "-"),
            "name": name,
            "url": f"https://in.linkedin.com/in/{name.casefold().replace(' ', '-')}",
            "position": title,
            "city": location,
            "current_company": {"name": company},
            "experience": [{
                "title": title,
                "company": company,
                "location": experience_location,
                "start_date": "2023",
                "end_date": "Present",
            }],
        },
        evidence_kind=evidence_kind,
        retrieved_at="2026-09-14T00:00:00+00:00",
    )


def test_missing_configuration_uses_no_network(tmp_path):
    session = FakeSession([])
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(""),
        session=session,
        cache_path=tmp_path / "cache.json",
    )

    result = provider.search_people(company="Ramkrishna Forgings Limited")

    assert result["status"] == "CONFIG_REQUIRED"
    assert result["records"] == []
    assert session.calls == []
    assert result["telemetry"]["BRIGHTDATA_REQUESTS"] == 0


def test_people_search_is_one_company_first_request_and_normalizes(tmp_path):
    credential = f"credential-{tmp_path.name}"
    session = FakeSession([
        FakeResponse(200, {"hits": [
            {
                "id": "quality-leader",
                "name": "Amit Kulkarni",
                "url": "https://in.linkedin.com/in/amit-kulkarni/?trk=public_profile",
                "position": "Plant Quality Head",
                "city": "Jamshedpur",
                "current_company": {"name": "Ramkrishna Forgings Limited"},
                "experience": [{
                    "title": "Plant Quality Head",
                    "company": "Ramkrishna Forgings Limited",
                    "location": "Plant V, Baliguma",
                    "end_date": "Present",
                }],
            },
            {
                "id": "junior",
                "name": "Ravi Singh",
                "url": "https://www.linkedin.com/in/ravi-singh",
                "position": "Quality Engineer",
                "current_company": {"name": "Ramkrishna Forgings Limited"},
            },
        ]}),
    ])
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(credential),
        session=session,
        cache_path=tmp_path / "cache.json",
        clock=lambda: 1_789_344_000,
    )

    result = provider.search_people(
        company="Ramkrishna Forgings Limited",
        facility="Plant V / Baliguma",
        city="Jamshedpur",
    )

    assert result["status"] == "WORKING"
    assert len(session.calls) == 1
    assert session.calls[0]["url"].endswith("/datasets/search/people_dataset")
    request_filter = session.calls[0]["json"]["filter"]
    assert request_filter == {
        "name": "current_company_name",
        "operator": "includes",
        "value": "Ramkrishna Forgings Limited",
    }
    assert session.calls[0]["json"]["size"] == 10
    assert result["records"][0]["name"] == "Amit Kulkarni"
    assert result["records"][0]["linkedin_url"] == "https://www.linkedin.com/in/amit-kulkarni"
    assert result["records"][0]["source"] == "BRIGHTDATA_LINKEDIN"
    assert "ready_for_contact_enrichment" not in result["records"][0]
    assert result["telemetry"]["BRIGHTDATA_REQUESTS"] == 1
    assert result["telemetry"]["BRIGHTDATA_RECORDS"] == 2


def test_cache_avoids_duplicate_brightdata_request(tmp_path):
    credential = f"credential-{tmp_path.name}"
    session = FakeSession([FakeResponse(200, {"hits": [{
        "name": "Amit Kulkarni",
        "url": "https://www.linkedin.com/in/amit-kulkarni",
        "position": "Plant Quality Head",
        "current_company": {"name": "Ramkrishna Forgings Limited"},
    }]})])
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(credential),
        session=session,
        cache_path=tmp_path / "cache.json",
        clock=lambda: 1_789_344_000,
    )

    first = provider.search_people(company="Ramkrishna Forgings Limited")
    second = provider.search_people(company="Ramkrishna Forgings Limited")

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(session.calls) == 1
    assert second["telemetry"]["BRIGHTDATA_REQUESTS"] == 1
    assert second["telemetry"]["BRIGHTDATA_CACHE_HITS"] == 1


def test_http_error_is_sanitized_and_token_never_leaks(tmp_path, caplog):
    credential = f"credential-{tmp_path.name}"
    session = FakeSession([FakeResponse(401, {"error": credential})])
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(credential),
        session=session,
        cache_path=tmp_path / "cache.json",
    )

    result = provider.search_people(company="Ramkrishna Forgings Limited")
    serialized = json.dumps(result) + repr(provider) + caplog.text

    assert result["status"] == "AUTH_ERROR"
    assert credential not in serialized


def test_people_search_reports_no_match_for_422(tmp_path):
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(f"credential-{tmp_path.name}"),
        session=FakeSession([FakeResponse(422, {"error": "no matches"})]),
        cache_path=tmp_path / "cache.json",
    )

    result = provider.search_people(company="Ramkrishna Forgings Limited")

    assert result["status"] == "NO_MATCH"
    assert result["error"] == {
        "code": "NO_MATCH",
        "stage": "people_search",
        "http_status": 422,
    }


def test_people_search_reports_brightdata_server_error_for_5xx(tmp_path):
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(f"credential-{tmp_path.name}"),
        session=FakeSession([FakeResponse(500, {"error": "internal"})]),
        cache_path=tmp_path / "cache.json",
    )

    result = provider.search_people(company="Ramkrishna Forgings Limited")

    assert result["status"] == "BRIGHTDATA_SERVER_ERROR"
    assert result["error"] == {
        "code": "BRIGHTDATA_SERVER_ERROR",
        "stage": "people_search",
        "http_status": 500,
    }


def test_profile_lookup_supports_async_snapshot(tmp_path):
    credential = f"credential-{tmp_path.name}"
    session = FakeSession([
        FakeResponse(202, {"snapshot_id": "snapshot_one"}),
        FakeResponse(200, {"status": "ready"}),
        FakeResponse(200, [{
            "name": "Amit Kulkarni",
            "url": "https://www.linkedin.com/in/amit-kulkarni",
            "position": "Plant Quality Head",
            "current_company": {"name": "Ramkrishna Forgings Limited"},
        }]),
    ])
    provider = BrightDataLinkedInProvider(
        settings_obj=provider_settings(credential),
        session=session,
        cache_path=tmp_path / "cache.json",
        monotonic=MagicMock(side_effect=[0, 0]),
    )

    result = provider.get_person_profile("https://in.linkedin.com/in/amit-kulkarni/?trk=test")

    assert result["status"] == "WORKING"
    assert result["record"]["evidence_kind"] == "PROFILE_LOOKUP"
    assert [call["method"] for call in session.calls] == ["POST", "GET", "GET"]
    assert session.calls[-1]["url"].endswith("/datasets/v3/snapshot/snapshot_one")
    assert result["telemetry"]["BRIGHTDATA_REQUESTS"] == 3
    assert result["telemetry"]["BRIGHTDATA_PROFILE_FETCHES"] == 1


class FakeProvider:
    def __init__(self, records, profiles=None, search_status="WORKING"):
        self.records = records
        self.profiles = profiles or {}
        self.search_status = search_status
        self.profile_calls = []

    def search_people(self, **kwargs):
        return {"status": self.search_status, "records": self.records}

    def get_person_profile(self, linkedin_url):
        self.profile_calls.append(linkedin_url)
        record = self.profiles.get(linkedin_url)
        return {"status": "WORKING" if record else "EMPTY", "record": record}

    def telemetry(self):
        return {
            "BRIGHTDATA_REQUESTS": 0,
            "BRIGHTDATA_RECORDS": 0,
            "BRIGHTDATA_CACHE_HITS": 0,
            "BRIGHTDATA_PROFILE_FETCHES": len(self.profile_calls),
        }


def test_empty_people_result_becomes_hold_without_profile_calls():
    provider = FakeProvider([])

    result = discover_people_with_brightdata(
        company_name="Ramkrishna Forgings Limited",
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        provider=provider,
    )

    assert result["status"] == "HOLD"
    assert result["candidates"] == []
    assert provider.profile_calls == []


def test_profile_is_not_called_when_search_evidence_is_sufficient():
    record = normalized_record()
    provider = FakeProvider([record])

    result = discover_people_with_brightdata(
        company_name="Ramkrishna Forgings Limited",
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        provider=provider,
    )

    assert result["candidates"][0]["current_employment"] == "VERIFIED"
    assert result["candidates"][0]["facility_relationship"] == "FACILITY_FUNCTION_OWNER"
    assert provider.profile_calls == []


def test_profile_fetches_only_top_two_candidates_when_needed():
    records = [
        normalized_record(
            name=name,
            title="Quality Manager",
            company="",
            experience_location="",
        )
        for name in ("Amit Kulkarni", "Ravi Singh", "Sanjay Sharma")
    ]
    provider = FakeProvider(records)

    discover_people_with_brightdata(
        company_name="Ramkrishna Forgings Limited",
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
        provider=provider,
    )

    assert len(provider.profile_calls) == 2


def test_newer_current_other_employer_overrides_search_evidence():
    search_record = normalized_record()
    profile_record = normalized_record(
        company="Other Manufacturing Limited",
        evidence_kind="PROFILE_LOOKUP",
    )

    candidate = qualify_brightdata_person_records(
        [search_record, profile_record],
        company_name="Ramkrishna Forgings Limited",
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
    )

    assert candidate["current_employment"] == "CONTRADICTED"
    assert candidate["verification_status"] == "PERSON_REJECTED"
    assert candidate["ready_for_contact_enrichment"] is False


def test_general_city_location_does_not_create_direct_facility_proof():
    record = normalized_record(experience_location="")

    candidate = qualify_brightdata_person_records(
        [record],
        company_name="Ramkrishna Forgings Limited",
        facility_name="Plant V / Baliguma",
        city="Jamshedpur",
        state="Jharkhand",
    )

    assert candidate["location"] == "Jamshedpur, Jharkhand"
    assert candidate["facility_relationship"] == "FUNCTIONALLY_RELEVANT"
    assert candidate["function_ownership"] == "STRONG_PLANT_QUALITY_OWNER"
    assert candidate["facility_verified"] is False


def test_apollo_requires_contact_enrichment_ready_status():
    candidate = MagicMock()
    candidate.verification_status = "PERSON_PUBLICLY_VERIFIED"
    candidate.verification_confidence = 0.99
    db = MagicMock()

    with patch("services.apollo_adapter.enrich_specific_person") as apollo:
        result = enrich_candidate_via_apollo(candidate, "Ramkrishna Forgings Limited", db)

    assert result["status"] == "SKIPPED"
    apollo.assert_not_called()
    db.commit.assert_not_called()
