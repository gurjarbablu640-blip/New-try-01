"""Verification Test Suite for Historical Quotation Ingestion & Statistical Price Benchmarks."""
import unittest
from database import Base, SessionLocal, sync_engine
from models.company import Company
from models.sales_os import PriceHistory, Quotation
from services.historical_quote_importer import (
    parse_historical_quote_text,
    ingest_historical_quotation,
    get_historical_pricing_analytics,
)


class TestHistoricalQuotationImport(unittest.TestCase):
    def setUp(self):
        if SessionLocal is not None and sync_engine is not None:
            Base.metadata.create_all(sync_engine)
            self.db = SessionLocal()
        else:
            self.db = None

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.rollback()
            self.db.close()

    def test_parse_historical_quote_text(self):
        sample_text = """
        Quotation Ref: Q-2025-IND-884
        Date: 2025-05-20
        Customer: Mahindra Heavy Engines Ltd
        Location: Chakan, Pune
        
        1. Digital Vernier Caliper 0-300mm | Qty: 4 | Rate: INR 850
        2. External Micrometer 0-25mm | Qty: 6 | Rate: INR 650
        3. Pressure Transmitter 0-100 bar | Qty: 2 | Rate: INR 1800
        Total Value: INR 10,900
        """
        parsed = parse_historical_quote_text(sample_text, source_file="mahindra_quote.txt")

        self.assertEqual(parsed["quotation_number"], "Q-2025-IND-884")
        self.assertEqual(parsed["customer_name"], "Mahindra Heavy Engines Ltd")
        self.assertEqual(len(parsed["items"]), 3)
        self.assertEqual(parsed["items"][0]["instrument_name"], "Digital Vernier Caliper 0-300mm")
        self.assertEqual(parsed["items"][0]["quantity"], 4.0)
        self.assertEqual(parsed["items"][0]["unit_price"], 850.0)

    def test_ingest_historical_quotation_and_analytics(self):
        if not self.db:
            return

        parsed = {
            "quotation_number": "Q-HIST-TEST-001",
            "quotation_date": "2025-06-15",
            "customer_name": "Tata Motors Pune Plant Test",
            "location": "Pune, Maharashtra",
            "subtotal": 12000.0,
            "discount": 0.0,
            "tax": 2160.0,
            "total": 14160.0,
            "outcome": "Won",
            "source_file": "tata_historical.pdf",
            "items": [
                {
                    "instrument_name": "Digital Micrometer 0-25mm Test",
                    "parameter": "Dimensional",
                    "quantity": 10,
                    "unit_price": 700.0,
                    "total_price": 7000.0,
                },
                {
                    "instrument_name": "Digital Micrometer 0-25mm Test",
                    "parameter": "Dimensional",
                    "quantity": 5,
                    "unit_price": 750.0,
                    "total_price": 3750.0,
                },
            ],
        }

        quote = ingest_historical_quotation(self.db, parsed)
        self.assertIsNotNone(quote.id)
        self.assertEqual(quote.status, "Won")
        self.assertEqual(len(quote.items), 2)

        # Verify price history records were created with provenance
        hist_records = self.db.query(PriceHistory).filter(PriceHistory.quotation_id == quote.id).all()
        self.assertEqual(len(hist_records), 2)
        self.assertIn(float(hist_records[0].unit_price), [700.0, 750.0])

        # Verify statistical pricing benchmarks
        analytics = get_historical_pricing_analytics(self.db)
        self.assertGreaterEqual(analytics["total_quotations"], 1)
        self.assertGreaterEqual(analytics["total_line_items"], 2)
        self.assertGreaterEqual(len(analytics["instrument_benchmarks"]), 1)


if __name__ == "__main__":
    unittest.main()
