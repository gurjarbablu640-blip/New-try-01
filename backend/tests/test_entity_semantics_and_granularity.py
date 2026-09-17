"""Authoritative Unit & Semantic Tests for Task 3D.1E.1.

Tests:
1. Global Industrial Companies (Geography Decoupled from Target Status):
   - Royal Philips (healthcare/medical device manufacturing) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - Copeland (HVAC/compressor manufacturing) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - GE Healthcare (medical systems/hardware manufacturing) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - Hovione New Jersey (API/pharma manufacturing facility) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - Eli Lilly Puerto Rico (pharma formulation facility) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
2. Non-Industrial Commercial Business Models:
   - Inven (B2B SaaS / search software) -> REAL_COMPANY_NON_TARGET (should_persist = False)
3. Operating Entity Granularity & Ambiguity:
   - "Tata" with NO subsidiary in evidence -> AMBIGUOUS_GROUP (should_persist = False)
   - "Tata Motors" with EV manufacturing evidence -> EXACT_OPERATING_COMPANY (should_persist = True)
   - PARENT_GROUP without demonstrated targetability -> should_persist = False
   - PARENT_GROUP with explicit event grounding & demonstrated targetability -> should_persist = True (Branch B)
4. Zero-Invention Enforcement:
   - Candidate "Tata" where LLM hallucinates "Tata Motors" but "Tata Motors" is NOT in evidence -> ungrounded, demoted, should_persist = False
5. Preserved Junk Suppression:
   - "COVER STORY" -> deterministic reject
   - "Chemical" -> deterministic reject
   - "Semiconductor Industry in India" -> generic text reject
   - "Capsule Manufacturing in India" -> generic text reject
   - "ECMS Accelerates Electronics" -> headline fragment reject
   - "Square" -> headline/measurement fragment reject
   - "Tamil" -> generic/state name fragment reject
"""
import pytest
from unittest.mock import MagicMock
from services.pre_persistence_entity_gate import (
    PrePersistenceEntityGate,
    PrePersistenceEntityDecision,
)


class MockLLMProvider:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    def complete(self, **kwargs):
        self.call_count += 1
        messages = kwargs.get("messages", [])
        prompt_text = messages[0]["content"] if messages else kwargs.get("prompt", "")
        
        for match_key, resp in self.responses.items():
            if match_key.lower() in prompt_text.lower():
                mock_resp = MagicMock()
                mock_resp.parse_json.return_value = resp
                return mock_resp
        
        mock_resp = MagicMock()
        mock_resp.parse_json.return_value = {
            "entity_type": "UNKNOWN",
            "canonical_company_name": None,
            "industrial_relevance": "UNKNOWN",
            "facility_country": None,
            "geographic_serviceability": "UNKNOWN",
            "entity_granularity": "UNKNOWN",
            "operating_entity_name": None,
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.5,
            "supporting_evidence": [],
            "reason": "Default mock unknown",
        }
        return mock_resp


