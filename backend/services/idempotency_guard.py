"""Idempotency Guard — Prevents duplicate processing after restarts.

Provides deterministic idempotency keys for:
- Company discovery tasks
- Evidence records
- Staging records
- Follow-up scheduling

INVARIANTS:
1. Same company + same trigger + same day → same idempotency key.
2. Replay after restart must NOT create duplicate records.
3. Idempotency keys are deterministic (not UUID-based).
4. Guard state persists across restarts via JSON file.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

IDEMPOTENCY_STATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "runtime_state"
)
IDEMPOTENCY_STATE_FILE = os.path.join(IDEMPOTENCY_STATE_DIR, "idempotency_state.json")


def make_idempotency_key(
    *,
    operation: str,
    company: str,
    facility: str = "",
    person: str = "",
    trigger: str = "",
    date_str: str = "",
) -> str:
    """Generate a deterministic idempotency key.

    Same inputs on the same day always produce the same key.
    """
    if not date_str:
        date_str = date.today().isoformat()

    raw = f"{operation}|{company.strip().lower()}|{facility.strip().lower()}|{person.strip().lower()}|{trigger.strip().lower()[:100]}|{date_str}"
    return f"idem-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]}"


class IdempotencyGuard:
    """Tracks processed operations to prevent duplicates after restart."""

    def __init__(self, state_file: str = IDEMPOTENCY_STATE_FILE):
        self.state_file = state_file
        self._processed: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load persisted state from disk."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._processed = data.get("processed", {})
            except Exception as exc:
                logger.warning("Failed to load idempotency state: %s", exc)
                self._processed = {}

    def _save(self) -> None:
        """Persist state to disk atomically."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        temp = f"{self.state_file}.tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump({
                "processed": self._processed,
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)
        os.replace(temp, self.state_file)

    def check_and_mark(
        self,
        key: str,
        operation: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if operation was already processed. Returns True if DUPLICATE.

        If not a duplicate, marks the key as processed and returns False.
        """
        if key in self._processed:
            logger.info("Idempotency DUPLICATE detected: %s (operation: %s)", key, operation)
            return True

        self._processed[key] = {
            "operation": operation,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        self._save()
        return False

    def is_processed(self, key: str) -> bool:
        """Check if a key was already processed (read-only)."""
        return key in self._processed

    def get_processed_count(self) -> int:
        """Return the number of processed operations."""
        return len(self._processed)

    def clear_expired(self, max_age_days: int = 7) -> int:
        """Clear entries older than max_age_days. Returns count removed."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        expired = [
            k for k, v in self._processed.items()
            if v.get("processed_at", "") < cutoff
        ]
        for k in expired:
            del self._processed[k]
        if expired:
            self._save()
        return len(expired)

    def reset_for_testing(self) -> None:
        """Clear all state — ONLY for testing."""
        self._processed = {}
        if os.path.exists(self.state_file):
            os.remove(self.state_file)


# Global instance
idempotency_guard = IdempotencyGuard()
