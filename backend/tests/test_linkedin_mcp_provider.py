"""Comprehensive unit and integration tests for LinkedIn MCP Provider (stickerdaniel/linkedin-mcp-server).

Verifies strict safety boundaries:
1. Deny-by-default on all unknown tools.
2. Mutation/action tools (connect_with_person, send_message) are blocked locally before network dispatch.
3. Server states: DISABLED, SERVER_UNAVAILABLE, LOGIN_REQUIRED, MANUAL_BROWSER_ACTION_REQUIRED, RATE_LIMITED, READY.
4. Profile location != DIRECT facility ownership (Correction 1).
5. Unseeded decision-maker discovery: control person name is not injected (Correction 2).
6. Newer other-employer experience overrides older Present (Correction 7).
7. Separate reporting for FUNCTION_VERIFIED and AUTHORITY_VERIFIED (Correction 8).
8. Clean fallback to public Serper research on MCP failure without lowering gates (Correction 11).
"""
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest
import requests

from services.linkedin_mcp_provider import (
    LinkedInMCPProvider,
    LinkedInMCPActionBlockedError,
    LinkedInMCPAuthError,
    LinkedInMCPRateLimitError,
    LinkedInMCPUnavailableError,
    READ_ONLY_ALLOWLIST,
    BLOCKED_ACTION_TOOLS,
    SENIOR_AUTHORITY_ROLE_ORDER,
)


def _mock_response(payload=None, *, status_code=200, headers=None):
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = "" if payload is None else __import__("json").dumps(payload)
    response.json.return_value = payload or {}
    return response


def _successful_handshake(final_response):
    initialize_response = _mock_response(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-03-26",
                "serverInfo": {"name": "mcp-server-linkedin", "version": "4.24.0"},
                "capabilities": {},
            },
        },
        headers={"mcp-session-id": "test-session"},
    )
    initialized_response = _mock_response(status_code=202)
    return [initialize_response, initialized_response, final_response]


@pytest.fixture
def provider():
    """Create test provider instance with explicit test endpoint."""
    return LinkedInMCPProvider(
        endpoint_url="http://127.0.0.1:8765/mcp",
        enabled=True,
        timeout_seconds=5,
        max_candidates=3,
    )


class TestLinkedInMCPSafetyAndAllowlist:
    """Verify strict read-only boundary and local deny-by-default enforcement."""

    def test_disabled_by_default(self):
        """When disabled, provider must report DISABLED without network traffic."""
        disabled_provider = LinkedInMCPProvider(enabled=False)
        assert disabled_provider.enabled is False
        status = disabled_provider.get_status()
        assert status["status"] == "DISABLED"

    def test_unknown_mcp_tool_denied_by_default(self, provider):
        """Any unapproved third-party tool must default to BLOCKED immediately."""
        with patch("requests.post") as mock_post:
            with pytest.raises(LinkedInMCPActionBlockedError) as exc_info:
                provider.invoke_tool("some_unknown_mutation_tool", {"foo": "bar"})
            assert "not in the Salesoorja LinkedIn MCP read-only allowlist" in str(exc_info.value)
            mock_post.assert_not_called()

    def test_mutation_tools_strictly_blocked_before_network_dispatch(self, provider):
        """Mutation tools like connect_with_person and send_message must be blocked locally."""
        with patch("requests.post") as mock_post:
            # 1. connect_with_person
            with pytest.raises(LinkedInMCPActionBlockedError):
                provider.invoke_tool("connect_with_person", {"profile_url": "https://linkedin.com/in/test"})

            # 2. send_message
            with pytest.raises(LinkedInMCPActionBlockedError):
                provider.invoke_tool("send_message", {"profile_url": "https://linkedin.com/in/test", "message": "hello"})

            # 3. like_post / comment_on_post
            with pytest.raises(LinkedInMCPActionBlockedError):
                provider.invoke_tool("like_post", {"post_urn": "urn:li:activity:123"})
            with pytest.raises(LinkedInMCPActionBlockedError):
                provider.invoke_tool("comment_on_post", {"post_urn": "urn:li:activity:123", "comment": "great"})

            # No network call must ever have taken place
            mock_post.assert_not_called()

    def test_allowlist_contains_only_read_tools(self):
        """Verify allowlist strictly contains read tools only."""
        assert "connect_with_person" not in READ_ONLY_ALLOWLIST
        assert "send_message" not in READ_ONLY_ALLOWLIST
        assert "like_post" not in READ_ONLY_ALLOWLIST
        assert "comment_on_post" not in READ_ONLY_ALLOWLIST
        assert "get_company_profile" in READ_ONLY_ALLOWLIST
        assert "get_person_profile" in READ_ONLY_ALLOWLIST
        assert "search_people" in READ_ONLY_ALLOWLIST
        assert "get_company_employees" in READ_ONLY_ALLOWLIST

    def test_structured_content_is_preferred_for_typed_tool_results(self, provider):
        payload = {"url": "https://www.linkedin.com/company/example/", "sections": {"about": "Example Ltd"}}
        with patch.object(provider, "_send_jsonrpc", return_value={
            "content": [{"type": "text", "text": "typed tool result"}],
            "structuredContent": payload,
            "isError": False,
        }):
            assert provider.invoke_tool("get_company_profile", {"company_name": "example"}) == payload


