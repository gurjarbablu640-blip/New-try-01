"""Direct DDL verification of upgrade() and downgrade() for 20260901_add_conversation_memory."""
import os
import sys
import unittest
import importlib
from types import SimpleNamespace

from sqlalchemy import create_engine, text, inspect
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

class MockOp:
    """Mock alembic.op executing real DDL on a connection."""
    def __init__(self, connection):
        self.conn = connection
        self.metadata = sa.MetaData()

    def create_table(self, table_name, *columns, **kwargs):
        cols = []
        for col in columns:
            if isinstance(col, sa.Column):
                # Swap JSONB for TEXT if SQLite
                if isinstance(col.type, JSONB):
                    col = sa.Column(col.name, sa.Text(), *col.foreign_keys, primary_key=col.primary_key, nullable=col.nullable)
                cols.append(col)
        table = sa.Table(table_name, self.metadata, *cols)
        table.create(self.conn)

    def create_index(self, index_name, table_name, columns, **kwargs):
        cols_str = ", ".join(columns)
        self.conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({cols_str})"))

    def drop_index(self, index_name, table_name=None, **kwargs):
        self.conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))

    def drop_table(self, table_name, **kwargs):
        self.conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
        if table_name in self.metadata.tables:
            self.metadata.remove(self.metadata.tables[table_name])


import types

class TestMigrationDDL(unittest.TestCase):
    def test_upgrade_and_downgrade_ddl(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.connect() as conn:
            mock_op = MockOp(conn)
            alembic_mod = types.ModuleType("alembic")
            alembic_mod.op = mock_op
            sys.modules["alembic"] = alembic_mod
            
            import importlib.util
            migration_path = os.path.join(backend_dir, "alembic", "versions", "20260901_add_conversation_memory.py")
            spec = importlib.util.spec_from_file_location("conv_migration", migration_path)
            conv_migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(conv_migration)
            conv_migration.op = mock_op
            
            # 1. Test Upgrade
            conv_migration.upgrade()
            inspector = inspect(conn)
            tables = inspector.get_table_names()
            self.assertIn("conversation_sessions", tables)
            self.assertIn("conversation_turns", tables)

            # 2. Test Downgrade (drops conversation_turns first, then conversation_sessions)
            conv_migration.downgrade()
            inspector = inspect(conn)
            tables_after = inspector.get_table_names()
            self.assertNotIn("conversation_turns", tables_after)
            self.assertNotIn("conversation_sessions", tables_after)

            # 3. Test Upgrade again (re-creation clean)
            conv_migration.upgrade()
            inspector = inspect(conn)
            tables_recreated = inspector.get_table_names()
            self.assertIn("conversation_sessions", tables_recreated)
            self.assertIn("conversation_turns", tables_recreated)
            print("DDL upgrade -> downgrade -> upgrade executed cleanly with 0 errors!")


if __name__ == "__main__":
    unittest.main()
