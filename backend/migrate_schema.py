"""Auto-Migration Script for PostgreSQL Database Schema.

Ensures all tables and missing columns exist in the active database.
"""
import sys
import os
from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import sync_engine, Base
# Import all models to ensure metadata is complete
import models.company
import models.person
import models.facility
import models.customer_asset
import models.lab_scope
import models.company_brain
import models.reasoning_engine
import models.decision_maker_candidate
import models.sales_os
import models.conversation
import models.campaign
import models.competitor_intel
import models.intent_signal
import models.web_research


def migrate_all():
    print("Running database migration...")
    if not sync_engine:
        print("Sync engine not available.")
        return

    # 1. Create any missing tables
    Base.metadata.create_all(bind=sync_engine)
    print("Base.metadata.create_all() executed.")

    # 2. Add specific missing columns to existing tables
    with sync_engine.connect() as conn:
        # persons table
        person_columns = [
            ("discovery_status", "VARCHAR(50) DEFAULT 'UNKNOWN'"),
            ("discovery_source", "VARCHAR(100)"),
            ("evidence_json", "JSONB"),
        ]
        for col_name, col_type in person_columns:
            try:
                conn.execute(text(f"ALTER TABLE persons ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                conn.commit()
                print(f"persons.{col_name} column ensured.")
            except Exception as e:
                print(f"persons.{col_name} column check note: {e}")

        # companies table
        company_columns = [
            ("domain", "VARCHAR(255)"),
            ("strategic_segment", "VARCHAR(100)"),
            ("total_asset_count", "INTEGER DEFAULT 0"),
        ]
        for col_name, col_type in company_columns:
            try:
                conn.execute(text(f"ALTER TABLE companies ADD COLUMN IF NOT EXISTS {col_name} {col_type};"))
                conn.commit()
                print(f"companies.{col_name} column ensured.")
            except Exception as e:
                print(f"companies.{col_name} column check note: {e}")

        # nabl_lab_scopes and quotations data_provenance
        provenance_tables = ["nabl_lab_scopes", "quotations"]
        for tbl in provenance_tables:
            try:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS data_provenance VARCHAR(50) DEFAULT 'PILOT_TEST_DATA';"))
                conn.execute(text(f"UPDATE {tbl} SET data_provenance = 'PILOT_TEST_DATA' WHERE data_provenance IS NULL;"))
                conn.commit()
                print(f"{tbl}.data_provenance column ensured.")
            except Exception as e:
                print(f"{tbl}.data_provenance check note: {e}")

    print("Migration completed successfully.")


if __name__ == "__main__":
    migrate_all()
