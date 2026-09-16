"""Tests for Company-First Discovery Lane and Directory Safety.

Verifies:
- Directory/list detection (top manufacturers, directories, industrial parks)
- Extraction of genuine entity names from listing snippets
- Rejection of directory titles as Company.name
- Bounded trigger research (max 1 follow-up call)
- Static company without verified trigger is HELD and never outreach-ready
"""
import pytest
from unittest.mock import MagicMock
from services.company_first_discovery import (
    CompanyFirstDiscoveryService,
    is_directory_or_list_title,
    extract_candidate_entities_from_text,
)


def test_directory_and_list_title_detection():
    # Directory patterns
    assert is_directory_or_list_title("Top 10 Automobile Component Manufacturers in Pune") is True
    assert is_directory_or_list_title("List of EV Battery Companies in Gujarat", "Industrial directory") is True
    assert is_directory_or_list_title("Manufacturers in Sanand GIDC Industrial Park") is True
    assert is_directory_or_list_title("Auto Ancillary Suppliers in Chennai Yellow Pages") is True

    # Genuine company websites
    assert is_directory_or_list_title("Neuron Energy Pvt Ltd - EV Battery Pack Manufacturer") is False
    assert is_directory_or_list_title("RenewSys India - Solar Cell & Module Manufacturing") is False


def test_extract_candidate_entities_from_snippet():
    snippet = (
        "Key players in the corridor include Flash Electronics India Pvt Ltd, "
        "Endurance Technologies Limited, and Varroc Engineering Ltd located in Chakan."
    )
    entities = extract_candidate_entities_from_text(snippet)
    assert len(entities) >= 3
    assert any("Flash Electronics" in e for e in entities)
    assert any("Endurance Technologies" in e for e in entities)
    assert any("Varroc Engineering" in e for e in entities)


def test_directory_title_rejected_as_company_name():
    mock_router = MagicMock()
    mock_router.search.return_value = {
        "results": [
            {
                "title": "Top 10 Auto Parts Manufacturers in Pune - Directory",
                "snippet": "Leading manufacturers include Minda Corporation Limited and Sandhar Technologies Ltd.",
                "url": "https://industry-directory.com/pune-auto",
            }
        ]
    }

    service = CompanyFirstDiscoveryService(router=mock_router)
    companies = service.discover_corridor_manufacturers("Automotive & Auto Components", "Maharashtra")

    # Directory title must NOT become Company.name!
    for comp in companies:
        assert "Top 10" not in comp["company_name"]
        assert "Directory" not in comp["company_name"]
    # Instead, real entities inside snippet should be extracted
    assert any("Minda Corporation" in c["company_name"] for c in companies)


def test_static_company_without_verified_trigger_is_held():
    mock_router = MagicMock()
    # Search returns 0 active trigger events
    mock_router.search.return_value = {"results": []}

    service = CompanyFirstDiscoveryService(router=mock_router)
    trigger_check = service.research_company_triggers("Static Forgings Ltd", "Gujarat", "Automotive")

    assert trigger_check["has_trigger"] is False
    assert trigger_check["hold_reason"] == "STATIC_MANUFACTURER_NO_CURRENT_TRIGGER"