class TestLinkedInMCPStatusAndErrorHandling:
    """Verify clean status detection and safety error classification."""

    def test_server_unavailable_handling(self, provider):
        """When local MCP sidecar is offline, report SERVER_UNAVAILABLE."""
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
            status = provider.get_status()
            assert status["status"] == "SERVER_UNAVAILABLE"
            assert "Cannot connect" in status["message"]

    def test_login_required_detection(self, provider):
        """When MCP server reports unauthenticated session, report LOGIN_REQUIRED."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "LinkedIn authentication required: sign in session expired"}}'
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "LinkedIn authentication required: sign in session expired"},
        }
        with patch("requests.post", return_value=mock_resp):
            status = provider.get_status()
            assert status["status"] == "LOGIN_REQUIRED"

    def test_captcha_checkpoint_challenge(self, provider):
        """When security verification or CAPTCHA appears, report MANUAL_BROWSER_ACTION_REQUIRED."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "LinkedIn presented security challenge: checkpoint CAPTCHA required"}}'
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32000, "message": "LinkedIn presented security challenge: checkpoint CAPTCHA required"},
        }
        with patch("requests.post", return_value=mock_resp):
            status = provider.get_status()
            assert status["status"] == "MANUAL_BROWSER_ACTION_REQUIRED"

    def test_rate_limited_detection(self, provider):
        """When HTTP 429 Too Many Requests is returned, report RATE_LIMITED."""
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        with patch("requests.post", return_value=mock_resp):
            status = provider.get_status()
            assert status["status"] == "RATE_LIMITED"

    def test_ready_status(self, provider):
        """When MCP server responds with tools list, report READY."""
        mock_resp = _mock_response({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {
                "tools": [
                    {"name": "get_company_profile"},
                    {"name": "search_people"},
                ]
            },
        })
        with patch("requests.post", side_effect=_successful_handshake(mock_resp)) as mock_post:
            status = provider.get_status()
            assert status["status"] == "READY"
            assert "search_people" in status["tools_available"]
            assert mock_post.call_args_list[0].kwargs["json"]["method"] == "initialize"
            assert mock_post.call_args_list[1].kwargs["json"]["method"] == "notifications/initialized"
            assert mock_post.call_args_list[2].kwargs["json"]["method"] == "tools/list"
            assert mock_post.call_args_list[2].kwargs["headers"]["Mcp-Session-Id"] == "test-session"

    def test_initialization_timeout_is_not_server_unavailable(self, provider):
        """A connected server that stalls during initialize gets a precise timeout status."""
        with patch("requests.post", side_effect=requests.exceptions.Timeout("read timeout")):
            status = provider.get_status()
        assert status["status"] == "MCP_INITIALIZATION_TIMEOUT"
        assert "initialize request timed out" in status["message"]

    def test_host_rejection_has_precise_status(self, provider):
        """HTTP 421 from strict Host protection is not a generic timeout or outage."""
        rejected = _mock_response(status_code=421)
        rejected.text = "Misdirected Request"
        with patch("requests.post", return_value=rejected):
            status = provider.get_status()
        assert status["status"] == "MCP_HOST_REJECTED"

    def test_configured_loopback_host_override_applies_to_full_lifecycle(self):
        """Docker bridge requests preserve the sidecar's loopback Host identity."""
        configured = LinkedInMCPProvider(
            endpoint_url="http://host.docker.internal:8765/mcp",
            host_header="127.0.0.1:8765",
            enabled=True,
            timeout_seconds=5,
        )
        tools_response = _mock_response({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {"tools": [{"name": "get_company_profile"}]},
        })
        with patch("requests.post", side_effect=_successful_handshake(tools_response)) as mock_post:
            status = configured.get_status()
        assert status["status"] == "READY"
        assert all(
            call.kwargs["headers"]["Host"] == "127.0.0.1:8765"
            for call in mock_post.call_args_list
        )

    def test_local_runtime_omits_host_override(self):
        """Native localhost clients keep the normal HTTP Host behavior."""
        local = LinkedInMCPProvider(
            endpoint_url="http://127.0.0.1:8765/mcp",
            host_header="",
            enabled=True,
            timeout_seconds=5,
        )
        tools_response = _mock_response({
            "jsonrpc": "2.0",
            "id": 3,
            "result": {"tools": [{"name": "get_company_profile"}]},
        })
        with patch("requests.post", side_effect=_successful_handshake(tools_response)) as mock_post:
            status = local.get_status()
        assert status["status"] == "READY"
        assert all("Host" not in call.kwargs["headers"] for call in mock_post.call_args_list)


