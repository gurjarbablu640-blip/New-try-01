"""Unit tests for Authoritative LLM Information-Gain Gate (Task 3D.1F)."""
import pytest
from unittest.mock import MagicMock, patch

from services.followup_information_gain_gate import (
    FollowupInformationGainGate,
    InformationGainDecision,
    get_telemetry,
    reset_telemetry,
    GENERIC_ENTITY_BLOCKLIST,
)
from services.adaptive_research_service import (
    AdaptiveResearchService,
    FOLLOWUP_TEMPLATES,
)
from services.company_first_discovery import CompanyFirstDiscoveryService


@pytest.fixture(autouse=True)
def clean_telemetry():
    reset_telemetry()
    yield
    reset_telemetry()


class MockLLMResponse:
    def __init__(self, data):
        self.data = data

    def parse_json(self):
        return self.data


class TestFollowupInformationGainGate:

    def test_generic_entity_blocked_immediately(self):
        """Generic entities like 'Chemical', 'Steel', 'Manufacturing' must be blocked."""
        gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)
        
        for generic in ["Chemical", "steel", "MANUFACTURING", "Plant", "Company", "Industry"]:
            decision = gate.evaluate_followup_search(
                company_name=generic,
                missing_fact="COMMISSIONING_STATUS",
            )
            assert decision.search_needed is False
            assert decision.expected_information_gain == "LOW"
            assert decision.blocked_reason == "BLOCK_GENERIC_ENTITY"
            assert decision.decision_type == "DETERMINISTIC_REJECT"

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_SEARCH_BLOCKED_GENERIC_ENTITY"] >= 6

    def test_unresolved_entity_blocked(self):
        """Weak/ungrounded entity without company ID or pre-persistence pass must be blocked (Amendment 5)."""
        gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)

        # Mock pre_persistence_entity_gate to reject
        with patch("services.pre_persistence_entity_gate.pre_persistence_entity_gate.resolve_pre_persistence_decision") as mock_pre:
            mock_eval = MagicMock()
            mock_eval.should_persist = False
            mock_eval.entity_type = "HEADLINE_FRAGMENT"
            mock_eval.reason = "Candidate is a headline fragment"
            mock_pre.return_value = mock_eval

            decision = gate.evaluate_followup_search(
                company_name="Random Fragment",
                missing_fact="FACILITY_LOCATION",
                company_id=None,
                candidate_group={"entity_verified": False, "is_target_industrial": False},
            )
            assert decision.search_needed is False
            assert decision.blocked_reason == "BLOCK_UNRESOLVED_ENTITY"

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_BLOCKED_UNRESOLVED_ENTITY"] >= 1

    def test_existing_evidence_sufficient_llm_judgment(self):
        """LLM determines existing evidence already proves commissioning date -> USE_EXISTING_EVIDENCE (Amendment 2)."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MockLLMResponse({
            "search_needed": False,
            "missing_fact": "COMMISSIONING_STATUS",
            "expected_information_gain": "LOW",
            "reason": "Existing evidence from article explicitly confirms commercial production commenced in August 2024 at Surat Unit 2.",
            "suggested_query": "",
            "research_strategy": "GENERAL_WEB",
            "alternative_action": "USE_EXISTING_EVIDENCE",
        })

        gate = FollowupInformationGainGate(primary_provider=mock_deepseek, fallback_provider=None)

        decision = gate.evaluate_followup_search(
            company_name="Aether Industries Limited",
            missing_fact="COMMISSIONING_STATUS",
            company_id=284,
            current_evidence={
                "titles": ["Aether Industries commences commercial production at Surat Unit"],
                "snippets": ["The company announced commercial production at its new manufacturing plant in Surat."],
            },
        )

        assert decision.search_needed is False
        assert decision.alternative_action == "USE_EXISTING_EVIDENCE"
        assert decision.expected_information_gain == "LOW"

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_EXISTING_EVIDENCE_REUSED"] == 1
        assert telemetry["FOLLOWUP_LLM_EXISTING_EVIDENCE_SUFFICIENT"] == 1
        assert telemetry["FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE"] == 1

    def test_two_failed_searches_stop_repetition(self):
        """For same (COMPANY + MISSING_FACT), maximum 2 unsuccessful searches before STOP (Section 8)."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MockLLMResponse({
            "search_needed": True,
            "missing_fact": "FACILITY_LOCATION",
            "expected_information_gain": "MEDIUM",
            "reason": "Searching again for facility location with general web",
            "suggested_query": "Aether Industries plant location",
            "research_strategy": "GENERAL_WEB",
            "alternative_action": "SEARCH",
        })

        gate = FollowupInformationGainGate(primary_provider=mock_deepseek, fallback_provider=None)

        # Record 2 unsuccessful searches in memory
        gate.record_search_outcome(
            company_name="Aether Industries Limited",
            missing_fact="FACILITY_LOCATION",
            query="Aether Industries plant location Gujarat",
            research_strategy="GENERAL_WEB",
            new_evidence_found=False,
            company_id=284,
        )
        gate.record_search_outcome(
            company_name="Aether Industries Limited",
            missing_fact="FACILITY_LOCATION",
            query="Aether Industries manufacturing unit city",
            research_strategy="GENERAL_WEB",
            new_evidence_found=False,
            company_id=284,
        )

        # 3rd attempt: general web must be BLOCKED as exhausted
        decision = gate.evaluate_followup_search(
            company_name="Aether Industries Limited",
            missing_fact="FACILITY_LOCATION",
            company_id=284,
        )

        assert decision.search_needed is False
        assert decision.blocked_reason == "BLOCK_EXHAUSTED"
        assert "Blocked after 2 unsuccessful searches" in decision.reason

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED"] >= 1

    def test_materially_different_source_strategy_allowed(self):
        """After 2 failed general web searches, an escalated strategy (OFFICIAL_COMPANY) with rationale is allowed (Section 8)."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MockLLMResponse({
            "search_needed": True,
            "missing_fact": "COMMISSIONING_STATUS",
            "expected_information_gain": "HIGH",
            "reason": "General web failed twice. An official investor relations filing on the corporate domain will conclusively prove commissioning status.",
            "suggested_query": "site:aether.co.in/investor-relations commercial production commissioning",
            "research_strategy": "OFFICIAL_COMPANY",
            "alternative_action": "SEARCH",
        })

        gate = FollowupInformationGainGate(primary_provider=mock_deepseek, fallback_provider=None)

        # Record 2 unsuccessful GENERAL_WEB searches
        gate.record_search_outcome(
            company_name="Aether Industries Limited",
            missing_fact="COMMISSIONING_STATUS",
            query="Aether Industries plant commissioning",
            research_strategy="GENERAL_WEB",
            new_evidence_found=False,
            company_id=284,
        )
        gate.record_search_outcome(
            company_name="Aether Industries Limited",
            missing_fact="COMMISSIONING_STATUS",
            query="Aether Industries commercial production status",
            research_strategy="GENERAL_WEB",
            new_evidence_found=False,
            company_id=284,
        )

        # 3rd attempt: OFFICIAL_COMPANY is an escalated strategy -> MAY ALLOW
        decision = gate.evaluate_followup_search(
            company_name="Aether Industries Limited",
            missing_fact="COMMISSIONING_STATUS",
            company_id=284,
        )

        assert decision.search_needed is True
        assert decision.expected_information_gain == "HIGH"
        assert decision.research_strategy == "OFFICIAL_COMPANY"
        assert "site:aether.co.in" in decision.suggested_query

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_SEARCH_ALLOWED"] == 1
        assert telemetry["FOLLOWUP_LLM_NEW_SEARCH_JUSTIFIED"] == 1

    def test_cosmetic_query_rewrite_rejected(self):
        """Cosmetic query rewrites of exhausted prior queries are blocked (BLOCK_REPETITION)."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        # Propose essentially the same query that was already run
        mock_deepseek.complete.return_value = MockLLMResponse({
            "search_needed": True,
            "missing_fact": "CAPEX_EVENT",
            "expected_information_gain": "MEDIUM",
            "reason": "Minor rephrasing",
            "suggested_query": '"Dharamsi Morarji Chemical" plant capex expansion',
            "research_strategy": "GENERAL_WEB",
            "alternative_action": "SEARCH",
        })

        gate = FollowupInformationGainGate(primary_provider=mock_deepseek, fallback_provider=None)

        # Prior query has essentially identical normalized tokens
        gate.record_search_outcome(
            company_name="Dharamsi Morarji Chemical",
            missing_fact="CAPEX_EVENT",
            query="Dharamsi Morarji Chemical plant capex expansion",
            research_strategy="GENERAL_WEB",
            new_evidence_found=False,
            company_id=297,
        )

        decision = gate.evaluate_followup_search(
            company_name="Dharamsi Morarji Chemical",
            missing_fact="CAPEX_EVENT",
            company_id=297,
        )

        assert decision.search_needed is False
        assert decision.blocked_reason == "BLOCK_REPETITION"

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_QUERY_REPETITION_BLOCKED"] == 1

    def test_new_evidence_recognized_and_hold_to_pass_counted(self):
        """Search outcome with new evidence records correctly and increments HOLD -> PASS (Section 7)."""
        gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)

        gate.record_search_outcome(
            company_name="Dharamsi Morarji Chemical",
            missing_fact="COMMISSIONING_STATUS",
            query="Dharamsi Morarji Chemical Dahej plant commissioning",
            research_strategy="OFFICIAL_COMPANY",
            result_count=3,
            useful_urls=["https://dmcc.com/news/dahej-commissioning"],
            new_evidence_found=True,
            evidence_type_found="COMMISSIONING_DATE_VERIFIED",
            funnel_state_before="HOLD",
            funnel_state_after="PASS",
            company_id=297,
        )

        telemetry = get_telemetry()
        assert telemetry["FOLLOWUP_SEARCHES_EXECUTED"] == 1
        assert telemetry["FOLLOWUP_SEARCHES_WITH_NEW_EVIDENCE"] == 1
        assert telemetry["FOLLOWUP_PRODUCTIVE_OUTCOME_PRESERVED"] == 1
        assert telemetry["FOLLOWUP_HOLD_TO_PASS"] == 1

        # Check that subsequent search for same fact is skipped because it's now resolved
        decision = gate.evaluate_followup_search(
            company_name="Dharamsi Morarji Chemical",
            missing_fact="COMMISSIONING_STATUS",
            company_id=297,
        )
        assert decision.search_needed is False
        assert decision.alternative_action == "USE_EXISTING_EVIDENCE"

    def test_deepseek_failure_gemini_fallback(self):
        """When DeepSeek fails, Gemini provider is called as fallback."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.side_effect = RuntimeError("DeepSeek rate limited")

        mock_gemini = MagicMock()
        mock_gemini.is_available.return_value = True
        mock_gemini.complete.return_value = MockLLMResponse({
            "search_needed": True,
            "missing_fact": "FACILITY_LOCATION",
            "expected_information_gain": "HIGH",
            "reason": "Gemini fallback: verified missing facility",
            "suggested_query": "Dharamsi Morarji Chemical manufacturing facility location",
            "research_strategy": "GENERAL_WEB",
            "alternative_action": "SEARCH",
        })

        gate = FollowupInformationGainGate(primary_provider=mock_deepseek, fallback_provider=mock_gemini)

        decision = gate.evaluate_followup_search(
            company_name="Dharamsi Morarji Chemical",
            missing_fact="FACILITY_LOCATION",
            company_id=297,
        )

        assert decision.search_needed is True
        assert decision.provider_used == "GEMINI"
        assert decision.expected_information_gain == "HIGH"

        telemetry = get_telemetry()
        assert telemetry["GEMINI_FOLLOWUP_FALLBACKS"] == 1
        assert telemetry["FOLLOWUP_PROVIDER_FAILURES"] == 1

    def test_llm_unavailable_safe_deterministic_fallback(self):
        """When both LLMs fail, safe deterministic fallback executes cleanly."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = False
        mock_gemini = MagicMock()
        mock_gemini.is_available.return_value = False

        gate = FollowupInformationGainGate(primary_provider=mock_deepseek, fallback_provider=mock_gemini)

        decision = gate.evaluate_followup_search(
            company_name="Aether Industries Limited",
            missing_fact="FACILITY_LOCATION",
            company_id=284,
            current_evidence={"titles": [], "snippets": []},
        )

        assert decision.search_needed is True
        assert decision.decision_type == "DETERMINISTIC_FALLBACK"
        assert decision.expected_information_gain == "MEDIUM"

    def test_static_negative_tails_absent_from_default(self):
        """Verify that default templates in AdaptiveResearchService do NOT contain -stock -share (Amendment 6)."""
        for field, template in FOLLOWUP_TEMPLATES.items():
            assert "-stock" not in template.lower(), f"Template '{field}' contains -stock"
            assert "-share" not in template.lower(), f"Template '{field}' contains -share"
            assert "-dividend" not in template.lower(), f"Template '{field}' contains -dividend"
            assert "-trading" not in template.lower(), f"Template '{field}' contains -trading"

    def test_adaptive_research_service_skips_when_gate_blocks(self):
        """When gate blocks search (e.g. existing evidence sufficient), adaptive research issues 0 Serper queries."""
        mock_router = MagicMock()
        mock_gate = MagicMock()
        mock_gate.evaluate_followup_search.return_value = InformationGainDecision(
            search_needed=False,
            missing_fact="COMMISSIONING_STATUS",
            expected_information_gain="LOW",
            reason="Existing evidence is already sufficient",
            suggested_query="",
            research_strategy="GENERAL_WEB",
            alternative_action="USE_EXISTING_EVIDENCE",
        )

        service = AdaptiveResearchService(router=mock_router, gate=mock_gate)

        candidate_group = {
            "company_name": "Aether Industries Limited",
            "company_id": 284,
            "titles": ["Aether news"],
            "snippets": ["Commissioned in 2024"],
            "source_urls": ["https://example.com"],
            "dates": ["2024-08-01"],
            "evidence_packets": [],
        }
        initial_assessment = {
            "opportunity_classification": "INCOMPLETE",
            "missing_fields": ["COMMISSIONING_STATUS"],
        }

        res = service.conduct_targeted_research(candidate_group, initial_assessment)

        assert res["searches_conducted"] == 0
        mock_router.search.assert_not_called()

    def test_company_first_discovery_blocks_generic_entity(self):
        """When research_company_triggers is called for generic entity 'Chemical', router.search is never called."""
        service = CompanyFirstDiscoveryService()
        service.router = MagicMock()

        res = service.research_company_triggers(
            company_name="Chemical",
            geography="Gujarat",
            sector="Chemicals & Specialty Materials",
        )

        assert res["has_trigger"] is False
        assert res["hold_reason"] == "BLOCK_GENERIC_ENTITY"
        service.router.search.assert_not_called()