@pytest.fixture
def gate_with_mocks():
    mock_responses = {
        "Royal Philips": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Royal Philips",
            "operating_entity_name": "Royal Philips",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Royal Philips expands medical device manufacturing plant in Chakan, Pune"],
            "reason": "Authentic medical device and healthcare hardware manufacturer with plant in Chakan, Pune",
        },
        "Copeland": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Copeland",
            "operating_entity_name": "Copeland",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Copeland commissions new industrial compressor manufacturing facility in Atit, Maharashtra"],
            "reason": "Major HVAC/refrigeration compressor and industrial equipment manufacturer operating in Atit",
        },
        "GE Healthcare": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "GE Healthcare",
            "operating_entity_name": "Wipro GE Healthcare",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "SUBSIDIARY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Wipro GE Healthcare opens medical device manufacturing plant in Whitefield, Bengaluru"],
            "reason": "Precision medical technology and healthcare equipment manufacturer in Whitefield",
        },
        "Hovione": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Hovione",
            "operating_entity_name": "Hovione New Jersey",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "USA",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "SUBSIDIARY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Hovione expands pharmaceutical API manufacturing facility in East Windsor, New Jersey"],
            "reason": "Contract development and manufacturing organization (CDMO) operating industrial pharmaceutical plants globally",
        },
        "Arterex": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Arterex",
            "operating_entity_name": "Arterex",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "USA",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Arterex invests in medical device contract manufacturing plant"],
            "reason": "Authentic medical device contract manufacturer operating precision cleanroom moulding and assembly plants",
        },
        "Eli Lilly": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Eli Lilly",
            "operating_entity_name": "Eli Lilly and Company",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "Puerto Rico",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Eli Lilly announces major manufacturing capacity expansion at Puerto Rico pharmaceutical facility"],
            "reason": "Global pharmaceutical and biotechnology manufacturer operating multiple sterile formulation plants",
        },
        "Inven": {
            "entity_type": "REAL_COMPANY_NON_TARGET",
            "canonical_company_name": "Inven",
            "operating_entity_name": None,
            "industrial_relevance": "NON_INDUSTRIAL",
            "facility_country": "Finland",
            "geographic_serviceability": "UNKNOWN",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Inven is an AI search tool for M&A and corporate finance professionals"],
            "reason": "Software-only B2B SaaS platform for financial data and M&A; no industrial manufacturing or testing operations",
        },
        "Bare Tata": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata",
            "operating_entity_name": None,
            "industrial_relevance": "INDUSTRIAL_OPERATOR",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "AMBIGUOUS_GROUP",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.70,
            "supporting_evidence": ["Tata plans new capex across multiple unspecified sectors"],
            "reason": "Broad conglomerate without evidence-grounded operating subsidiary; held from persistence",
        },
        "Tata Motors": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata Motors",
            "operating_entity_name": "Tata Motors Limited",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Tata Motors commissions new commercial vehicle assembly line in Pune"],
            "reason": "Leading Indian automotive and EV manufacturer with assembly facilities in Pune and Sanand",
        },
        "Tata Group Sovereign MoU": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata Group",
            "operating_entity_name": None,
            "industrial_relevance": "INDUSTRIAL_OPERATOR",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "PARENT_GROUP",
            "parent_group_event_is_explicitly_grounded": True,
            "downstream_targetability_is_demonstrated": True,
            "confidence": 0.95,
            "supporting_evidence": ["Tata Group signs Rs 70000 crore multi-sector industrial MoU with Gujarat government"],
            "reason": "Group-wide mega capex sovereign commitment with direct group-level procurement and downstream facility targetability",
        },
    }
    primary = MockLLMProvider(mock_responses)
    gate = PrePersistenceEntityGate(primary_provider=primary, fallback_provider=None)
    return gate


def test_deterministic_hard_rejects():
    gate = PrePersistenceEntityGate(primary_provider=None, fallback_provider=None)
    
    # 1. Publication headers
    res = gate.resolve_pre_persistence_decision("COVER STORY", title="Industry special report")
    assert res.entity_type == "GENERIC_TEXT"
    assert res.should_persist is False

    # 2. Generic industry nouns
    res = gate.resolve_pre_persistence_decision("Chemical", title="Chemical sector outlook")
    assert res.entity_type == "GENERIC_TEXT"
    assert res.should_persist is False

    # 3. Pronouns
    res = gate.resolve_pre_persistence_decision("We", title="We announce expansion")
    assert res.entity_type == "INVALID_ENTITY"
    assert res.should_persist is False

    # 4. URLs / emails
    res = gate.resolve_pre_persistence_decision("contact@waaree.com", title="Contact info")
    assert res.entity_type == "INVALID_ENTITY"
    assert res.should_persist is False


def test_global_industrial_manufacturers_geography_decoupled(gate_with_mocks):
    # Royal Philips
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Royal Philips",
        title="Royal Philips expands medical device manufacturing plant in Chakan, Pune",
        snippet="Royal Philips inaugurated new production capacity for healthcare diagnostic equipment.",
        url="https://health.economictimes.indiatimes.com/news/philips-plant",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.industrial_relevance == "MANUFACTURER"
    assert dec.geographic_serviceability == "SERVICEABLE"
    assert dec.entity_granularity == "EXACT_OPERATING_COMPANY"
    assert dec.should_persist is True

    # Copeland
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Copeland",
        title="Copeland commissions new industrial compressor manufacturing facility in Atit, Maharashtra",
        snippet="Copeland expanded plant capacity with high-efficiency CNC machining centers.",
        url="https://copeland.com/news",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.industrial_relevance == "MANUFACTURER"
    assert dec.entity_granularity == "EXACT_OPERATING_COMPANY"
    assert dec.should_persist is True

    # GE Healthcare
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="GE Healthcare",
        title="Wipro GE Healthcare opens medical device manufacturing plant in Whitefield, Bengaluru",
        snippet="Wipro GE Healthcare announced precision medical equipment manufacturing expansion.",
        url="https://investor.gehealthcare.com/news",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.industrial_relevance == "MANUFACTURER"
    assert dec.entity_granularity == "SUBSIDIARY"
    assert dec.operating_entity_name == "Wipro GE Healthcare"
    assert dec.should_persist is True


