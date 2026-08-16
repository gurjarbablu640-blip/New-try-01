"""Automated verification suite for Step 3: Calibration Domain Intelligence, Facilities, Customer Assets, Due Dates, NABL Fit, NBA, and Company 360."""
import json
import os
import sqlite3
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import ARRAY
from sqlalchemy.dialects.postgresql import JSONB

# SQLite adapter for Python lists and PostgreSQL-specific types during tests
sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)

@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base
from models.company import Company
from models.facility import Facility
from models.customer_asset import CustomerAsset
from models.person import Person
from models.pipeline import PipelineStage
from services.calibration_intelligence import (
    calculate_asset_due_status,
    calculate_company_asset_calibration_summary,
    match_nabl_service_fit,
)
from services.buyingWindow import _determine_buying_window
from services.nextBestAction import get_next_best_action
from routes.company_360 import get_company_360, _company_summary
from routes.facilities import _serialize_facility
from routes.customer_assets import _serialize_asset


class TestStep3CalibrationDomainIntelligence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # ------------------------------------------------------------
    # 1. Deterministic Calibration Due Date Logic
    # ------------------------------------------------------------
    def test_due_date_calculation_bands(self):
        today = date.today()

        # Overdue (-15 days)
        overdue_date = today - timedelta(days=15)
        res_overdue = calculate_asset_due_status(overdue_date, reference_date=today)
        self.assertEqual(res_overdue["due_status"], "OVERDUE")
        self.assertEqual(res_overdue["urgency_level"], "CRITICAL")
        self.assertTrue(res_overdue["is_buying_window_active"])

        # Active 30 days (+20 days)
        active_30 = today + timedelta(days=20)
        res_30 = calculate_asset_due_status(active_30, reference_date=today)
        self.assertEqual(res_30["due_status"], "ACTIVE")
        self.assertEqual(res_30["urgency_level"], "HIGH")
        self.assertTrue(res_30["is_buying_window_active"])

        # Active 60 days (+45 days)
        active_60 = today + timedelta(days=45)
        res_60 = calculate_asset_due_status(active_60, reference_date=today)
        self.assertEqual(res_60["due_status"], "ACTIVE")
        self.assertEqual(res_60["urgency_level"], "MEDIUM")
        self.assertTrue(res_60["is_buying_window_active"])

        # Upcoming (+90 days)
        upcoming = today + timedelta(days=90)
        res_upcoming = calculate_asset_due_status(upcoming, reference_date=today)
        self.assertEqual(res_upcoming["due_status"], "UPCOMING")
        self.assertFalse(res_upcoming["is_buying_window_active"])

        # Future (+180 days)
        future = today + timedelta(days=180)
        res_future = calculate_asset_due_status(future, reference_date=today)
        self.assertEqual(res_future["due_status"], "FUTURE")
        self.assertFalse(res_future["is_buying_window_active"])

    # ------------------------------------------------------------
    # 2. NABL Scope & Service Fit Matching
    # ------------------------------------------------------------
    def test_nabl_scope_matching(self):
        # Pressure Gauge -> FULL_SCOPE
        fit_pressure = match_nabl_service_fit("Bourdon Tube Pressure Gauge", parameter="Pressure", range_value="0 to 40 bar")
        self.assertEqual(fit_pressure["fit_status"], "FULL_SCOPE")
        self.assertEqual(fit_pressure["discipline"], "Pressure & Vacuum")
        self.assertTrue(fit_pressure["nabl_accredited"])

        # Temperature Indicator / RTD -> FULL_SCOPE
        fit_temp = match_nabl_service_fit("Digital Temperature Indicator with PT100", parameter="Thermal", range_value="-50 to 400 °C")
        self.assertEqual(fit_temp["fit_status"], "FULL_SCOPE")
        self.assertEqual(fit_temp["discipline"], "Thermal")

        # Digital Multimeter -> FULL_SCOPE
        fit_dmm = match_nabl_service_fit("Fluke 87V Digital Multimeter", parameter="Voltage / Current / Resistance")
        self.assertEqual(fit_dmm["fit_status"], "FULL_SCOPE")
        self.assertEqual(fit_dmm["discipline"], "Electro-Technical")

        # Vernier Caliper -> FULL_SCOPE
        fit_caliper = match_nabl_service_fit("Mitutoyo Digital Vernier Caliper 0-300mm", parameter="Dimensional")
        self.assertEqual(fit_caliper["fit_status"], "FULL_SCOPE")
        self.assertEqual(fit_caliper["discipline"], "Mechanical & Dimensional")

        # Gas Chromatograph -> SUBCONTRACT_REQUIRED
        fit_gc = match_nabl_service_fit("Shimadzu GC-2030 Gas Chromatograph", parameter="Analytical")
        self.assertEqual(fit_gc["fit_status"], "SUBCONTRACT_REQUIRED")
        self.assertFalse(fit_gc["nabl_accredited"])

        # Office Equipment -> OUT_OF_SCOPE
        fit_office = match_nabl_service_fit("Office Printer Deskjet", parameter="General")
        self.assertEqual(fit_office["fit_status"], "OUT_OF_SCOPE")

    # ------------------------------------------------------------
    # 3. Facility Creation, CustomerAsset Linking & Hierarchy
    # ------------------------------------------------------------
    def test_facility_and_customer_asset_crud(self):
        company = Company(
            name="Bharat Heavy Electricals Ltd",
            domain="bhel.in",
            city="Trichy",
            state="Tamil Nadu",
            industry="Engineering",
        )
        self.db.add(company)
        self.db.flush()

        facility = Facility(
            company_id=company.id,
            name="High Pressure Boiler Plant",
            plant_code="HPBP-01",
            industrial_estate="Trichy Industrial Complex",
            city="Trichy",
            state="Tamil Nadu",
            address="Thiruverumbur, Tiruchirappalli",
        )
        self.db.add(facility)
        self.db.flush()

        asset = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            asset_tag="BHEL-TR-TI-101",
            serial_number="TC-88910",
            instrument_name="Thermocouple Calibration Furnace",
            make="Isotech",
            model="Pegasus 650",
            parameter="Thermal",
            range_value="150 to 650 °C",
            location_in_plant="Standards Lab",
            calibration_due_date=date.today() + timedelta(days=10),
            calibration_interval_months=12,
            status="Active",
        )
        self.db.add(asset)
        self.db.commit()

        # Check relationships
        self.assertEqual(len(company.facilities), 1)
        self.assertEqual(company.facilities[0].name, "High Pressure Boiler Plant")
        self.assertEqual(len(facility.assets), 1)
        self.assertEqual(facility.assets[0].instrument_name, "Thermocouple Calibration Furnace")
        self.assertEqual(len(company.customer_assets), 1)

        # Check serializers
        f_dict = _serialize_facility(facility, self.db)
        self.assertEqual(f_dict["name"], "High Pressure Boiler Plant")
        self.assertEqual(f_dict["asset_count"], 1)

        a_dict = _serialize_asset(asset)
        self.assertEqual(a_dict["due_status"], "ACTIVE")
        self.assertEqual(a_dict["urgency_level"], "HIGH")
        self.assertEqual(a_dict["nabl_fit"]["fit_status"], "FULL_SCOPE")

    # ------------------------------------------------------------
    # 4. Realistic Scenario: Aarti Industries Hierarchy, NBA & 360
    # ------------------------------------------------------------
    def test_realistic_company_facility_asset_hierarchy(self):
        today = date.today()

        # 1. Create Company (Aarti Industries)
        company = Company(
            name="Aarti Industries Ltd",
            domain="aarti-industries.com",
            city="Dahej",
            state="Gujarat",
            industry="Chemical",
            has_nabl=True,
            icp_score=80.0,
            calculated_tier="High-Value Recurring",
            lead_status="New",
        )
        self.db.add(company)
        self.db.flush()

        person = Person(
            company_id=company.id,
            full_name="Rajesh Patel",
            designation="Quality Head",
            email="rajesh.patel@aarti-industries.com",
            phone="9825014820",
            is_decision_maker=1,
        )
        self.db.add(person)
        self.db.flush()

        # 2. Create Facility (Dahej Plant)
        facility = Facility(
            company_id=company.id,
            name="Dahej Main Chemical Complex",
            plant_code="DHJ-PLANT-01",
            industrial_estate="GIDC Dahej Phase 2",
            city="Dahej",
            state="Gujarat",
            address="Plot No. 42-45, GIDC Industrial Estate, Dahej, Bharuch",
        )
        self.db.add(facility)
        self.db.flush()

        # 3. Create Customer Assets
        # Asset 1: Overdue Pressure Gauge
        asset1 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            asset_tag="AIL-DHJ-PG-001",
            serial_number="WIKA-89210",
            instrument_name="WIKA Pressure Gauge",
            make="WIKA",
            model="232.50",
            parameter="Pressure",
            range_value="0 to 25 bar",
            location_in_plant="Reactor Unit 3",
            last_calibrated_date=today - timedelta(days=380),
            calibration_due_date=today - timedelta(days=15),  # OVERDUE
            calibration_interval_months=12,
            certificate_number="CERT-2025-081",
            status="Active",
        )

        # Asset 2: Active 30-day Temperature Indicator
        asset2 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            asset_tag="AIL-DHJ-TI-002",
            serial_number="YOKO-44129",
            instrument_name="Yokogawa Digital Temperature Indicator",
            make="Yokogawa",
            model="UT35A",
            parameter="Thermal",
            range_value="-50 to 600 °C",
            location_in_plant="Distillation Column A",
            last_calibrated_date=today - timedelta(days=340),
            calibration_due_date=today + timedelta(days=25),  # ACTIVE 30-DAY
            calibration_interval_months=12,
            certificate_number="CERT-2025-092",
            status="Active",
        )

        # Asset 3: Upcoming 90-day Digital Multimeter
        asset3 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            asset_tag="AIL-DHJ-DMM-003",
            serial_number="FLK-99120",
            instrument_name="Fluke 179 True-RMS Multimeter",
            make="Fluke",
            model="179",
            parameter="Electro-Technical",
            range_value="0 to 1000V AC/DC",
            location_in_plant="Electrical Maintenance Lab",
            last_calibrated_date=today - timedelta(days=275),
            calibration_due_date=today + timedelta(days=90),  # UPCOMING
            calibration_interval_months=12,
            certificate_number="CERT-2025-115",
            status="Active",
        )

        self.db.add_all([asset1, asset2, asset3])
        self.db.commit()

        # 4. Verify Company Asset Calibration Summary
        summary = calculate_company_asset_calibration_summary(company.id, self.db, reference_date=today)
        self.assertEqual(summary["total_assets"], 3)
        self.assertEqual(summary["facilities_count"], 1)
        self.assertEqual(summary["due_metrics"]["overdue"], 1)
        self.assertEqual(summary["due_metrics"]["due_next_30_days"], 1)
        self.assertEqual(summary["due_metrics"]["due_next_60_days"], 1)
        self.assertEqual(summary["due_metrics"]["upcoming_90_to_120_days"], 1)
        self.assertEqual(summary["buying_window"], "next_30_days")
        self.assertTrue(summary["is_active_buying_window"])
        self.assertEqual(summary["nabl_fit_summary"]["full_scope_count"], 3)
        self.assertEqual(summary["nabl_fit_summary"]["full_scope_ratio"], 1.0)

        # 5. Verify Buying Window Engine Integration
        window_result = _determine_buying_window(company, self.db)
        self.assertEqual(window_result, "next_30_days")

        # 6. Verify Next Best Action Triggered by Calibration Urgency
        pipeline = PipelineStage(
            company_id=company.id,
            stage="New",
        )
        self.db.add(pipeline)
        self.db.commit()

        nba = get_next_best_action(company.id, self.db)
        self.assertEqual(nba["action"], "MAKE_CALL")  # Rajesh has phone -> High urgency Call
        self.assertEqual(nba["timing"], "today")
        self.assertIn("calibration", nba["reason"].lower())


if __name__ == "__main__":
    unittest.main()