class TestLinkedInMCPCompanyAndPeopleSearch:
    """Verify company resolution and senior authority prioritization in search."""

    def test_resolve_company_profile_extracts_urn(self, provider):
        """Company profile resolution extracts universal slug and numeric URN."""
        mock_profile = {
            "name": "Ramkrishna Forgings Limited",
            "universal_name": "ramkrishna-forgings",
            "urn": "urn:li:company:1817109",
            "employee_count": 5000,
            "website": "https://www.ramkrishnaforgings.com",
        }
        with patch.object(provider, "invoke_tool", return_value=mock_profile) as invoke_tool:
            info = provider.resolve_company("Ramkrishna Forgings", domain="ramkrishnaforgings.com")
            assert info is not None
            assert info["company_name"] == "Ramkrishna Forgings Limited"
            assert info["company_slug"] == "ramkrishna-forgings"
            assert info["company_urn"] == "1817109"
            invoke_tool.assert_called_once_with(
                "get_company_profile",
                {"company_name": "ramkrishna-forgings"},
            )

    def test_resolve_company_parses_sidecar_sections_and_references(self, provider):
        sidecar_payload = {
            "url": "https://www.linkedin.com/company/ramkrishna-forgings/",
            "sections": {"about": "Ramkrishna Forgings Limited\nAutomotive component manufacturer"},
            "references": {"about": [{"kind": "company_urn", "url": "/search/results/people/", "value": "1817109"}]},
        }
        with patch.object(provider, "invoke_tool", return_value=sidecar_payload):
            info = provider.resolve_company("Ramkrishna Forgings Limited")
        assert info["company_name"] == "Ramkrishna Forgings Limited"
        assert info["company_slug"] == "ramkrishna-forgings"
        assert info["company_urn"] == "1817109"
        assert info["company_url"] == "https://www.linkedin.com/company/ramkrishna-forgings/"

    def test_senior_authority_role_order_in_search(self, provider):
        """Search decision makers queries senior authority roles before fallback ICs."""
        recorded_calls = []

        def fake_invoke(tool_name: str, args: Dict[str, Any]):
            recorded_calls.append((tool_name, args))
            if tool_name == "search_people":
                return {
                    "results": [
                        {
                            "name": "Arun Kumar",
                            "headline": "Plant Head at Ramkrishna Forgings",
                            "profile_url": "https://www.linkedin.com/in/arun-kumar-planthead",
                            "location": "Jamshedpur, Jharkhand",
                        }
                    ]
                }
            return {}

        with patch.object(provider, "invoke_tool", side_effect=fake_invoke):
            results = provider.search_decision_makers(
                company_name="Ramkrishna Forgings",
                company_urn="1817109",
                city="Jamshedpur",
                max_candidates=2,
            )
            assert len(results) >= 1
            assert results[0]["name"] == "Arun Kumar"
            assert results[0]["authority_tier"] == "SENIOR"

            # Check search query arguments
            search_args = recorded_calls[0][1]
            assert "Plant Head" in search_args["keywords"]
            assert "Head Quality" in search_args["keywords"]
            assert search_args["current_company"] == "1817109"
            assert search_args["location"] == "Jamshedpur"

    def test_missing_company_urn_uses_company_keywords_without_invalid_facet(self, provider):
        recorded_args = []

        def fake_invoke(tool_name: str, args: Dict[str, Any]):
            recorded_args.append(args)
            return {"results": [{
                "name": "Arun Kumar",
                "headline": "Plant Head at Ramkrishna Forgings Limited",
                "profile_url": "https://www.linkedin.com/in/arun-kumar-planthead",
            }]}

        with patch.object(provider, "invoke_tool", side_effect=fake_invoke):
            provider.search_decision_makers(
                company_name="Ramkrishna Forgings Limited",
                company_urn=None,
                city="Jamshedpur",
                max_candidates=1,
            )

        assert "current_company" not in recorded_args[0]
        assert '"Ramkrishna Forgings Limited"' in recorded_args[0]["keywords"]

    def test_rate_limit_stops_before_additional_linkedin_searches(self, provider):
        with patch.object(
            provider,
            "invoke_tool",
            side_effect=LinkedInMCPRateLimitError("LinkedIn rate limit reached"),
        ) as invoke_tool:
            with pytest.raises(LinkedInMCPRateLimitError):
                provider.search_decision_makers(
                    company_name="Ramkrishna Forgings Limited",
                    company_urn=None,
                    city="Jamshedpur",
                    max_candidates=3,
                )
        assert invoke_tool.call_count == 1

    def test_expected_control_person_not_injected_into_smoke_search(self, provider):
        """Correction 2: Benchmark answer leakage guard.

        DO NOT pass 'Krishna Kumar Jha' into search. Discovery must run unseeded.
        """
        recorded_keywords = []
        recorded_calls = []

        def fake_invoke(tool_name: str, args: Dict[str, Any]):
            recorded_calls.append((tool_name, args))
            if tool_name == "search_people":
                recorded_keywords.append(args.get("keywords", ""))
            return {"results": []}

        with patch.object(provider, "invoke_tool", side_effect=fake_invoke):
            provider.search_decision_makers(
                company_name="Ramkrishna Forgings",
                company_urn="1817109",
                city="Jamshedpur",
                facility_name="Plant V",
                max_candidates=3,
            )

            # Assert NO leakage of expected truth control name
            for kw in recorded_keywords:
                assert "krishna" not in kw.lower()
                assert "jha" not in kw.lower()
                assert "krishna kumar jha" not in kw.lower()

            employee_call = next(call for call in recorded_calls if call[0] == "get_company_employees")
            assert employee_call[1] == {
                "company_name": "ramkrishna-forgings",
                "keywords": "Quality",
            }

    def test_people_search_parses_sidecar_person_references(self, provider):
        sidecar_payload = {
            "url": "https://www.linkedin.com/search/results/people/",
            "sections": {"search_results": "Senior quality leaders"},
            "references": {"search_results": [{
                "kind": "person",
                "url": "/in/arun-kumar-planthead/",
                "text": "Arun Kumar",
                "context": "Plant Head at Ramkrishna Forgings",
            }]},
        }
        with patch.object(provider, "invoke_tool", return_value=sidecar_payload):
            results = provider.search_decision_makers(
                company_name="Ramkrishna Forgings Limited",
                company_urn="1817109",
                company_slug="ramkrishna-forgings",
                city="Jamshedpur",
                max_candidates=1,
            )
        assert results[0]["name"] == "Arun Kumar"
        assert results[0]["profile_url"] == "https://www.linkedin.com/in/arun-kumar-planthead/"


