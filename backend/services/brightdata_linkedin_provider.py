"""Bright Data evidence provider for LinkedIn people and profile records."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse, urlunparse

import requests

from config import settings


logger = logging.getLogger(__name__)

PROVIDER_NAME = "BRIGHTDATA_LINKEDIN"
MAX_CANDIDATES = 5
PRIORITY_ROLE_FAMILIES = [
    "Plant Head",
    "Factory Head",
    "Unit Head",
    "Plant Quality Head",
    "Head Quality",
    "QA Head",
    "QC Head",
    "Metrology Head",
    "Calibration Head",
    "GM Quality",
    "AGM Quality",
    "Manufacturing Head",
    "Operations Head",
    "Maintenance Head",
    "Instrumentation Head",
    "Senior Quality Manager",
    "Quality Manager",
]
DEFAULT_CACHE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "runtime_state"
    / "brightdata_linkedin_cache.json"
)
_CACHE_LOCK = threading.Lock()


class BrightDataProviderError(RuntimeError):
    """Sanitized provider failure that never contains credentials or response bodies."""

    def __init__(self, code: str, stage: str, http_status: Optional[int] = None):
        self.code = code
        self.stage = stage
        self.http_status = http_status
        super().__init__(f"{code} during {stage}")

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "stage": self.stage}
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        return payload


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _company_name(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_text(
            value.get("name")
            or value.get("company_name")
            or value.get("title")
        )
    return _clean_text(value)


def _canonical_linkedin_url(value: Any) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = parsed.netloc.lower().split(":", 1)[0]
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        return ""
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    return urlunparse(("https", "www.linkedin.com", path, "", "", ""))


def _date_text(value: Any) -> str:
    if isinstance(value, dict):
        parts = [value.get("month"), value.get("year")]
        return " ".join(_clean_text(part) for part in parts if part)
    return _clean_text(value)


def _normalize_experience(
    value: Any,
    current_company: str,
) -> List[Dict[str, Any]]:
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: List[Dict[str, Any]] = []
    current_company_key = current_company.casefold()
    for item in items:
        if isinstance(item, str):
            text = _clean_text(item)
            if text:
                normalized.append({
                    "title": text,
                    "company": "",
                    "location": "",
                    "start_date": "",
                    "end_date": "",
                    "is_current": bool(re.search(r"\b(present|current|currently)\b", text, re.I)),
                })
            continue
        if not isinstance(item, dict):
            continue
        company = _company_name(
            item.get("company")
            or item.get("company_name")
            or item.get("organization")
        )
        title = _clean_text(item.get("title") or item.get("position") or item.get("role"))
        location = _clean_text(item.get("location") or item.get("city"))
        start_date = _date_text(item.get("start_date") or item.get("start"))
        end_date = _date_text(item.get("end_date") or item.get("end"))
        explicit_current = item.get("is_current")
        if explicit_current is None:
            explicit_current = item.get("current")
        if explicit_current is None:
            explicit_current = item.get("currently_working")
        is_current = bool(explicit_current) or bool(
            re.search(r"\b(present|current|currently)\b", end_date, re.I)
        )
        if (
            not is_current
            and not end_date
            and current_company_key
            and company.casefold() == current_company_key
        ):
            is_current = True
        if any((company, title, location, start_date, end_date)):
            normalized.append({
                "title": title,
                "company": company,
                "location": location,
                "start_date": start_date,
                "end_date": end_date,
                "is_current": is_current,
            })
    return normalized


def normalize_linkedin_record(
    record: Dict[str, Any],
    *,
    evidence_kind: str,
    retrieved_at: str,
) -> Dict[str, Any]:
    """Normalize a Bright Data record without assigning Salesoorja truth labels."""
    linkedin_url = _canonical_linkedin_url(
        record.get("url")
        or record.get("linkedin_url")
        or record.get("profile_url")
    )
    current_company = _company_name(
        record.get("current_company")
        or record.get("current_company_name")
        or record.get("company")
        or record.get("company_name")
    )
    current_title = _clean_text(
        record.get("position")
        or record.get("current_title")
        or record.get("job_title")
    )
    headline = _clean_text(record.get("subtitle") or record.get("headline") or current_title)
    location = _clean_text(record.get("location") or record.get("city"))
    experience = _normalize_experience(record.get("experience"), current_company)
    if not current_title:
        current_title = next(
            (item["title"] for item in experience if item.get("is_current") and item.get("title")),
            "",
        )
    if not current_company:
        current_company = next(
            (item["company"] for item in experience if item.get("is_current") and item.get("company")),
            "",
        )
    provenance = {
        field: {
            "provider": PROVIDER_NAME,
            "evidence_kind": evidence_kind,
            "source_field": source_field,
            "source_url": linkedin_url,
        }
        for field, source_field in {
            "name": "name",
            "linkedin_url": "url",
            "linkedin_id": "id",
            "headline": "subtitle|headline|position",
            "location": "location|city",
            "current_company": "current_company|current_company_name|company",
            "current_title": "position|current_title|experience.title",
            "experience": "experience",
        }.items()
    }
    return {
        "name": _clean_text(record.get("name") or record.get("full_name")),
        "linkedin_url": linkedin_url,
        "linkedin_id": _clean_text(record.get("id") or record.get("linkedin_id")),
        "headline": headline,
        "location": location,
        "current_company": current_company,
        "current_title": current_title,
        "experience": experience,
        "source": PROVIDER_NAME,
        "evidence_kind": evidence_kind,
        "retrieved_at": retrieved_at,
        "field_provenance": provenance,
    }


def _company_tokens(company: str) -> List[str]:
    ignored = {"limited", "ltd", "private", "pvt", "inc", "corporation", "corp"}
    return [
        token
        for token in re.findall(r"[a-z0-9]+", company.casefold())
        if len(token) >= 3 and token not in ignored
    ]


def _company_matches(candidate_company: str, target_company: str) -> bool:
    candidate = candidate_company.casefold()
    tokens = _company_tokens(target_company)
    return bool(candidate and tokens and all(token in candidate for token in tokens[:2]))


def rank_people_records(
    records: Iterable[Dict[str, Any]],
    *,
    company: str,
    facility: str = "",
    city: str = "",
    role_families: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Rank provider records locally without assigning qualification status."""
    priorities = role_families or PRIORITY_ROLE_FAMILIES
    facility_terms = [
        token for token in re.findall(r"[a-z0-9]+", facility.casefold())
        if len(token) >= 3 and token not in {"plant", "unit", "facility", "factory"}
    ]
    ranked: List[Dict[str, Any]] = []
    for record in records:
        item = dict(record)
        title = _clean_text(item.get("current_title") or item.get("headline")).casefold()
        experience_text = " ".join(
            " ".join(_clean_text(exp.get(key)) for key in ("title", "company", "location"))
            for exp in item.get("experience", [])
            if isinstance(exp, dict)
        ).casefold()
        score = 0
        if _company_matches(_clean_text(item.get("current_company")), company):
            score += 100
        for index, role in enumerate(priorities):
            role_key = role.casefold()
            if role_key in title:
                score += max(70 - index * 2, 35)
                break
        else:
            role_terms = {
                "quality", "qa", "qc", "metrology", "calibration", "plant",
                "factory", "operations", "manufacturing", "maintenance", "instrumentation",
            }
            score += 25 if any(term in title for term in role_terms) else 0
        if facility_terms and any(term in experience_text for term in facility_terms):
            score += 35
        if city and city.casefold() in experience_text:
            score += 20
        elif city and city.casefold() in _clean_text(item.get("location")).casefold():
            score += 5
        if any(
            exp.get("is_current") and _company_matches(_clean_text(exp.get("company")), company)
            for exp in item.get("experience", [])
            if isinstance(exp, dict)
        ):
            score += 25
        if item.get("linkedin_url"):
            score += 5
        item["discovery_rank_score"] = score
        ranked.append(item)
    ranked.sort(key=lambda item: (-int(item.get("discovery_rank_score") or 0), item.get("name", "").casefold()))
    return ranked


