"""Test Suite for Outreach Claim Guard & Zero Factual Invention.

Validates:
1. Detection of unapproved regional center claims ("Pune & Dahej Regional Metrology Centers").
2. Detection of unapproved turnaround SLAs ("48-to-72-hour expedited turnaround").
3. Detection of unapproved commercial guarantees / free audit claims.
4. Detection of invalid NABL certificate numbers.
5. Detection of out-of-scope calibration claims.
6. Automatic copy sanitization anchoring to official CC-3963 standards.
"""
import unittest
from services.outreach_claim_guard import (
    APPROVED_CERTIFICATE_NO,
    APPROVED_STANDARD,
    outreach_claim_guard,
)


class TestOutreachClaimGuard(unittest.TestCase):

    def test_clean_authoritative_text_passes(self):
        clean_text = (
            "Dear Rajesh,\n"
            "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate No. CC-3963).\n"
            "We provide certified calibration for precision Vernier Calipers and Micrometers with documented uncertainty budgets (CMC).\n"
            "Best regards,\nOorja Technical Services\nEngineering & Metrology Services\nAccreditation: ISO/IEC 17025:2017 (NABL CC-3963)"
        )
        report = outreach_claim_guard.audit_outreach_claims(clean_text)
        self.assertTrue(report.clean)
        self.assertEqual(len(report.violations), 0)
        self.assertFalse(report.unapproved_locations_detected)
        self.assertFalse(report.unapproved_slas_detected)

    def test_detects_unapproved_regional_centers(self):
        bad_text = "Our facilities: Pune & Dahej Regional Metrology Centers provide fast service."
        report = outreach_claim_guard.audit_outreach_claims(bad_text)
        self.assertFalse(report.clean)
        self.assertTrue(report.unapproved_locations_detected)
        violations = [v for v in report.violations if v.category == "UNAPPROVED_FACILITY_LOCATION"]
        self.assertGreaterEqual(len(violations), 1)

        # Verify sanitization strips unapproved locations
        self.assertNotIn("Pune & Dahej Regional Metrology Centers", report.sanitized_text)

    def test_detects_unapproved_turnaround_sla(self):
        bad_text = "Oorja Technical Services provides a certified 48-to-72-hour expedited turnaround with on-site calibration teams."
        report = outreach_claim_guard.audit_outreach_claims(bad_text)
        self.assertFalse(report.clean)
        self.assertTrue(report.unapproved_slas_detected)
        violations = [v for v in report.violations if v.category == "UNAPPROVED_TURNAROUND_SLA"]
        self.assertGreaterEqual(len(violations), 1)

        # Verify sanitization replaces SLA with consultative wording
        self.assertNotIn("48-to-72-hour expedited turnaround", report.sanitized_text)
        self.assertIn("ISO/IEC 17025:2017 accredited calibration", report.sanitized_text)

    def test_detects_free_audit_and_commercial_guarantees(self):
        bad_text = "We offer a 100% free audit and money-back guarantee on all calibrations."
        report = outreach_claim_guard.audit_outreach_claims(bad_text)
        self.assertFalse(report.clean)
        self.assertTrue(report.unapproved_commercial_detected)

        # Verify sanitization replaces free audit with consultative review
        self.assertNotIn("free audit", report.sanitized_text)

    def test_detects_unapproved_certificate_numbers(self):
        bad_text = "Calibrations conducted under NABL certificate CC-99999."
        report = outreach_claim_guard.audit_outreach_claims(bad_text)
        self.assertFalse(report.clean)
        violations = [v for v in report.violations if v.category == "UNAPPROVED_CERTIFICATE_NO"]
        self.assertGreaterEqual(len(violations), 1)

    def test_detects_out_of_scope_nabl_claims(self):
        unsupported_instruments = ["Liquid Chromatography HPLC Column", "Radiation dosimeter"]
        text = "Full NABL certified calibration provided for HPLC and radiation equipment."
        report = outreach_claim_guard.audit_outreach_claims(text, instruments=unsupported_instruments)
        self.assertFalse(report.clean)
        self.assertFalse(report.cc_3963_scope_validated)

    def test_detects_complimentary_drift_study_and_uncertainty_review(self):
        bad_text = "We include a free drift study and complimentary uncertainty review with all on-site visits."
        report = outreach_claim_guard.audit_outreach_claims(bad_text)
        self.assertFalse(report.clean)
        self.assertTrue(report.unapproved_commercial_detected)
        self.assertNotIn("free drift study", report.sanitized_text)
        self.assertNotIn("complimentary uncertainty review", report.sanitized_text)
        self.assertIn("measurement drift and stability analysis", report.sanitized_text)
        self.assertIn("CMC measurement uncertainty evaluation", report.sanitized_text)

    def test_detects_unapproved_pricing_and_discounts(self):
        bad_text = "We guarantee lowest price guaranteed with 20% discount on all calibration contracts."
        report = outreach_claim_guard.audit_outreach_claims(bad_text)
        self.assertFalse(report.clean)
        self.assertTrue(report.unapproved_commercial_detected)


if __name__ == "__main__":
    unittest.main()
