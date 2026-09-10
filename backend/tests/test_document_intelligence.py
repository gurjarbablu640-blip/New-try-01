import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from services.document_intelligence import (
    analyze_document,
    extract_entities_from_text,
    hash_document_bytes,
    _DOCUMENT_CACHE,
)


class DocumentIntelligenceTests(unittest.TestCase):
    def setUp(self):
        _DOCUMENT_CACHE.clear()

    def test_entity_extraction_from_technical_brochure(self):
        sample_text = """
        Valeo India Private Limited
        Plant-1, Sanand Industrial Area, Ahmedabad, Gujarat
        
        Contact:
        Abhijit Biswal - Quality Manager
        Email: abhijit.biswal@valeo.com
        Mobile: +91 98765 43210
        
        New CNC Machining Bay Commissioning & Expansion
        We require NABL accredited calibration for our new CMM and Bourdon Tube Pressure Gauge.
        Annual Maintenance & Calibration Scope ISO/IEC 17025 compliance required.
        """
        entities = extract_entities_from_text(sample_text, "brochure.pdf")

        # 1. Person & Designation
        names = [p["name"] for p in entities["persons"]]
        self.assertIn("Abhijit Biswal", names)
        self.assertEqual(entities["persons"][0]["designation"], "Quality Manager")

        # 2. Email & Phone
        self.assertIn("abhijit.biswal@valeo.com", entities["emails"])
        self.assertEqual(len(entities["phones"]), 1)
        self.assertEqual(entities["phones"][0]["phone_type"], "PERSONAL_MOBILE")

        # 3. Location & Plant
        self.assertIn("Sanand", entities["locations"])
        self.assertIn("Plant-1", entities["plants"])

        # 4. Calibration Triggers & Instruments
        self.assertTrue(entities["has_calibration_demand"])
        self.assertIn("expansion", entities["triggers"])
        self.assertIn("commissioning", entities["triggers"])
        self.assertIn("cmm", entities["instruments"])
        self.assertIn("pressure gauge", entities["instruments"])

    def test_adaptive_routing_to_pypdf_for_simple_pdf(self):
        fixture = b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n2 0 obj<< /Type /Pages /Kids [] /Count 0 >>endobj\ntrailer<< /Root 1 0 R >>\n%%EOF"
        with patch("services.document_intelligence.extract_pdf_bytes") as mock_pypdf:
            mock_pypdf.return_value = SimpleNamespace(
                status="SUCCESS",
                text="Simple text with more than one hundred characters of extracted content describing plant calibration scope and requirements.",
                adapter="pypdf",
            )
            res = analyze_document(fixture, "simple.pdf", force_docling=False)
            self.assertEqual(res["adapter_used"], "pypdf")
            mock_pypdf.assert_called_once()

    def test_routing_to_docling_when_forced_or_complex(self):
        fixture = b"%PDF-1.4\ncomplex mock pdf bytes"

        class ConvertedDoc:
            def export_to_markdown(self):
                return "# Technical Specification\nPlant Head: Ravi Singh\nEmail: ravi.singh@kehems.com\nFacility: Indore Unit 2"

        class MockConverter:
            def convert(self, path):
                return ConvertedDoc()

        res = analyze_document(fixture, "complex.pdf", force_docling=True, docling_converter=MockConverter())
        self.assertEqual(res["adapter_used"], "docling")
        self.assertIn("ravi.singh@kehems.com", res["entities"]["emails"])
        self.assertIn("Indore", res["entities"]["locations"])

    def test_sha256_result_caching(self):
        fixture = b"%PDF-1.4\nrepeat bytes for caching test"
        with patch("services.document_intelligence.extract_pdf_bytes") as mock_pypdf:
            mock_pypdf.return_value = SimpleNamespace(
                status="SUCCESS",
                text="A sufficiently long text string for the caching test to ensure valid parsing and entity discovery across calls.",
                adapter="pypdf",
            )
            res1 = analyze_document(fixture, "test.pdf")
            self.assertFalse(res1["cache_hit"])
            self.assertEqual(mock_pypdf.call_count, 1)

            # Second call with identical content should hit cache
            res2 = analyze_document(fixture, "test.pdf")
            self.assertTrue(res2["cache_hit"])
            self.assertEqual(mock_pypdf.call_count, 1)

    def test_crm_deduplication_match(self):
        db = MagicMock()
        mock_person = SimpleNamespace(id=42, full_name="Abhijit Biswal", company_id=10)
        db.query.return_value.filter.return_value.first.return_value = mock_person
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = []

        fixture = b"%PDF-1.4\nminimal"
        with patch("services.document_intelligence.extract_pdf_bytes") as mock_pypdf:
            mock_pypdf.return_value = SimpleNamespace(
                status="SUCCESS",
                text="Abhijit Biswal — abhijit.biswal@valeo.com — Sanand Plant",
                adapter="pypdf",
            )
            res = analyze_document(fixture, "test.pdf", db=db)
            self.assertTrue(any(m["type"] == "PERSON" and m["id"] == 42 for m in res["crm_dedup_matches"]))


if __name__ == "__main__":
    unittest.main()
