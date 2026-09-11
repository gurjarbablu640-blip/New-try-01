"""Tests for Evidence Provenance Tracker and Leakage Prevention."""
import unittest
from services.evidence_provenance import (
    EvidenceProvenanceRecord,
    check_evidence_leakage,
    compute_text_hash,
    extract_domain,
    filter_valid_evidence,
    tag_evidence,
)


class TestEvidenceProvenance(unittest.TestCase):
    def test_deterministic_text_hash_and_domain(self):
        text = "Dixon Technologies opens new 200,000 sq ft manufacturing plant in Noida"
        h1 = compute_text_hash(text)
        h2 = compute_text_hash(text)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)

        url = "https://www.dixoninfo.com/investor-relations/announcement-2026.html"
        self.assertEqual(extract_domain(url), "www.dixoninfo.com")

    def test_record_generation_with_fields(self):
        rec = EvidenceProvenanceRecord(
            evidence_id="",
            claim_type="FACILITY_LOCATION",
            company="Dixon Technologies",
            facility="Noida Plant",
            person="Sunil Kumar",
            source_url="https://www.dixoninfo.com/plants/noida",
            snippet="Noida plant houses advanced SMT lines and quality testing labs.",
        )
        self.assertTrue(rec.evidence_id.startswith("ev_"))
        self.assertEqual(rec.source_domain, "www.dixoninfo.com")
        self.assertTrue(len(rec.raw_text_hash) > 0)
        self.assertEqual(rec.claim_type, "FACILITY_LOCATION")
        self.assertIn("source", rec.provenance)

    def test_prevent_candidate_leakage(self):
        """Old candidate Rakesh Sharma's evidence must NOT be attributed to Sunil Kumar."""
        rakesh_ev = tag_evidence(
            evidence={"email": "rakesh@dixon.com", "verified_duties": "Head of Quality"},
            person_name="Rakesh Sharma",
            company="Dixon Technologies",
            facility="Noida",
            claim_type="PERSON_IDENTITY",
            snippet="Rakesh Sharma oversees plant quality at Noida.",
        )

        res = check_evidence_leakage(
            rakesh_ev,
            target_company="Dixon Technologies",
            target_facility="Noida",
            target_person="Sunil Kumar",
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(res.leakage_detected)
        self.assertEqual(res.leakage_type, "CANDIDATE_LEAKAGE")
        self.assertEqual(res.stale_person, "Rakesh Sharma")
        self.assertIn("cannot be used for target candidate 'Sunil Kumar'", res.reason)

    def test_prevent_facility_leakage(self):
        """Facility A evidence cannot be applied to Facility B."""
        noida_ev = tag_evidence(
            evidence={"calibration_need": "CMM & Torque Calibrations"},
            person_name="Sunil Kumar",
            company="Dixon Technologies",
            facility="Noida Phase II",
            claim_type="CALIBRATION_NEED",
            snippet="Noida Phase II houses precision CNC machining and CMM inspection.",
        )

        res = check_evidence_leakage(
            noida_ev,
            target_company="Dixon Technologies",
            target_facility="Dahej Plant",
            target_person="Sunil Kumar",
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(res.leakage_detected)
        self.assertEqual(res.leakage_type, "FACILITY_LEAKAGE")
        self.assertEqual(res.stale_facility, "Noida Phase II")

    def test_prevent_company_leakage(self):
        """Company A evidence cannot be applied to Company B."""
        bharat_ev = tag_evidence(
            evidence={"capex_amount": "Rs 250 Cr"},
            person_name="Amit Patel",
            company="Bharat Forge",
            facility="Pune",
            claim_type="CAPEX_TRIGGER",
        )

        res = check_evidence_leakage(
            bharat_ev,
            target_company="Dixon Technologies",
            target_facility="Pune",
            target_person="Amit Patel",
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(res.leakage_detected)
        self.assertEqual(res.leakage_type, "COMPANY_LEAKAGE")
        self.assertEqual(res.stale_company, "Bharat Forge")

    def test_prevent_trigger_context_leakage(self):
        """Obsolete trigger context cannot leak to different trigger."""
        ev = tag_evidence(
            evidence={"trigger": "EV expansion"},
            person_name="Sunil Kumar",
            company="Dixon Technologies",
            facility="Noida",
            trigger_context="2025_EV_EXPANSION",
        )

        res = check_evidence_leakage(
            ev,
            target_company="Dixon Technologies",
            target_facility="Noida",
            target_person="Sunil Kumar",
            target_trigger="2026_DEFENSE_ELECTRONICS",
        )
        self.assertFalse(res.is_valid)
        self.assertTrue(res.leakage_detected)
        self.assertEqual(res.leakage_type, "TRIGGER_LEAKAGE")

    def test_filter_valid_evidence_batch(self):
        """Filtering a mixed batch of evidence isolates only valid target evidence."""
        pool = [
            # 1. Valid for Sunil Kumar @ Dixon Noida
            tag_evidence(
                {"id": 1, "data": "valid_sunil"},
                person_name="Sunil Kumar",
                company="Dixon Technologies",
                facility="Noida",
            ),
            # 2. Leaked from Rakesh Sharma (superseded)
            tag_evidence(
                {"id": 2, "data": "rakesh_phone"},
                person_name="Rakesh Sharma",
                company="Dixon Technologies",
                facility="Noida",
            ),
            # 3. Leaked from Dahej facility
            tag_evidence(
                {"id": 3, "data": "dahej_specs"},
                person_name="Sunil Kumar",
                company="Dixon Technologies",
                facility="Dahej",
            ),
            # 4. Leaked from Bharat Forge
            tag_evidence(
                {"id": 4, "data": "bharat_forge_capex"},
                person_name="Sunil Kumar",
                company="Bharat Forge",
                facility="Noida",
            ),
        ]

        valid = filter_valid_evidence(
            pool,
            current_person="Sunil Kumar",
            current_company="Dixon Technologies",
            current_facility="Noida",
        )

        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["data"], "valid_sunil")


if __name__ == "__main__":
    unittest.main()
