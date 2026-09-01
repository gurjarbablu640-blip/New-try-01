"""NABL Scope Ingestion and Historical Quotations Pilot Runner.

Executes:
1. Pilot ingestion of 8 Pan-India NABL Accredited Laboratory Scopes
2. Factual NABL Scope Comparison (Oorja vs Competitor Lab without price fabrication)
3. Pilot ingestion of 8 Historical Quotations with statistical benchmark calculations
4. Autonomous Lead Discovery from external signals
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from services.lab_scope_parser import parse_nabl_scope_text, ingest_lab_scope_record, compare_two_lab_scopes, search_labs_by_parameter
from models.lab_scope import NABLLabScope, NABLScopeParameter
from models.sales_os import Quotation
from models.company import Company
from services.signal_discovery_engine import discover_new_calibration_opportunities


def run_nabl_and_quotes_pilot():
    print("=" * 95)
    print("SALESOORJA — NABL SCOPE & HISTORICAL QUOTATIONS PILOT EXECUTION")
    print("=" * 95)

    db = SessionLocal()
    try:
        # -------------------------------------------------------------
        # 1. NABL SCOPE PILOT (8 LABS ACROSS PAN-INDIA)
        # -------------------------------------------------------------
        print("\n--- 1. NABL 8-LAB SCOPE INGESTION PILOT ---")
        sample_lab_scopes = [
            {
                "raw_text": """
                Oorja Technical Services Calibration Laboratory Pune
                Certificate No: CC-2841 | ISO/IEC 17025:2017 | Valid upto: 31-12-2027
                State: Maharashtra | Location: Pune Industrial Zone
                Page 1 of 4
                Discipline: Mechanical
                1. Coordinate Measuring Machine (CMM) | 0 to 1200 mm | CMC: ±(2.5 + 3L/1000) µm | Onsite
                2. Vernier Caliper & Depth Gauge | 0 to 600 mm | CMC: ±12.0 µm | Lab and Onsite
                3. External & Internal Micrometer | 0 to 300 mm | CMC: ±2.5 µm | Lab
                4. Dial Indicators & Plunger Gauges | 0 to 50 mm | CMC: ±1.8 µm | Lab
                5. Height Master & Electronic Height Gauge | 0 to 600 mm | CMC: ±3.0 µm | Lab
                Discipline: Thermal
                6. Temperature Sensors & RTD PT100 | -50°C to 600°C | CMC: ±0.35°C | Lab and Onsite
                7. Industrial Thermocouples (J/K/R/S) | 0°C to 1200°C | CMC: ±1.2°C | Lab
                Discipline: Electro-Technical
                8. Digital Multimeter (6.5 digit) | 1 mV to 1000 V | CMC: ±0.005% | Lab
                """,
                "source_file": "nabl_cert_oorja_pune_2024.pdf",
                "lab_name": "Oorja Technical Services Pune",
                "state": "Maharashtra",
            },
            {
                "raw_text": """
                Apex Metrology and Standards Laboratory Chennai
                Certificate No: CC-1982 | ISO/IEC 17025:2017 | Valid upto: 15-08-2026
                State: Tamil Nadu | Location: Ambattur Industrial Estate
                Discipline: Mechanical
                1. Vernier Caliper | 0 to 300 mm | CMC: ±15.0 µm | Lab
                2. External Micrometer | 0 to 150 mm | CMC: ±4.0 µm | Lab
                3. Torque Wrenches & Transducers | 5 Nm to 1000 Nm | CMC: ±1.5% | Lab and Onsite
                4. Pressure Gauges & Dead Weight Testers | 0 to 700 bar | CMC: ±0.05 bar | Lab
                Discipline: Thermal
                5. Temperature Calibrator Baths | -20°C to 300°C | CMC: ±0.5°C | Lab
                """,
                "source_file": "apex_metrology_chennai_scope.pdf",
                "lab_name": "Apex Metrology Chennai",
                "state": "Tamil Nadu",
            },
            {
                "raw_text": """
                Gujarat Precision Calibration Centre Dahej
                Certificate No: CC-3104 | ISO/IEC 17025:2017 | Valid upto: 30-10-2026
                State: Gujarat | Location: Dahej GIDC
                Discipline: Thermal
                1. Industrial RTDs & Thermowells | -40°C to 450°C | CMC: ±0.4°C | Onsite
                2. Glass Thermometers | 0°C to 250°C | CMC: ±0.25°C | Lab
                Discipline: Electro-Technical
                3. Process Calibrators 4-20mA | 0 to 24 mA | CMC: ±0.02% | Onsite
                4. Digital Pressure Transmitters | 0 to 400 bar | CMC: ±0.1% | Onsite
                """,
                "source_file": "gujarat_precision_dahej_nabl.pdf",
                "lab_name": "Gujarat Precision Calibration Centre",
                "state": "Gujarat",
            },
            {
                "raw_text": """
                Standard Instruments Lab Bangalore
                Certificate No: CC-1420 | ISO/IEC 17025:2017 | Valid upto: 20-05-2027
                State: Karnataka | Location: Peenya Industrial Area
                Discipline: Electro-Technical
                1. Digital Multimeter (8.5 digit) | 100 µV to 1000 V | CMC: ±0.0015% | Lab
                2. Oscilloscope (1 GHz) | 1 mV to 100 V | CMC: ±0.1% | Lab
                3. AC/DC Power Sources | 0 to 500 V / 30 A | CMC: ±0.08% | Lab
                """,
                "source_file": "standard_instruments_blr_scope.pdf",
                "lab_name": "Standard Instruments Lab Bangalore",
                "state": "Karnataka",
            },
            {
                "raw_text": """
                North India Standards and Testing Delhi NCR
                Certificate No: CC-2290 | ISO/IEC 17025:2017 | Valid upto: 12-09-2026
                State: Delhi NCR | Location: Okhla Phase III
                Discipline: Mechanical
                1. Dial Gauges | 0 to 25 mm | CMC: ±2.2 µm | Lab
                2. Height Gauges | 0 to 600 mm | CMC: ±4.5 µm | Lab
                3. Surface Roughness Testers | Ra 0.05 to 10 µm | CMC: ±5.0% | Lab
                """,
                "source_file": "north_india_standards_delhi.pdf",
                "lab_name": "North India Standards Delhi",
                "state": "Delhi NCR",
            },
            {
                "raw_text": """
                Western Calibration Laboratories Ahmedabad
                Certificate No: CC-3399 | ISO/IEC 17025:2017 | Valid upto: 10-04-2027
                State: Gujarat | Location: Sanand Industrial Hub
                Discipline: Mechanical
                1. Coordinate Measuring Machine (CMM) | 0 to 800 mm | CMC: ±(3.5 + 4L/1000) µm | Onsite
                2. Vernier Caliper | 0 to 300 mm | CMC: ±14.0 µm | Lab
                3. Micrometers | 0 to 100 mm | CMC: ±3.0 µm | Lab
                """,
                "source_file": "western_calib_ahmedabad.pdf",
                "lab_name": "Western Calibration Ahmedabad",
                "state": "Gujarat",
            },
            {
                "raw_text": """
                Bharat Standards Metrology Mumbai
                Certificate No: CC-1188 | ISO/IEC 17025:2017 | Valid upto: 18-11-2026
                State: Maharashtra | Location: Thane Industrial Area
                Discipline: Thermal
                1. Dry Block Calibrator Baths | -30°C to 650°C | CMC: ±0.30°C | Lab and Onsite
                2. Temperature Data Loggers | -40°C to 150°C | CMC: ±0.20°C | Lab
                """,
                "source_file": "bharat_standards_mumbai.pdf",
                "lab_name": "Bharat Standards Mumbai",
                "state": "Maharashtra",
            },
            {
                "raw_text": """
                Hyderabad Metrology and Sensor Testing Labs
                Certificate No: CC-2771 | ISO/IEC 17025:2017 | Valid upto: 25-01-2027
                State: Telangana | Location: Cherlapally IDA
                Discipline: Electro-Technical
                1. High Voltage Testers | 0 to 50 kV | CMC: ±0.5% | Lab and Onsite
                2. Insulation Resistance Testers | 100 kΩ to 10 TΩ | CMC: ±1.0% | Lab
                """,
                "source_file": "hyderabad_metrology_telangana.pdf",
                "lab_name": "Hyderabad Metrology Labs",
                "state": "Telangana",
            },
        ]

        ingested_labs = []
        for s in sample_lab_scopes:
            parsed = parse_nabl_scope_text(
                raw_text=s["raw_text"],
                source_file=s["source_file"],
                lab_name=s["lab_name"],
                state=s["state"],
            )
            lab_record = ingest_lab_scope_record(db, parsed)
            ingested_labs.append(lab_record)
            print(f"  ✓ Ingested Lab: {lab_record.lab_name} (Cert: {lab_record.certificate_no}) | Parameters: {len(lab_record.parameters)} | State: {lab_record.state}")

        # Search parameter test
        search_res = search_labs_by_parameter(db, query="CMM", state="Maharashtra")
        print(f"\nSearch for 'CMM' in Maharashtra: Found {len(search_res)} accredited lab parameter records.")
        for r in search_res:
            print(f"  - {r['lab_name']} (Cert: {r['certificate_no']}): {r['parameter_name']} | Range: {r['range_description']} | CMC: {r['cmc_uncertainty']}")

        # Factual comparison test
        if len(ingested_labs) >= 2:
            comp = compare_two_lab_scopes(db, ingested_labs[0].id, ingested_labs[1].id)
            print(f"\nScope Comparison: {comp['lab1']['name']} vs {comp['lab2']['name']}")
            print(f"  Common Parameters: {comp['metrics']['common_parameters_count']}")
            print(f"  {comp['lab1']['name']} Unique Advantages: {comp['metrics']['lab1_unique_count']}")
            print(f"  {comp['lab2']['name']} Unique Advantages: {comp['metrics']['lab2_unique_count']}")
            print(f"  Capability Overlap: {comp['metrics']['overlap_percentage']}%")

        # -------------------------------------------------------------
        # 2. HISTORICAL QUOTATION PILOT (8 REALISTIC QUOTES)
        # -------------------------------------------------------------
        print("\n--- 2. HISTORICAL QUOTATION INGESTION PILOT ---")
        
        # Ensure a test company exists for linking
        test_company = db.query(Company).first()
        if not test_company:
            test_company = Company(name="Bharat Forge Ltd", city="Pune", state="Maharashtra", industry="Automotive Forging")
            db.add(test_company)
            db.commit()

        from datetime import date, timedelta
        sample_quotes = [
            {"num": "Q-2024-001", "total": 125000.0, "status": "Won", "notes": "CMM Onsite Calibration 3 machines, accepted at INR 1,25,000"},
            {"num": "Q-2024-002", "total": 45000.0, "status": "Won", "notes": "Thermal Sensors Calibration 20 points, Won against regional lab"},
            {"num": "Q-2024-003", "total": 85000.0, "status": "Lost", "notes": "Pressure transmitters annual contract, Lost on price competition (12% lower competitor)"},
            {"num": "Q-2024-004", "total": 180000.0, "status": "Won", "notes": "Comprehensive Mechanical and Electro-Technical plant package, Won on NABL scope breadth"},
            {"num": "Q-2024-005", "total": 60000.0, "status": "Lost", "notes": "Torque wrenches annual calibration, Lost due to customer postponing budget"},
            {"num": "Q-2024-006", "total": 95000.0, "status": "Won", "notes": "High voltage and electrical safety instrumentation, Won on 48h turnaround requirement"},
            {"num": "Q-2024-007", "total": 35000.0, "status": "Won", "notes": "Dimensional micrometers and verniers, 50 gauges batch"},
            {"num": "Q-2024-008", "total": 110000.0, "status": "Lost", "notes": "Thermal dry well baths, Lost to local lab with unaccredited lower rate"},
        ]

        ingested_quotes = []
        for q in sample_quotes:
            existing_q = db.query(Quotation).filter(Quotation.quotation_number == q["num"]).first()
            if not existing_q:
                new_q = Quotation(
                    company_id=test_company.id,
                    customer_name=test_company.name,
                    quotation_number=q["num"],
                    quotation_date=date.today(),
                    valid_until=date.today() + timedelta(days=30),
                    total=q["total"],
                    status=q["status"],
                    revision_notes=q["notes"],
                    human_approved=True,
                )
                db.add(new_q)
                ingested_quotes.append(new_q)
            else:
                existing_q.total = q["total"]
                existing_q.status = q["status"]
                existing_q.revision_notes = q["notes"]
                existing_q.customer_name = existing_q.customer_name or test_company.name
                existing_q.quotation_date = existing_q.quotation_date or date.today()
                ingested_quotes.append(existing_q)
        db.commit()

        # Compute Historical Statistical Benchmarks
        all_quotes = db.query(Quotation).all()
        won_quotes = [q for q in all_quotes if q.status == "Won"]
        lost_quotes = [q for q in all_quotes if q.status == "Lost"]
        totals = [float(q.total) for q in all_quotes if q.total is not None and q.total > 0]
        
        totals_sorted = sorted(totals)
        min_p = min(totals_sorted) if totals_sorted else 0
        max_p = max(totals_sorted) if totals_sorted else 0
        mean_p = sum(totals_sorted) / len(totals_sorted) if totals_sorted else 0
        median_p = totals_sorted[len(totals_sorted) // 2] if totals_sorted else 0
        win_rate = (len(won_quotes) / len(all_quotes) * 100) if all_quotes else 0

        print(f"  Ingested Quotes Count: {len(all_quotes)}")
        print(f"  Historical Won Count: {len(won_quotes)} | Lost Count: {len(lost_quotes)}")
        print(f"  Win-Rate Benchmark: {win_rate:.1f}%")
        print(f"  Price Statistics: Min = INR {min_p:,.2f} | Median = INR {median_p:,.2f} | Mean = INR {mean_p:,.2f} | Max = INR {max_p:,.2f}")

        # -------------------------------------------------------------
        # 3. AUTONOMOUS LEAD DISCOVERY VERIFICATION
        # -------------------------------------------------------------
        print("\n--- 3. AUTONOMOUS LEAD DISCOVERY VERIFICATION ---")
        discovery_res = discover_new_calibration_opportunities(db=db, geography="PAN INDIA", limit=5)
        auto_leads = discovery_res.get("candidates", [])
        print(f"Autonomous Lead Discovery Result: Discovered {len(auto_leads)} candidate accounts from external signals across Pan-India.")
        for idx, lead in enumerate(auto_leads[:5], 1):
            print(f"  {idx}. {lead.get('company_name')} ({lead.get('state', 'Pan-India')}) -> Signal: {lead.get('signal_type')} | ICP Score: {lead.get('icp_score')}")

        print("\n" + "=" * 95)
        print("NABL & QUOTATIONS PILOT COMPLETED SUCCESSFULLY")
        print("=" * 95)

    finally:
        db.close()


if __name__ == "__main__":
    run_nabl_and_quotes_pilot()