class TestLinkedInMCPExperienceVerification:
    """Verify Experience parsing, contradiction overrides, and facility relationship grounding."""

    def test_verified_current_employment(self, provider):
        """Experience entry at target company with Present marker yields VERIFIED."""
        profile_data = {
            "name": "Sanjay Sharma",
            "headline": "Head Quality at ABC Forgings Ltd",
            "location": "Pune, Maharashtra",
            "experience": [
                {
                    "company": "ABC Forgings Ltd",
                    "title": "Head Quality",
                    "date_range": "Jan 2024 – Present",
                    "is_current": True,
                    "location": "Pune, India",
                    "description": "Leading plant quality and metrology labs.",
                }
            ],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_data) as invoke_tool:
            verif = provider.verify_candidate_experience(
                profile_url="https://linkedin.com/in/sanjay-sharma",
                target_company="ABC Forgings Ltd",
                target_city="Pune",
            )
            assert verif["current_employment"] == "VERIFIED"
            assert verif["is_contradicted"] is False
            assert verif["function_verified"] is True
            assert verif["authority_verified"] is True
            invoke_tool.assert_called_once_with(
                "get_person_profile",
                {
                    "linkedin_username": "https://linkedin.com/in/sanjay-sharma",
                    "sections": "experience",
                },
            )

    def test_experience_parses_sidecar_raw_sections(self, provider):
        sidecar_payload = {
            "url": "https://www.linkedin.com/in/sanjay-sharma/",
            "sections": {
                "main_profile": "Sanjay Sharma\nHead Quality at ABC Forgings Ltd\nPune, Maharashtra, India",
                "experience": "Experience\nHead Quality\nABC Forgings Ltd · Full-time\nJan 2024 – Present\nPune, Maharashtra, India\nLeading plant quality and metrology labs.",
            },
        }
        with patch.object(provider, "invoke_tool", return_value=sidecar_payload):
            verification = provider.verify_candidate_experience(
                profile_url="https://www.linkedin.com/in/sanjay-sharma/",
                target_company="ABC Forgings Ltd",
                target_city="Pune",
            )
        assert verification["name"] == "Sanjay Sharma"
        assert verification["current_employment"] == "VERIFIED"
        assert verification["current_title"] == "Head Quality"
        assert verification["target_experience"]["location"] == "Pune, Maharashtra, India"

    def test_newer_other_employer_overrides_older_target_present(self, provider):
        """Correction 7: Newer Experience entry at another employer CONTRADICTS older target company entry."""
        profile_data = {
            "name": "Vikram Singh",
            "headline": "Director Quality at NewCo",
            "location": "Bengaluru, Karnataka",
            "experience": [
                {
                    "company": "NewCo Technologies Ltd",
                    "title": "Director of Quality",
                    "date_range": "Feb 2025 – Present",
                    "is_current": True,
                    "location": "Bengaluru, India",
                },
                {
                    "company": "Target Forgings Ltd",
                    "title": "Head Quality",
                    "date_range": "2021 – Present",  # Older unclosed entry
                    "is_current": True,
                    "location": "Pune, India",
                },
            ],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_data):
            verif = provider.verify_candidate_experience(
                profile_url="https://linkedin.com/in/vikram-singh",
                target_company="Target Forgings Ltd",
                target_city="Pune",
            )
            # Crucial: Contradiction must override older target company Present
            assert verif["current_employment"] == "CONTRADICTED"
            assert verif["is_contradicted"] is True

    def test_past_only_target_company_experience_contradicted(self, provider):
        """If candidate was at target company in the past and has since moved on, status is CONTRADICTED."""
        profile_data = {
            "name": "Pooja Verma",
            "headline": "VP Quality at Global Corp",
            "location": "Chennai, Tamil Nadu",
            "experience": [
                {
                    "company": "Global Corp Ltd",
                    "title": "VP Quality",
                    "date_range": "Jan 2024 – Present",
                    "is_current": True,
                },
                {
                    "company": "Target Forgings Ltd",
                    "title": "Quality Manager",
                    "date_range": "2018 – 2023",
                    "is_current": False,
                },
            ],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_data):
            verif = provider.verify_candidate_experience(
                profile_url="https://linkedin.com/in/pooja-verma",
                target_company="Target Forgings Ltd",
            )
            assert verif["current_employment"] == "CONTRADICTED"
            assert verif["is_contradicted"] is True

    def test_generic_profile_location_cannot_create_direct_facility(self, provider):
        """Correction 1: Generic LinkedIn profile location != DIRECT facility ownership.

        Example from prompt:
        Target: Sanand Plant
        Profile location: Ahmedabad, Gujarat
        May support: STRONG, but MUST NOT create DIRECT / FACILITY_FUNCTION_OWNER.
        """
        profile_data = {
            "name": "Nilesh Shah",
            "headline": "Quality Head at Tata Motors",
            "location": "Ahmedabad, Gujarat",  # Generic profile location (metro area)
            "experience": [
                {
                    "company": "Tata Motors Ltd",
                    "title": "Quality Head",
                    "date_range": "2023 – Present",
                    "is_current": True,
                    "location": "India",  # Generic country location in experience
                    "description": "Leading quality management systems.",
                }
            ],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_data):
            verif = provider.verify_candidate_experience(
                profile_url="https://linkedin.com/in/nilesh-shah",
                target_company="Tata Motors Ltd",
                target_facility="Sanand Plant",
                target_city="Sanand",
            )
            # Profile location only supports STRONG, NEVER FACILITY_FUNCTION_OWNER / DIRECT!
            assert verif["facility_relationship"] == "STRONG"
            assert verif["facility_relationship"] != "FACILITY_FUNCTION_OWNER"
            assert verif["facility_relationship"] != "FACILITY_OWNER"

    def test_experience_specific_plant_location_creates_direct(self, provider):
        """Experience entry explicitly naming the plant or job location tied specifically to that experience creates DIRECT."""
        profile_data = {
            "name": "Nilesh Shah",
            "headline": "Quality Head at Tata Motors",
            "location": "Ahmedabad, Gujarat",
            "experience": [
                {
                    "company": "Tata Motors Ltd",
                    "title": "Quality Head",
                    "date_range": "2023 – Present",
                    "is_current": True,
                    "location": "Sanand Plant, Gujarat",  # Tied specifically to this experience
                    "description": "Leading plant quality and metrology lab at Sanand.",
                }
            ],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_data):
            verif = provider.verify_candidate_experience(
                profile_url="https://linkedin.com/in/nilesh-shah",
                target_company="Tata Motors Ltd",
                target_facility="Sanand Plant",
                target_city="Sanand",
            )
            assert verif["facility_relationship"] == "FACILITY_FUNCTION_OWNER"

    def test_headline_plant_binding_creates_direct(self, provider):
        """Explicit plant/unit wording in candidate headline creates direct facility function ownership."""
        profile_data = {
            "name": "Krishna Kumar Jha",
            "headline": "Head Quality - Plant V at Ramkrishna Forgings Limited",
            "location": "Jamshedpur, Jharkhand",
            "experience": [
                {
                    "company": "Ramkrishna Forgings Limited",
                    "title": "Head Quality",
                    "date_range": "2021 – Present",
                    "is_current": True,
                    "location": "Jamshedpur",
                    "description": "Responsible for Quality Assurance and Metrology.",
                }
            ],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_data):
            verif = provider.verify_candidate_experience(
                profile_url="https://linkedin.com/in/krishna-kumar-jha",
                target_company="Ramkrishna Forgings Limited",
                target_facility="Plant V",
                target_city="Jamshedpur",
            )
            assert verif["current_employment"] == "VERIFIED"
            assert verif["facility_relationship"] == "FACILITY_FUNCTION_OWNER"
            assert verif["function_verified"] is True
            assert verif["authority_verified"] is True

    def test_separate_function_and_authority_reporting(self, provider):
        """Correction 8: Report FUNCTION_VERIFIED and AUTHORITY_VERIFIED separately."""
        # Case A: Senior Authority + Quality Function
        profile_a = {
            "name": "Candidate A",
            "headline": "Plant Head at ABC Ltd",
            "experience": [{"company": "ABC Ltd", "title": "Plant Head", "date_range": "2022 – Present", "is_current": True}],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_a):
            verif_a = provider.verify_candidate_experience("url_a", target_company="ABC Ltd")
            assert verif_a["function_verified"] is True
            assert verif_a["authority_verified"] is True

        # Case B: Quality IC (Quality Engineer) -> Function YES, Authority NO
        profile_b = {
            "name": "Candidate B",
            "headline": "Quality Engineer at ABC Ltd",
            "experience": [{"company": "ABC Ltd", "title": "Quality Engineer", "date_range": "2023 – Present", "is_current": True}],
        }
        with patch.object(provider, "invoke_tool", return_value=profile_b):
            verif_b = provider.verify_candidate_experience("url_b", target_company="ABC Ltd")
            assert verif_b["function_verified"] is True
            # Junior IC is not verified commercial decision-maker authority
            assert verif_b["authority_verified"] is False