class BrightDataLinkedInProvider:
    """Cache-first client for Bright Data Dataset Search and Profile Scraper APIs."""

    def __init__(
        self,
        *,
        settings_obj: Any = settings,
        session: Optional[requests.Session] = None,
        cache_path: Optional[Path] = None,
        clock: Any = time.time,
        monotonic: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self._api_token = _clean_text(getattr(settings_obj, "BRIGHTDATA_API_TOKEN", ""))
        self.people_dataset_id = _clean_text(
            getattr(settings_obj, "BRIGHTDATA_LINKEDIN_PEOPLE_SEARCH_DATASET_ID", "")
        )
        self.profile_dataset_id = _clean_text(
            getattr(settings_obj, "BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID", "")
        )
        self.base_url = _clean_text(
            getattr(settings_obj, "BRIGHTDATA_API_BASE_URL", "https://api.brightdata.com")
        ).rstrip("/")
        self.timeout_seconds = max(1, int(getattr(settings_obj, "BRIGHTDATA_TIMEOUT_SECONDS", 60)))
        self.poll_timeout_seconds = max(
            1, int(getattr(settings_obj, "BRIGHTDATA_POLL_TIMEOUT_SECONDS", 75))
        )
        self.cache_ttl_seconds = max(
            0, int(getattr(settings_obj, "BRIGHTDATA_CACHE_TTL_SECONDS", 2592000))
        )
        self.cache_path = Path(cache_path or DEFAULT_CACHE_PATH)
        self._session = session or requests.Session()
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._telemetry = {
            "BRIGHTDATA_REQUESTS": 0,
            "BRIGHTDATA_RECORDS": 0,
            "BRIGHTDATA_CACHE_HITS": 0,
            "BRIGHTDATA_PROFILE_FETCHES": 0,
        }

    def __repr__(self) -> str:
        return "BrightDataLinkedInProvider(provider='BRIGHTDATA_LINKEDIN')"

    def telemetry(self) -> Dict[str, int]:
        return dict(self._telemetry)

    def configuration_status(self) -> Dict[str, Any]:
        missing = []
        if not self._api_token:
            missing.append("BRIGHTDATA_API_TOKEN")
        if not self.people_dataset_id:
            missing.append("BRIGHTDATA_LINKEDIN_PEOPLE_SEARCH_DATASET_ID")
        if not self.profile_dataset_id:
            missing.append("BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID")
        return {
            "status": "READY" if not missing else "CONFIG_REQUIRED",
            "provider": PROVIDER_NAME,
            "missing": missing,
        }

    def search_people(
        self,
        *,
        company: str,
        facility: str = "",
        city: str = "",
        state: str = "",
        role_families: Optional[List[str]] = None,
        max_candidates: int = MAX_CANDIDATES,
    ) -> Dict[str, Any]:
        """Search a LinkedIn people dataset once and retain at most five candidates."""
        config = self.configuration_status()
        if config["status"] != "READY":
            return {**config, "records": [], "telemetry": self.telemetry()}
        roles = list(role_families or PRIORITY_ROLE_FAMILIES)
        retained_limit = min(max(1, int(max_candidates)), MAX_CANDIDATES)
        cache_key = self._cache_key("search", {
            "company": company,
            "facility": facility,
            "city": city,
            "state": state,
            "roles": roles,
            "limit": retained_limit,
        })
        cached = self._cache_get(cache_key)
        if cached is not None:
            return {
                "status": "WORKING",
                "provider": PROVIDER_NAME,
                "records": cached,
                "cache_hit": True,
                "telemetry": self.telemetry(),
            }
        filter_object = {
            "name": "current_company_name",
            "operator": "includes",
            "value": company,
        }
        try:
            payload = self._request_json(
                "POST",
                f"/datasets/search/{self.people_dataset_id}",
                stage="people_search",
                json_body={"size": max(retained_limit * 2, 10), "filter": filter_object},
            )
            raw_records = self._extract_records(payload)
            self._telemetry["BRIGHTDATA_RECORDS"] += len(raw_records)
            retrieved_at = self._retrieved_at()
            normalized = [
                normalize_linkedin_record(record, evidence_kind="PEOPLE_SEARCH", retrieved_at=retrieved_at)
                for record in raw_records
                if isinstance(record, dict)
            ]
            ranked = rank_people_records(
                normalized,
                company=company,
                facility=facility,
                city=city,
                role_families=roles,
            )[:retained_limit]
            self._cache_set(cache_key, ranked)
            return {
                "status": "WORKING" if ranked else "EMPTY",
                "provider": PROVIDER_NAME,
                "records": ranked,
                "cache_hit": False,
                "telemetry": self.telemetry(),
            }
        except BrightDataProviderError as error:
            logger.warning("Bright Data people search failed: %s at %s", error.code, error.stage)
            return {
                "status": error.code,
                "provider": PROVIDER_NAME,
                "records": [],
                "error": error.to_dict(),
                "telemetry": self.telemetry(),
            }

    def get_person_profile(self, linkedin_url: str) -> Dict[str, Any]:
        """Fetch one public LinkedIn profile record when search evidence is insufficient."""
        config = self.configuration_status()
        if config["status"] != "READY":
            return {**config, "record": None, "telemetry": self.telemetry()}
        canonical_url = _canonical_linkedin_url(linkedin_url)
        if not canonical_url or "/in/" not in urlparse(canonical_url).path.casefold():
            return {
                "status": "INVALID_PROFILE_URL",
                "provider": PROVIDER_NAME,
                "record": None,
                "telemetry": self.telemetry(),
            }
        cache_key = self._cache_key("profile", {"linkedin_url": canonical_url})
        cached = self._cache_get(cache_key)
        if cached is not None:
            return {
                "status": "WORKING",
                "provider": PROVIDER_NAME,
                "record": cached,
                "cache_hit": True,
                "telemetry": self.telemetry(),
            }
        try:
            self._telemetry["BRIGHTDATA_PROFILE_FETCHES"] += 1
            payload = self._request_json(
                "POST",
                "/datasets/v3/scrape",
                stage="profile_lookup",
                params={"dataset_id": self.profile_dataset_id, "include_errors": "true"},
                json_body={"input": [{"url": canonical_url}]},
                allow_async=True,
            )
            raw_records = self._extract_records(payload)
            self._telemetry["BRIGHTDATA_RECORDS"] += len(raw_records)
            if not raw_records:
                return {
                    "status": "EMPTY",
                    "provider": PROVIDER_NAME,
                    "record": None,
                    "cache_hit": False,
                    "telemetry": self.telemetry(),
                }
            normalized = normalize_linkedin_record(
                raw_records[0],
                evidence_kind="PROFILE_LOOKUP",
                retrieved_at=self._retrieved_at(),
            )
            self._cache_set(cache_key, normalized)
            return {
                "status": "WORKING",
                "provider": PROVIDER_NAME,
                "record": normalized,
                "cache_hit": False,
                "telemetry": self.telemetry(),
            }
        except BrightDataProviderError as error:
            logger.warning("Bright Data profile lookup failed: %s at %s", error.code, error.stage)
            return {
                "status": error.code,
                "provider": PROVIDER_NAME,
                "record": None,
                "error": error.to_dict(),
                "telemetry": self.telemetry(),
            }

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_token}",
            "Content-Type": "application/json",
        }

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        stage: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        allow_async: bool = False,
    ) -> Any:
        url = f"{self.base_url}{path}"
        self._telemetry["BRIGHTDATA_REQUESTS"] += 1
        try:
            response = self._session.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException:
            raise BrightDataProviderError("NETWORK_ERROR", stage) from None
        if response.status_code == 202 and allow_async:
            payload = self._decode_json(response, stage)
            snapshot_id = _clean_text(payload.get("snapshot_id")) if isinstance(payload, dict) else ""
            if not snapshot_id:
                raise BrightDataProviderError("RESPONSE_PARSE_ERROR", stage, 202)
            return self._wait_for_snapshot(snapshot_id)
        if response.status_code == 422:
            raise BrightDataProviderError("NO_MATCH", stage, 422)
        if response.status_code < 200 or response.status_code >= 300:
            raise BrightDataProviderError(
                self._error_code(response.status_code),
                stage,
                response.status_code,
            )
        return self._decode_json(response, stage)

    def _wait_for_snapshot(self, snapshot_id: str) -> Any:
        deadline = self._monotonic() + self.poll_timeout_seconds
        while self._monotonic() < deadline:
            progress = self._request_json(
                "GET",
                f"/datasets/v3/progress/{snapshot_id}",
                stage="profile_snapshot_progress",
            )
            status = _clean_text(progress.get("status") if isinstance(progress, dict) else "").casefold()
            if status in {"ready", "completed", "done"}:
                return self._request_json(
                    "GET",
                    f"/datasets/v3/snapshot/{snapshot_id}",
                    stage="profile_snapshot_download",
                    params={"format": "json"},
                )
            if status in {"failed", "error", "cancelled", "canceled"}:
                raise BrightDataProviderError("SNAPSHOT_FAILED", "profile_snapshot_progress")
            self._sleep(min(2.0, max(0.0, deadline - self._monotonic())))
        raise BrightDataProviderError("SNAPSHOT_TIMEOUT", "profile_snapshot_progress")

    @staticmethod
    def _decode_json(response: requests.Response, stage: str) -> Any:
        try:
            return response.json()
        except (ValueError, TypeError):
            raise BrightDataProviderError(
                "RESPONSE_PARSE_ERROR",
                stage,
                response.status_code,
            ) from None

    @staticmethod
    def _extract_records(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("hits", "records", "results", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            if any(key in payload for key in ("name", "url", "linkedin_url", "id")):
                return [payload]
        return []

    @staticmethod
    def _error_code(status_code: int) -> str:
        if 500 <= status_code <= 599:
            return "BRIGHTDATA_SERVER_ERROR"
        return {
            400: "FILTER_ERROR",
            401: "AUTH_ERROR",
            402: "INSUFFICIENT_FUNDS",
            403: "ACCESS_DENIED",
            404: "DATASET_NOT_FOUND",
            409: "SNAPSHOT_NOT_READY",
            429: "RATE_LIMITED",
        }.get(status_code, "PROVIDER_ERROR")

    def _retrieved_at(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc).isoformat()

    @staticmethod
    def _cache_key(kind: str, value: Dict[str, Any]) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return f"{kind}:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()}"

    def _cache_get(self, key: str) -> Any:
        with _CACHE_LOCK:
            cache = self._read_cache()
            entry = cache.get(key)
            if not isinstance(entry, dict):
                return None
            if float(entry.get("expires_at") or 0) <= float(self._clock()):
                return None
            self._telemetry["BRIGHTDATA_CACHE_HITS"] += 1
            return entry.get("value")

    def _cache_set(self, key: str, value: Any) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        with _CACHE_LOCK:
            cache = self._read_cache()
            cache[key] = {
                "provider": PROVIDER_NAME,
                "retrieved_at": self._retrieved_at(),
                "expires_at": float(self._clock()) + self.cache_ttl_seconds,
                "value": value,
            }
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            temporary.write_text(json.dumps(cache, ensure_ascii=True, sort_keys=True), encoding="utf-8")
            temporary.replace(self.cache_path)

    def _read_cache(self) -> Dict[str, Any]:
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}


brightdata_linkedin_provider = BrightDataLinkedInProvider()
