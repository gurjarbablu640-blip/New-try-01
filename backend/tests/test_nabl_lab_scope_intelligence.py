"""Verification Test Suite for NABL Lab Scope Intelligence & 300-Lab Engine."""
import unittest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, SessionLocal, sync_engine
from models.lab_scope import NABLLabScope, NABLScopeParameter
from services.lab_scope_parser import (
    parse_nabl_scope_text,
    ingest_nabl_lab_scope,
    search_pan_india_lab_capabilities,
    compare_two_lab_scopes,
)


class TestNABLLabScopeIntelligence(unittest.TestCase):
    def setUp(self):
        if SessionLocal is not None and sync_engine is not None:
            Base.metadata.create_all(sync_engine)
            self.db = SessionLocal()
        else:
            self.engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(self.engine)
            Session = sessionmaker(bind=self.engine)
            self.db = Session()

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.rollback()
            self.db.close()

    def test_parse_nabl_scope_text(self):
        sample_text = """
        Certificate No: CC-2841
        Standard: ISO/IEC 17025:2017
        Laboratory: Western Metrology Center
        Validity: 2027-12-31
        Location: Pune, Maharashtra

        Schedule of Accreditation:
        1. Dimensional | Vernier Calipers | 0 to 300 mm | CMC: 12 µm | Page 2
        2. Dimensional | External Micrometers | 0 to 100 mm | CMC: 2.5 µm | Page 2
        3. Thermal | RTD Pt100 Sensors | -50 to 400 °C | CMC: 0.15 °C | Page 4
        4. Pressure | Digital Pressure Gauges | 0 to 700 bar | CMC: 0.05% FS | Page 5
        """
        parsed = parse_nabl_scope_text(sample_text, lab_name="Western Metrology Center", source_file="test_scope.txt")

        self.assertEqual(parsed["certificate_no"], "CC-2841")
        self.assertEqual(parsed["lab_name"], "Western Metrology Center")
        self.assertEqual(parsed["state"], "Maharashtra")
        self.assertEqual(len(parsed["parameters"]), 4)

        p1 = parsed["parameters"][0]
        self.assertEqual(p1["discipline"], "Mechanical")
        self.assertIn("Vernier Calipers", p1["parameter_name"])
        self.assertEqual(p1["cmc_uncertainty"], "12 µm")
        self.assertEqual(p1["source_page"], 2)

    def test_ingest_and_search_lab_scope(self):
        sample_text = """
        Certificate No: CC-9901
        Standard: ISO/IEC 17025:2017
        Laboratory: Apex Calibration Laboratory
        Location: Chennai, Tamil Nadu

        1. Mechanical | Coordinate Measuring Machine (CMM) | 1000x800x600 mm | CMC: 1.8 µm | Page 1
        2. Electro-Technical | Digital Multimeter 6.5 Digit | 0 to 1000 V | CMC: 15 ppm | Page 3
        """
        parsed = parse_nabl_scope_text(sample_text, lab_name="Apex Calibration Laboratory", source_file="apex_scope.txt")
        lab = ingest_nabl_lab_scope(self.db, parsed)

        self.assertIsNotNone(lab.id)
        self.assertEqual(lab.lab_name, "Apex Calibration Laboratory")
        self.assertEqual(lab.state, "Tamil Nadu")
        self.assertGreaterEqual(len(lab.parameters), 2)

        # Search for CMM across Pan-India
        results = search_pan_india_lab_capabilities(self.db, query="CMM", discipline=None, state=None)
        self.assertGreaterEqual(len(results), 1)
        found = any("Apex Calibration Laboratory" in r["lab_name"] for r in results)
        self.assertTrue(found)

    def test_compare_two_lab_scopes_factual(self):
        # Lab 1: Oorja Lab
        parsed1 = {
            "lab_name": "Oorja Calibration Lab Test",
            "certificate_no": "CC-1001-TEST",
            "accreditation_standard": "ISO/IEC 17025:2017",
            "validity_date": "2027-01-01",
            "state": "Maharashtra",
            "city": "Pune",
            "source_file": "oorja_scope.pdf",
            "parameters": [
                {"discipline": "Mechanical", "parameter_name": "Vernier Caliper", "range_description": "0-300mm", "cmc_uncertainty": "10 µm", "source_page": 1},
                {"discipline": "Mechanical", "parameter_name": "Micrometer", "range_description": "0-25mm", "cmc_uncertainty": "2.0 µm", "source_page": 1},
                {"discipline": "Thermal", "parameter_name": "Thermocouple", "range_description": "-40 to 1200 C", "cmc_uncertainty": "0.5 C", "source_page": 2},
            ],
        }
        lab1 = ingest_nabl_lab_scope(self.db, parsed1)

        # Lab 2: Competitor Lab
        parsed2 = {
            "lab_name": "Competitor Testing Lab Test",
            "certificate_no": "CC-2002-TEST",
            "accreditation_standard": "ISO/IEC 17025:2017",
            "validity_date": "2026-06-30",
            "state": "Gujarat",
            "city": "Vadodara",
            "source_file": "comp_scope.pdf",
            "parameters": [
                {"discipline": "Mechanical", "parameter_name": "Vernier Caliper", "range_description": "0-300mm", "cmc_uncertainty": "15 µm", "source_page": 1},
                {"discipline": "Pressure", "parameter_name": "Pressure Gauge", "range_description": "0-700 bar", "cmc_uncertainty": "0.1% FS", "source_page": 1},
            ],
        }
        lab2 = ingest_nabl_lab_scope(self.db, parsed2)

        comp = compare_two_lab_scopes(self.db, lab1.id, lab2.id)

        self.assertGreaterEqual(comp["metrics"]["common_parameters_count"], 1)
        self.assertGreaterEqual(comp["metrics"]["lab1_unique_count"], 2)
        self.assertGreaterEqual(comp["metrics"]["lab2_unique_count"], 1)
        self.assertEqual(comp["common_parameters"][0]["parameter"].lower(), "vernier caliper")


if __name__ == "__main__":
    unittest.main()
