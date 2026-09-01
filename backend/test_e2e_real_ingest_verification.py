"""End-to-End Ingestion & Persistence Verification Test.

Tests the full upload -> parse -> extract -> review -> confirm -> database persist
loop for both NABL Scope Documents and Historical Quotations.
"""
import io
from datetime import date
from database import SessionLocal
from models.lab_scope import NABLLabScope, NABLScopeParameter
from models.sales_os import Quotation, QuotationItem
from services.document_extractor import extract_text_from_bytes
from services.lab_scope_parser import parse_nabl_scope_text, ingest_lab_scope_record
from services.historical_quote_importer import parse_historical_quote_text, ingest_historical_quotation

def run_tests():
    print("==================================================")
    print("1. TEST NABL SCOPE EXTRACTION & PERSISTENCE")
    print("==================================================")

    sample_scope_text = """
    NATIONAL ACCREDITATION BOARD FOR TESTING AND CALIBRATION LABORATORIES (NABL)
    ACCID: CC-2849
    LABORATORY: Apex Metrology & Calibration Labs Pvt Ltd
    LOCATION: Chakan MIDC, Pune, Maharashtra
    VALIDITY: Valid upto 14/08/2027
    DISCIPLINE: Mechanical & Electro-Technical Calibration

    Schedule of Accreditation:
    1. Digital Vernier Caliper | Range: 0 to 300 mm | CMC Uncertainty: ± 12 µm | Lab & Onsite
    2. External Micrometer | Range: 0 to 100 mm | CMC Uncertainty: ± 1.8 µm | Lab & Onsite
    3. Coordinate Measuring Machine (CMM) | Range: 0 to 1500 mm | CMC Uncertainty: ± 2.5 µm | Lab Only
    4. Digital Temperature Indicator / RTD | Range: -50 to 400 °C | CMC Uncertainty: ± 0.35 °C | Lab & Onsite
    5. Digital Multimeter 6.5 Digit | Range: 0 to 1000 V | CMC Uncertainty: ± 15 ppm | Lab Only
    """

    db = SessionLocal()
    try:
        # Step A: Parse
        parsed_scope = parse_nabl_scope_text(
            sample_scope_text,
            source_file="test_fixture_apex_scope.pdf",
            source_reference="Test Script: test_e2e_real_ingest_verification.py",
        )
        parsed_scope["data_provenance"] = "TEST_DATA"

        print(f"Parsed Lab: {parsed_scope['lab_name']}")
        print(f"Cert No: {parsed_scope['certificate_no']}")
        print(f"Parameters Detected: {len(parsed_scope['parameters'])}")
        assert len(parsed_scope['parameters']) == 5, "Should detect exactly 5 parameters"

        # Step B: Confirm & Ingest
        lab_record = ingest_lab_scope_record(db, parsed_scope)
        db.commit()

        # Step C: Verify in Database
        persisted_lab = db.query(NABLLabScope).filter(NABLLabScope.id == lab_record.id).first()
        print(f"Persisted Lab in DB: ID={persisted_lab.id}, Name='{persisted_lab.lab_name}', Provenance={persisted_lab.data_provenance}")
        assert persisted_lab.data_provenance == "TEST_DATA"

        param_count = db.query(NABLScopeParameter).filter(NABLScopeParameter.lab_scope_id == persisted_lab.id).count()
        print(f"Persisted Parameters in DB (should be exactly 5): {param_count}")
        assert param_count == 5, f"Expected 5 parameters, found {param_count}"

        print("\n==================================================")
        print("2. TEST HISTORICAL QUOTATION EXTRACTION & PERSISTENCE")
        print("==================================================")

        sample_quote_text = """
        TAX INVOICE / QUOTATION
        Quote No: Q-TEST-2025-0942
        Date: 12/03/2025
        Customer: M/s Bharat Forge Precision Driveline Unit
        Location: Chakan, Pune, Maharashtra

        Scope of Calibration Services:
        1. Coordinate Measuring Machine (CMM) Calibration Qty: 2 Unit Price: Rs. 18500.00
        2. Mitutoyo Height Gauge 600mm Qty: 4 Unit Price: Rs. 2200.00
        3. Digital Torque Wrench 20-200 Nm Qty: 6 Unit Price: Rs. 1400.00
        4. Gauge Block Set (Grade 0, 83 pcs) Qty: 1 Unit Price: Rs. 6500.00

        Subtotal: Rs. 60700.00
        GST (18%): Rs. 10926.00
        Grand Total: Rs. 71626.00
        Status: Won
        """

        # Step A: Parse
        parsed_quote = parse_historical_quote_text(
            sample_quote_text,
            source_file="test_fixture_quote_bharat_forge.pdf",
        )
        parsed_quote["data_provenance"] = "TEST_DATA"

        print(f"Parsed Quote No: {parsed_quote['quotation_number']}")
        print(f"Parsed Customer: {parsed_quote['customer_name']}")
        print(f"Line Items Detected: {len(parsed_quote['items'])}")
        assert len(parsed_quote['items']) == 4, "Should detect 4 line items"

        # Step B: Confirm & Ingest
        quote_record = ingest_historical_quotation(db, parsed_quote)
        db.commit()

        # Step C: Verify in Database
        persisted_quote = db.query(Quotation).filter(Quotation.id == quote_record.id).first()
        print(f"Persisted Quote in DB: ID={persisted_quote.id}, Number='{persisted_quote.quotation_number}', Total=₹{persisted_quote.total}, Provenance={persisted_quote.data_provenance}")
        assert persisted_quote.data_provenance == "TEST_DATA"

        item_count = db.query(QuotationItem).filter(QuotationItem.quotation_id == persisted_quote.id).count()
        print(f"Persisted Quotation Items in DB (should be 4): {item_count}")
        assert item_count == 4

        print("\n==================================================")
        print("ALL END-TO-END INGESTION & PERSISTENCE TESTS PASSED!")
        print("==================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_tests()
