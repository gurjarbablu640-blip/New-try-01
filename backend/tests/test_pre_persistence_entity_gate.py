"""Unit tests for Pre-Persistence Entity Truth Gate (Task 3D.1D)."""
import pytest
from unittest.mock import MagicMock

from services.pre_persistence_entity_gate import (
    PrePersistenceEntityGate,
    PrePersistenceEntityDecision,
    get_prepersist_telemetry,
    increment_prepersist_telemetry,
)


class TestPrePersistenceDeterministicRejects:
    @pytest.fixture
    def gate(self):
        return PrePersistenceEntityGate(primary_provider=None, fallback_provider=None)

    @pytest.mark.parametrize("pronoun", ["We", "They", "Our", "It", "This", "us", "them"])
    def test_pronouns_rejected(self, gate, pronoun):
        dec = gate.resolve_pre_persistence_decision(pronoun)
        assert dec.is_target_industrial is False
        assert dec.entity_type == "INVALID_ENTITY"
        assert dec.provider_used == "DETERMINISTIC_FAST_REJECT"

    @pytest.mark.parametrize("noun", ["Chemical", "Steel", "Manufacturing", "Aerospace & Defence", "new solar module"])
    def test_generic_nouns_rejected(self, gate, noun):
        dec = gate.resolve_pre_persistence_decision(noun)
        assert dec.is_target_industrial is False
        assert dec.entity_type == "GENERIC_TEXT"
        assert dec.provider_used == "DETERMINISTIC_FAST_REJECT"

    @pytest.mark.parametrize("pub", ["COVER STORY", "Case Study", "Special Report", "Market Report"])
    def test_publication_headers_rejected(self, gate, pub):
        dec = gate.resolve_pre_persistence_decision(pub)
        assert dec.is_target_industrial is False
        assert dec.entity_type == "GENERIC_TEXT"
        assert dec.provider_used == "DETERMINISTIC_FAST_REJECT"

    @pytest.mark.parametrize("bad_str", ["mahasdb@maharashtra.gov", "info@tatasteel.com", "https://waaree.com", "www.reliance.com"])
    def test_email_and_urls_rejected(self, gate, bad_str):
        dec = gate.resolve_pre_persistence_decision(bad_str)
        assert dec.is_target_industrial is False
        assert dec.entity_type == "INVALID_ENTITY"
        assert dec.provider_used == "DETERMINISTIC_FAST_REJECT"

    def test_truncated_single_letter_rejected(self, gate):
        dec = gate.resolve_pre_persistence_decision("Waaree's N")
        assert dec.is_target_industrial is False
        assert dec.entity_type == "HEADLINE_FRAGMENT"

    def test_incomplete_phrase_rejected(self, gate):
        dec = gate.resolve_pre_persistence_decision("OFC industry in a take")
        assert dec.is_target_industrial is False
        assert dec.entity_type == "HEADLINE_FRAGMENT"


class TestZeroInventionEnforcement:
    @pytest.fixture
    def gate(self):
        return PrePersistenceEntityGate(primary_provider=None, fallback_provider=None)

    def test_grounded_name_accepted(self, gate):
        corpus = "Tata Steel opens new blast furnace at Kalinganagar plant in Odisha"
        assert gate.verify_zero_invention("Tata Steel", corpus) is True
        assert gate.verify_zero_invention("Tata Steel Limited", corpus) is True

    def test_hallucinated_name_rejected(self, gate):
        corpus = "Tata Steel opens new blast furnace at Kalinganagar plant in Odisha"
        assert gate.verify_zero_invention("Reliance Solar Power Ltd", corpus) is False
        assert gate.verify_zero_invention("Acme Manufacturing Global", corpus) is False

    def test_mock_llm_hallucination_blocked_by_zero_invention_guard(self):
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.complete.return_value = MagicMock(
            parse_json=lambda: {
                "entity_type": "TARGET_INDUSTRIAL_COMPANY",
                "canonical_company_name": "Invented Phantom Solar Corp",
                "industrial_relevance": "MANUFACTURER",
                "confidence": 0.99,
                "supporting_evidence": [],
                "reason": "Fictitious hallucination",
            }
        )
        gate = PrePersistenceEntityGate(primary_provider=mock_provider, fallback_provider=None)
        dec = gate.resolve_pre_persistence_decision(
            candidate_name="Solar Solutions Corp",
            title="Solar Panel Plant Expansion in Gujarat",
            snippet="State commissions 500MW solar cell facility",
            url="https://pv-magazine.com/news",
        )
        assert dec.is_target_industrial is False
        assert dec.entity_type == "UNKNOWN"
        assert "Zero-invention guard failed" in dec.reason


