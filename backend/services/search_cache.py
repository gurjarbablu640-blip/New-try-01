"""Thread-safe persistent search cache for research providers."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "search_provider_cache.json")
)


class SearchCache:
    """Persistent JSON cache for web search queries to prevent burning API budget."""

    def __init__(self, cache_path: str = DEFAULT_CACHE_PATH) -> None:
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _make_key(self, provider: str, query: str, **params: Any) -> str:
        clean_q = " ".join((query or "").strip().lower().split())
        param_str = json.dumps(params, sort_keys=True) if params else ""
        return f"{provider.lower().strip()}::{clean_q}::{param_str}"

    def _load(self) -> None:
        if not os.path.exists(self.cache_path):
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._entries = data.get("entries", {}) or {}
        except Exception as e:
            logger.warning("Could not load search cache from %s: %s", self.cache_path, e)
            self._entries = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        tmp_path = f"{self.cache_path}.tmp"
        payload = {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(self._entries),
            "entries": self._entries,
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        for attempt in range(5):
            try:
                os.replace(tmp_path, self.cache_path)
                break
            except PermissionError:
                if attempt == 4:
                    logger.warning("Failed to atomically replace %s", self.cache_path)
                time.sleep(0.02)

    def get(self, provider: str, query: str, **params: Any) -> Optional[Dict[str, Any]]:
        key = self._make_key(provider, query, **params)
        with self._lock:
            entry = self._entries.get(key)
            if entry:
                cached_data = dict(entry.get("payload") or {})
                cached_data["retrieved_at"] = entry.get("retrieved_at")
                cached_data["cache_hit"] = True
                return cached_data
        return None

    def set(self, provider: str, query: str, payload: Dict[str, Any], **params: Any) -> None:
        key = self._make_key(provider, query, **params)
        with self._lock:
            self._entries[key] = {
                "provider": provider,
                "query": query,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "payload": payload,
            }
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._entries = {}
            self._save()


# Default singleton
search_cache = SearchCache()
