"""Authoritative Unit & Semantic Tests for Task 3D.1E.1A.

Tests:
1. Global Industrial Companies (Geography Decoupled from Target Status):
   - Royal Philips (healthcare/medical device manufacturing) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - Copeland (HVAC/compressor manufacturing) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - GE Healthcare (medical systems/hardware manufacturing) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - Hovione New Jersey (API/pharma manufacturing facility) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
   - Eli Lilly Puerto Rico (pharma formulation facility) -> TARGET_INDUSTRIAL_COMPANY (Branch A)
2. Non-Industrial Commercial Business Models:
   - Inven (B2B SaaS / search software) -> REAL_COMPANY_NON_TARGET (should_persist = False)
3. Explicit Granularity & Facility Separation Tests (Task 3D.1E.1A Section 6):
   - "Tata" + Sanand EV plant evidence + no named operating subsidiary -> AMBIGUOUS_GROUP -> should_persist = False
   - "Tata Motors" + Sanand plant evidence -> TARGET_INDUSTRIAL_COMPANY -> EXACT_OPERATING_COMPANY / SUBSIDIARY -> should_persist = True
   - "Tata Group" + explicit Tata Group-level MoU + actionable downstream evidence -> PARENT_GROUP -> should_persist = True
   - "Hovione New Jersey" + evidence names Hovione manufacturing site -> company = Hovione, facility = New Jersey site, NOT subsidiary -> should_persist = True
4. Special Cases Audit Verification (Task 3D.1E.1A Section 3):
   - Tata Group, Tata, IAMPL, GE Healthcare / Wipro GE Healthcare, Hovione New Jersey, Amara Raja Advanced Technologies
5. Zero-Invention Enforcement:
   - Candidate "Tata" where LLM hallucinates "Tata Motors" but "Tata Motors" is NOT in evidence -> ungrounded, demoted, should_persist = False
6. Preserved Junk Suppression:
   - Deterministic rejects (pronouns, domains, headers, fragments)
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

    def call(self, **kwargs):
        self.call_count += 1
        messages = kwargs.get("messages", [])
        prompt_text = messages[0]["content"] if messages else kwargs.get("prompt", "")
        
        for match_key, resp in sorted(self.responses.items(), key=lambda x: len(x[0]), reverse=True):
            if match_key.lower() in prompt_text.lower():
                mock_resp = MagicMock()
                mock_resp.parse_json.return_value = resp
                return mock_resp
        
        mock_resp = MagicMock()
        mock_resp.parse_json.return_value = {
            "entity_type": "UNKNOWN",
            "canonical_company_name": None,
            "industrial_relevance": "UNKNOWN",
            "facility_name": None,
            "facility_country": None,
            "geographic_serviceability": "UNKNOWN",
            "entity_granularity": "UNKNOWN",
            "operating_entity_name": None,
            "evidence_supporting_entity_relationship": None,
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.5,
            "supporting_evidence": [],
            "reason": "Default mock unknown",
        }
        return mock_resp

    complete = call


@pytest.fixture
def gate_with_mocks():
    mock_responses = {
        "Royal Philips": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Royal Philips",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Chakan manufacturing facility",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Direct operating manufacturer",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Royal Philips expands medical device manufacturing plant in Chakan, Pune"],
            "reason": "Authentic medical device and healthcare hardware manufacturer with plant in Chakan, Pune",
        },
        "Copeland": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Copeland",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Atit compressor plant",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Direct industrial operating manufacturer",
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
            "facility_name": "Whitefield precision medical equipment plant",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "SUBSIDIARY",
            "evidence_supporting_entity_relationship": "Wipro GE Healthcare operating subsidiary under PLI scheme",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Wipro GE Healthcare opens medical device manufacturing plant in Whitefield, Bengaluru"],
            "reason": "Precision medical technology and healthcare equipment manufacturer in Whitefield",
        },
        "Hovione New Jersey": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Hovione",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "New Jersey manufacturing site",
            "facility_country": "USA",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Direct CDMO manufacturer operating New Jersey facility",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Hovione expands pharmaceutical manufacturing site in New Jersey, adding commercial spray drying capacity"],
            "reason": "Corporate manufacturer Hovione operating pharmaceutical manufacturing facility in New Jersey",
        },
        "Hovione": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Hovione",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "New Jersey manufacturing site",
            "facility_country": "USA",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Direct operating manufacturer",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Hovione expands pharmaceutical API manufacturing facility in East Windsor, New Jersey"],
            "reason": "Contract development and manufacturing organization (CDMO) operating industrial pharmaceutical plants globally",
        },
        "Arterex": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Arterex",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Medical component moulding plant",
            "facility_country": "USA",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Direct operating medical contract manufacturer",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Arterex invests in medical device contract manufacturing plant"],
            "reason": "Authentic medical device contract manufacturer operating precision cleanroom moulding and assembly plants",
        },
        "Eli Lilly": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Eli Lilly",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Puerto Rico injectable formulation plant",
            "facility_country": "Puerto Rico",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Direct pharmaceutical manufacturer",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Eli Lilly expands injectable drug formulation facility in Carolina, Puerto Rico"],
            "reason": "Global biopharmaceutical manufacturer expanding physical production line in Puerto Rico",
        },
        "Inven": {
            "entity_type": "REAL_COMPANY_NON_TARGET",
            "canonical_company_name": None,
            "operating_entity_name": None,
            "industrial_relevance": "NON_INDUSTRIAL",
            "facility_name": None,
            "facility_country": "Finland",
            "geographic_serviceability": "SERVICEABLE_SUBJECT_TO_PERMISSION",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Pure software company",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.98,
            "supporting_evidence": ["Inven is an AI search tool for M&A and corporate finance"],
            "reason": "B2B SaaS software indexing platform; not a physical manufacturing or engineering plant target",
        },
        "IAMPL": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "IAMPL",
            "operating_entity_name": "International Aerospace Manufacturing Pvt. Ltd.",
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Hosur aero-engine plant",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "JV",
            "evidence_supporting_entity_relationship": "50:50 joint venture between Rolls-Royce and HAL",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["International Aerospace Manufacturing Pvt. Ltd. (IAMPL), a 50:50 joint venture between Rolls-Royce and HAL, expands aero-engine components manufacturing in Hosur."],
            "reason": "Authentic aerospace joint venture operating precision component manufacturing facility",
        },
        "Amara Raja Advanced Technologies": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Amara Raja Advanced Technologies",
            "operating_entity_name": "Amara Raja Advanced Technologies",
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Telangana 16 GWh gigafactory",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "SUBSIDIARY",
            "evidence_supporting_entity_relationship": "Advanced cell technology operating subsidiary of Amara Raja",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Amara Raja Advanced Technologies sets up 16 GWh lithium-ion cell gigafactory and battery pack manufacturing facility in Telangana."],
            "reason": "Operating battery technology subsidiary establishing gigafactory",
        },
        "Tata": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Sanand EV battery plant",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "AMBIGUOUS_GROUP",
            "evidence_supporting_entity_relationship": "Brand 'Tata' announced plant but evidence does not name specific operating subsidiary",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.70,
            "supporting_evidence": ["Tata commits Rs 13,000 crore investment for EV lithium-ion battery plant in Sanand, Gujarat."],
            "reason": "Bare conglomerate/brand name; plant location does not identify which operating entity runs the facility",
        },
        "Tata Motors": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata Motors",
            "operating_entity_name": "Tata Motors",
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Sanand EV manufacturing facility",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "EXACT_OPERATING_COMPANY",
            "evidence_supporting_entity_relationship": "Operating automotive manufacturing company",
            "parent_group_event_is_explicitly_grounded": False,
            "downstream_targetability_is_demonstrated": False,
            "confidence": 0.95,
            "supporting_evidence": ["Tata Motors inaugurates new EV manufacturing facility in Sanand, Gujarat."],
            "reason": "Authentic automotive and EV operating OEM with named manufacturing plant in Sanand",
        },
        "Tata Group": {
            "entity_type": "TARGET_INDUSTRIAL_COMPANY",
            "canonical_company_name": "Tata Group",
            "operating_entity_name": None,
            "industrial_relevance": "MANUFACTURER",
            "facility_name": "Multi-sector manufacturing hubs",
            "facility_country": "India",
            "geographic_serviceability": "SERVICEABLE",
            "entity_granularity": "PARENT_GROUP",
            "evidence_supporting_entity_relationship": "Group-wide mega capex sovereign agreement with demonstrated downstream targetability",
            "parent_group_event_is_explicitly_grounded": True,
            "downstream_targetability_is_demonstrated": True,
            "confidence": 0.92,
            "supporting_evidence": ["Tata Group signs group-level MoU with Tamil Nadu government outlining Rs 12,000 crore investments across industrial manufacturing hubs."],
            "reason": "Group-level sovereign MoU with demonstrated downstream industrial targetability",
        },
    }

    mock_provider = MockLLMProvider(mock_responses)
    return PrePersistenceEntityGate(primary_provider=mock_provider, fallback_provider=mock_provider)


# ==============================================================================
# SECTION 6 TESTS: Explicit Tests Mandated by Task 3D.1E.1A
# ==============================================================================

def test_tata_bare_with_sanand_ev_plant_evidence_becomes_ambiguous_group_and_rejects(gate_with_mocks):
    """'Tata' + Sanand EV plant evidence + no named operating subsidiary
    -> AMBIGUOUS_GROUP
    -> should_persist False
    """
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata",
        title="EV battery cell manufacturer Gujarat announces new gigafactory investment",
        snippet="Tata commits Rs 13,000 crore investment for EV lithium-ion battery plant in Sanand, Gujarat.",
        url="https://bloomberg.com/tata-sanand-ev-plant",
        industry="EV & Battery Systems",
    )
    assert dec.entity_granularity == "AMBIGUOUS_GROUP"
    assert dec.should_persist is False
    assert dec.canonical_company_name is None
    assert dec.operating_entity_name is None
    assert "held from persistence" in dec.reason or "without evidence-grounded" in dec.reason


def test_tata_motors_with_sanand_plant_evidence_persists(gate_with_mocks):
    """'Tata Motors' + Sanand plant evidence
    -> TARGET_INDUSTRIAL_COMPANY
    -> EXACT_OPERATING_COMPANY / SUBSIDIARY as actually evidenced
    -> persist True
    """
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata Motors",
        title="Automotive OEM Gujarat announces new electric vehicle assembly plant",
        snippet="Tata Motors inaugurates new EV manufacturing facility in Sanand, Gujarat.",
        url="https://tatamotors.com/sanand-facility",
        industry="Automotive & Auto Components",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.entity_granularity in ("EXACT_OPERATING_COMPANY", "SUBSIDIARY")
    assert dec.should_persist is True
    assert dec.canonical_company_name == "Tata Motors"


def test_tata_group_with_explicit_group_mou_and_downstream_evidence_persists(gate_with_mocks):
    """'Tata Group' + explicit Tata Group-level MoU + actionable downstream evidence
    -> PARENT_GROUP
    -> persist True
    """
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata Group",
        title="Tamil Nadu Global Investors Meet mega capex investment announcement",
        snippet="Tata Group signs group-level MoU with Tamil Nadu government outlining Rs 12,000 crore investments across industrial manufacturing hubs.",
        url="https://thehindu.com/tata-group-mou",
        industry="Industrial Conglomerate",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.entity_granularity == "PARENT_GROUP"
    assert dec.parent_group_event_is_explicitly_grounded is True
    assert dec.downstream_targetability_is_demonstrated is True
    assert dec.should_persist is True
    assert dec.canonical_company_name == "Tata Group"


def test_hovione_new_jersey_separates_facility_and_does_not_invent_subsidiary(gate_with_mocks):
    """'Hovione New Jersey' + evidence names Hovione manufacturing site
    -> company = Hovione
    -> facility = New Jersey site
    -> do NOT invent SUBSIDIARY
    """
    dec = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Hovione New Jersey",
        title="CDMO expands pharmaceutical manufacturing site capacity",
        snippet="Hovione expands pharmaceutical manufacturing site in New Jersey, adding commercial spray drying capacity.",
        url="https://hovione.com/news/new-jersey-expansion",
        industry="Pharmaceuticals & Bulk Drugs",
    )
    assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
    assert dec.canonical_company_name == "Hovione"
    assert dec.facility_name in ("New Jersey manufacturing site", "New Jersey site", "New Jersey")
    assert dec.facility_country == "USA"
    assert dec.entity_granularity == "EXACT_OPERATING_COMPANY"  # NOT SUBSIDIARY!
    assert dec.geographic_serviceability == "SERVICEABLE_SUBJECT_TO_PERMISSION"
    assert dec.should_persist is True


# ==============================================================================
# SECTION 3 TESTS: Audit Special Cases Mandated by Task 3D.1E.1A
# ==============================================================================

def test_audit_special_cases_semantics(gate_with_mocks):
    """Recheck all special cases:
    Tata Group, Tata, IAMPL, GE Healthcare / Wipro GE Healthcare, Hovione New Jersey, Amara Raja Advanced Technologies
    """
    # 1. Tata Group (MoU) -> PARENT_GROUP -> Persist
    dec_tata_group = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata Group",
        title="Tamil Nadu industrial MoU",
        snippet="Tata Group signs group-level MoU with Tamil Nadu government outlining Rs 12,000 crore investments across industrial manufacturing hubs.",
    )
    assert dec_tata_group.entity_granularity == "PARENT_GROUP"
    assert dec_tata_group.should_persist is True

    # 2. Tata (Bare with Sanand Plant) -> AMBIGUOUS_GROUP -> Blocked
    dec_tata_bare = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Tata",
        title="Sanand plant investment",
        snippet="Tata commits Rs 13,000 crore investment for EV lithium-ion battery plant in Sanand, Gujarat.",
    )
    assert dec_tata_bare.entity_granularity == "AMBIGUOUS_GROUP"
    assert dec_tata_bare.should_persist is False

    # 3. IAMPL -> JV -> Persist
    dec_iampl = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="IAMPL",
        title="Hosur aero-engine plant",
        snippet="International Aerospace Manufacturing Pvt. Ltd. (IAMPL), a 50:50 joint venture between Rolls-Royce and HAL, expands aero-engine components manufacturing in Hosur.",
    )
    assert dec_iampl.entity_granularity == "JV"
    assert dec_iampl.operating_entity_name == "International Aerospace Manufacturing Pvt. Ltd."
    assert dec_iampl.should_persist is True

    # 4. GE Healthcare / Wipro GE Healthcare -> SUBSIDIARY -> Persist
    dec_ge = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="GE Healthcare",
        title="Whitefield precision plant",
        snippet="Wipro GE Healthcare opens medical device manufacturing plant in Whitefield, Bengaluru under the PLI scheme.",
    )
    assert dec_ge.entity_granularity == "SUBSIDIARY"
    assert dec_ge.operating_entity_name == "Wipro GE Healthcare"
    assert dec_ge.should_persist is True

    # 5. Hovione New Jersey -> EXACT_OPERATING_COMPANY -> Persist
    dec_hovione = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Hovione New Jersey",
        title="New Jersey spray drying",
        snippet="Hovione expands pharmaceutical manufacturing site in New Jersey, adding commercial spray drying capacity.",
    )
    assert dec_hovione.canonical_company_name == "Hovione"
    assert dec_hovione.entity_granularity == "EXACT_OPERATING_COMPANY"
    assert dec_hovione.should_persist is True

    # 6. Amara Raja Advanced Technologies -> SUBSIDIARY -> Persist
    dec_amara = gate_with_mocks.resolve_pre_persistence_decision(
        candidate_name="Amara Raja Advanced Technologies",
        title="Telangana gigafactory",
        snippet="Amara Raja Advanced Technologies sets up 16 GWh lithium-ion cell gigafactory and battery pack manufacturing facility in Telangana.",
    )
    assert dec_amara.entity_granularity == "SUBSIDIARY"
    assert dec_amara.operating_entity_name == "Amara Raja Advanced Technologies"
    assert dec_amara.should_persist is True


# ==============================================================================
# OTHER GENERAL AND REGRESSION TESTS
# ==============================================================================

def test_deterministic_hard_rejects():
    gate = PrePersistenceEntityGate()

    assert gate.deterministic_hard_reject("we").entity_type == "INVALID_ENTITY"
    assert gate.deterministic_hard_reject("it").entity_type == "INVALID_ENTITY"
    assert gate.deterministic_hard_reject("contact@vendor.com").entity_type == "INVALID_ENTITY"
    assert gate.deterministic_hard_reject("https://example.com").entity_type == "INVALID_ENTITY"
    assert gate.deterministic_hard_reject("COVER STORY").entity_type == "GENERIC_TEXT"
    assert gate.deterministic_hard_reject("Chemical").entity_type == "GENERIC_TEXT"
    assert gate.deterministic_hard_reject("Waaree\'s N").entity_type == "HEADLINE_FRAGMENT"
    assert gate.deterministic_hard_reject("OFC industry in a take").entity_type == "HEADLINE_FRAGMENT"


def test_global_industrial_manufacturers_geography_decoupled(gate_with_mocks):
    for cand in ["Royal Philips", "Copeland", "GE Healthcare", "Hovione New Jersey", "Arterex", "Eli Lilly"]:
        dec = gate_with_mocks.resolve_pre_persistence_decision(
            candidate_name=cand,
            title=f"{cand} announces new facility investment",
            snippet=f"{cand} expands physical production capacity and manufacturing operations.",
            url="https://industry-reports.com/plant-news",
        )
        assert dec.entity_type == "TARGET_INDUSTRIAL_COMPANY"
        assert dec.industrial_relevance in ("MANUFACTURER", "INDUSTRIAL_OPERATOR")
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


def test_zero_invention_prevents_hallucinating_subsidiary():
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
    
    dec = gate.resolve_pre_persistence_decision(
        candidate_name="Bare Tata",
        title="Tata announces industrial investment",
        snippet="Tata plans new manufacturing plant in Sanand.",
        url="https://news.com/tata",
    )
    assert dec.should_persist is False
    assert "Zero-invention guard failed" in dec.reason or dec.entity_type == "UNKNOWN" or dec.entity_granularity == "AMBIGUOUS_GROUP"