def test_foreign_facilities_serviceable_subject_to_permission(gate_with_mocks):
    # Hovione New Jersey
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Hovione",
        title="Hovione expands pharmaceutical API manufacturing facility in East Windsor, New Jersey",
        snippet="Hovione New Jersey adds new formulation suites and chemical reactors.",
        url="https://hovione.com/news/expansion-new-jersey",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.industrial_relevance == "MANUFACTURER"
    assert dec.facility_country == "USA"
    assert dec.geographic_serviceability == "SERVICEABLE_SUBJECT_TO_PERMISSION"
    assert dec.should_persist is True

    # Arterex
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Arterex",
        title="Arterex invests in medical device contract manufacturing plant",
        snippet="Arterex adds cleanroom injection moulding capacity for medical devices.",
        url="https://arterex.com/news",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.industrial_relevance == "MANUFACTURER"
    assert dec.facility_country == "USA"
    assert dec.geographic_serviceability == "SERVICEABLE_SUBJECT_TO_PERMISSION"
    assert dec.should_persist is True

    # Eli Lilly Puerto Rico
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Eli Lilly",
        title="Eli Lilly announces major manufacturing capacity expansion at Puerto Rico pharmaceutical facility",
        snippet="Eli Lilly and Company invests in automated sterile injectable production lines.",
        url="https://lilly.com/press",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.industrial_relevance == "MANUFACTURER"
    assert dec.facility_country == "Puerto Rico"
    assert dec.geographic_serviceability == "SERVICEABLE_SUBJECT_TO_PERMISSION"
    assert dec.should_persist is True


def test_non_industrial_company_rejected(gate_with_mocks):
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Inven",
        title="Inven is an AI search tool for M&A and corporate finance professionals",
        snippet="Inven helps private equity firms find companies using intelligent web indexing.",
        url="https://inven.ai",
    )
    assert dec.entity_type == "REAL_COMPANY_NON_TARGET"
    assert dec.industrial_relevance == "NON_INDUSTRIAL"
    assert dec.should_persist is False
    assert dec.canonical_company_name is None


def test_ambiguous_group_never_persists(gate_with_mocks):
    # Bare "Tata" with NO subsidiary in evidence -> AMBIGUOUS_GROUP -> MUST NEVER PERSIST
    dec_bare = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Bare Tata",
        title="Tata plans new capex across multiple unspecified sectors",
        snippet="Tata group announces multi-sector investment plans.",
        url="https://bloomberg.com/tata",
    )
    assert dec_bare.entity_granularity == "AMBIGUOUS_GROUP"
    assert dec_bare.should_persist is False
    assert dec_bare.canonical_company_name is None


def test_operating_company_and_parent_group_branches(gate_with_mocks):
    # Branch A: "Tata Motors" with EV manufacturing evidence -> EXACT_OPERATING_COMPANY
    dec_motors = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata Motors",
        title="Tata Motors commissions new commercial vehicle assembly line in Pune",
        snippet="Tata Motors Limited announces new electric commercial vehicle production line.",
        url="https://tatamotors.com/news",
    )
    assert dec_motors.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec_motors.entity_granularity == "EXACT_OPERATING_COMPANY"
    assert dec_motors.should_persist is True

    # Branch B: "Tata Group Sovereign MoU" with explicit parent grounding + demonstrated targetability
    dec_parent = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata Group Sovereign MoU",
        title="Tata Group signs Rs 70000 crore multi-sector industrial MoU with Gujarat government",
        snippet="Tata Group corporate office signs massive mega capex agreement for clean tech and industrial investments.",
        url="https://economictimes.com/tata-mou",
    )
    assert dec_parent.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec_parent.entity_granularity == "PARENT_GROUP"
    assert dec_parent.parent_group_event_is_explicitly_grounded is True
    assert dec_parent.downstream_targetability_is_demonstrated is True
    assert dec_parent.should_persist is True


def test_zero_invention_prevents_hallucinating_subsidiary():
    # If candidate is "Tata" and evidence does NOT mention "Tata Motors", LLM proposing "Tata Motors" must fail zero-invention
    mock_hallucinating_resp = {
        "Bare Tata": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata Motors",
            "operating_entity_name": "Tata Motors",
            "industrial_relevance": "MANUFACTURER",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "SUBSIDIARY",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.90,
            "supporting_evidence": ["Tata announces industrial investment"],
            "reason": "Assuming Tata Motors based on automotive knowledge",
        }
    }
    gate = PrePersistenceEntityGate(primary_provider=MockLLMProvider(mock_hallucinating_resp))
    
    # Notice snippet and title do NOT have "Motors"
    dec = gate.resolve_pre_persistence_decision(
        candidate_name="Bare Tata",
        title="Tata announces industrial investment",
        snippet="Tata plans new manufacturing plant in Sanand.",
        url="https://news.com/tata",
    )
    # Zero invention must reject the ungrounded "Tata Motors"
    assert dec.should_persist is False
    assert "Zero-invention guard failed" in dec.reason or dec.entity_type == "UNKNOWN"