class TestSemanticJudgeDecisions:
    def test_non_target_software_company(self):
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.complete.return_value = MagicMock(
            parse_json=lambda: {
                "entity_type": "REAL_COMPANY_NON_TARGET",
                "canonical_company_name": "Inven",
                "industrial_relevance": "NON_INDUSTRIAL",
                "confidence": 0.95,
                "supporting_evidence": ["Inven is software"],
                "reason": "Inven is a SaaS company, not industrial manufacturing",
            }
        )
        gate = PrePersistenceEntityGate(primary_provider=mock_provider, fallback_provider=None)
        dec = gate.resolve_pre_persistence_decision(
            candidate_name="Inven",
            title="Inven AI M&A Platform",
            snippet="Global private company intelligence software",
            url="https://inven.ai",
        )
        assert dec.is_target_industrial is False
        assert dec.entity_type == "REAL_COMPANY_NON_TARGET"
        assert dec.canonical_company_name is None

    def test_ambiguous_entity_held_as_unknown(self):
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.complete.return_value = MagicMock(
            parse_json=lambda: {
                "entity_type": "UNKNOWN",
                "canonical_company_name": None,
                "industrial_relevance": "UNKNOWN",
                "confidence": 0.90,
                "supporting_evidence": [],
                "reason": "Ambiguous conglomerate name without industrial operating division",
            }
        )
        gate = PrePersistenceEntityGate(primary_provider=mock_provider, fallback_provider=None)
        dec = gate.resolve_pre_persistence_decision(
            candidate_name="Reliance",
            title="Reliance Reports Financial Results",
            snippet="Conglomerate quarterly revenue update",
            url="https://reuters.com",
        )
        assert dec.is_target_industrial is False
        assert dec.entity_type == "UNKNOWN"

    def test_legitimate_industrial_manufacturer_accepted(self):
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.complete.return_value = MagicMock(
            parse_json=lambda: {
                "entity_type": "TARGET_INDUSTRIAL_COMPANY",
                "canonical_company_name": "Aether Industries Limited",
                "industrial_relevance": "MANUFACTURER",
                "confidence": 0.98,
                "supporting_evidence": ["Aether Industries operationalizes Dahej Site 3"],
                "reason": "Aether Industries is a specialty chemical manufacturer in Gujarat",
            }
        )
        gate = PrePersistenceEntityGate(primary_provider=mock_provider, fallback_provider=None)
        dec = gate.resolve_pre_persistence_decision(
            candidate_name="Aether Industries",
            title="Aether Industries operationalizes Dahej Site 3",
            snippet="Specialty chemical manufacturer commissions plant in Dahej, Gujarat",
            url="https://aether.co.in",
            industry="Chemicals",
        )
        assert dec.is_target_industrial is True
        assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
        assert dec.canonical_company_name == "Aether Industries Limited"


class TestTelemetryCounters:
    def test_telemetry_increments(self):
        initial = get_prepersist_telemetry()
        gate = PrePersistenceEntityGate(primary_provider=None, fallback_provider=None)
        gate.resolve_pre_persistence_decision("We")
        after = get_prepersist_telemetry()
        assert after["ENTITY_PREPERSIST_CANDIDATES"] == initial["ENTITY_PREPERSIST_CANDIDATES"] + 1
        assert after["ENTITY_PREPERSIST_DETERMINISTIC_REJECT"] == initial["ENTITY_PREPERSIST_DETERMINISTIC_REJECT"] + 1
        assert after["ENTITY_PREPERSIST_FINAL_REJECT"] == initial["ENTITY_PREPERSIST_FINAL_REJECT"] + 1