class TestLinkedInMCPIntegrationPipeline:
    """Verify integration with discover_and_rank_decision_makers in person_intelligence_service."""

    def test_linkedin_mcp_failure_never_invokes_searxng(self):
        from services.person_intelligence_service import discover_and_rank_decision_makers
        from services.linkedin_mcp_provider import linkedin_mcp_provider
        from services.research_provider import ResearchProviderRouter, PROVIDER_ERROR

        router = ResearchProviderRouter()
        with patch.object(linkedin_mcp_provider, "_explicit_enabled", True), \
             patch.object(linkedin_mcp_provider, "get_status", return_value={"status": "SERVER_UNAVAILABLE", "message": "Connection refused"}), \
             patch.object(router, "_search_serper", return_value=([], PROVIDER_ERROR, "Serper unavailable")), \
             patch.object(router, "_search_searxng") as mock_searxng, \
             patch("services.research_provider.get_setting_value") as mock_settings:
            mock_settings.side_effect = lambda key, default="": (
                "valid_serper_key_123456789" if key == "SERPER_API_KEY" else default
            )
            result = discover_and_rank_decision_makers(
                company_name="Acme Ltd",
                facility_name="Sanand Plant",
                city="Sanand",
                search_router=router,
                max_candidates=2,
                max_company_queries=1,
                max_stage_b_searches=0,
                search_workers=1,
            )

        assert result["telemetry"]["linkedin_mcp_status"] == "SERVER_UNAVAILABLE"
        mock_searxng.assert_not_called()

    def test_linkedin_mcp_failure_clean_fallback_without_lowering_gates(self):
        """Correction 11: LinkedIn MCP failure cleanly falls back to public Serper without lowering qualification gates."""
        from services.person_intelligence_service import discover_and_rank_decision_makers
        from services.linkedin_mcp_provider import linkedin_mcp_provider

        # Mock search router for Serper fallback
        mock_router = MagicMock()
        mock_router.search.return_value = {
            "results": [
                {
                    "title": "Arun Kumar - Quality Manager - Acme Ltd | LinkedIn",
                    "snippet": "Arun Kumar currently serves as Quality Manager at Acme Ltd Sanand plant.",
                    "url": "https://in.linkedin.com/in/arun-kumar-acme",
                }
            ]
        }

        # Mock LinkedIn MCP provider as enabled but raising connection error
        with patch.object(linkedin_mcp_provider, "_explicit_enabled", True), \
             patch.object(linkedin_mcp_provider, "get_status", return_value={"status": "SERVER_UNAVAILABLE", "message": "Connection refused"}):

            res = discover_and_rank_decision_makers(
                company_name="Acme Ltd",
                facility_name="Sanand Plant",
                city="Sanand",
                search_router=mock_router,
                max_candidates=2,
            )

            # Assert pipeline ran cleanly without uncaught exception
            assert res is not None
            assert res["telemetry"]["linkedin_mcp_status"] == "SERVER_UNAVAILABLE"
            assert res["telemetry"]["queries_run"] >= 1
            assert len(res["candidates"]) >= 1
            cand = res["candidates"][0]
            assert cand["name"] == "Arun Kumar"
            # Deterministic Salesoorja qualification gate must still apply
            assert cand["current_employment"] == "VERIFIED"

    def test_linkedin_mcp_conclusive_candidate_stops_early(self):
        """When LinkedIn MCP discovers and verifies a HIGH confidence candidate, discovery stops early, saving Serper queries."""
        from services.person_intelligence_service import discover_and_rank_decision_makers
        from services.linkedin_mcp_provider import linkedin_mcp_provider

        mock_router = MagicMock()
        mock_router.search.return_value = {"results": []}

        discovered_cand = [
            {
                "name": "Rajesh Gupta",
                "headline": "Head Quality - Plant V at Acme Forgings Ltd",
                "profile_url": "https://www.linkedin.com/in/rajesh-gupta-acme",
                "authority_tier": "SENIOR",
            }
        ]

        verified_cand = {
            "name": "Rajesh Gupta",
            "headline": "Head Quality - Plant V at Acme Forgings Ltd",
            "profile_url": "https://www.linkedin.com/in/rajesh-gupta-acme",
            "current_title": "Head Quality",
            "current_company": "Acme Forgings Ltd",
            "profile_location": "Jamshedpur, Jharkhand",
            "current_employment": "VERIFIED",
            "facility_relationship": "FACILITY_FUNCTION_OWNER",
            "function_verified": True,
            "authority_verified": True,
            "is_contradicted": False,
            "target_experience": {
                "title": "Head Quality",
                "company": "Acme Forgings Ltd",
                "dates": "Jan 2023 – Present",
                "location": "Plant V, Jamshedpur",
                "description": "Leading Plant V quality operations.",
            },
        }

        with patch.object(linkedin_mcp_provider, "_explicit_enabled", True), \
             patch.object(linkedin_mcp_provider, "get_status", return_value={"status": "READY"}), \
             patch.object(linkedin_mcp_provider, "resolve_company", return_value={"company_urn": "999", "company_slug": "acme"}), \
             patch.object(linkedin_mcp_provider, "search_decision_makers", return_value=discovered_cand), \
             patch.object(linkedin_mcp_provider, "verify_candidate_experience", return_value=verified_cand):

            res = discover_and_rank_decision_makers(
                company_name="Acme Forgings Ltd",
                facility_name="Plant V",
                city="Jamshedpur",
                search_router=mock_router,
                max_candidates=2,
            )

            assert res["telemetry"]["linkedin_mcp_status"] == "READY"
            assert res["telemetry"]["stopped_early"] is True
            assert res["telemetry"]["early_stop_reason"] == "SUFFICIENT_EVIDENCE_LINKEDIN_MCP"
            # Serper initial tier search was avoided because conclusive candidate was found
            assert mock_router.search.call_count == 0
            assert res["primary_person"] is not None
            assert res["primary_person"]["name"] == "Rajesh Gupta"
            assert res["primary_person"]["current_employment"] == "VERIFIED"
            assert res["primary_person"]["facility_relationship"] == "FACILITY_FUNCTION_OWNER"
            assert res["primary_person"]["person_confidence"] == "HIGH"
