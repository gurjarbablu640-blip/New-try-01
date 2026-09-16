"""Bounded Production Page Content Fetcher and Text Extractor.

Implements:
- Safe, bounded HTTP GET with timeouts, size limits, and redirect controls
- HTML cleanup (stripping nav, header, footer, script, style, ads, cookie notices)
- Publication date and metadata extraction (JSON-LD, OpenGraph, meta tags)
- Status classification (FETCH_SUCCESS, FETCH_BLOCKED, FETCH_TIMEOUT, FETCH_UNSUPPORTED, FETCH_EMPTY)
- PostgreSQL-backed evidence caching and 24h freshness reuse
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from models.research_evidence import ResearchEvidenceRecord

logger = logging.getLogger(__name__)

# Constants
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB limit
REQUEST_TIMEOUT_SECONDS = 6.0
MAX_EXTRACTED_CHARS = 12000
FRESHNESS_CACHE_HOURS = 24

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/plain",
}

STATUS_FETCH_SUCCESS = "FETCH_SUCCESS"
STATUS_FETCH_BLOCKED = "FETCH_BLOCKED"
STATUS_FETCH_TIMEOUT = "FETCH_TIMEOUT"
STATUS_FETCH_UNSUPPORTED = "FETCH_UNSUPPORTED"
STATUS_FETCH_EMPTY = "FETCH_EMPTY"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36 (Salesoorja Industrial Research Bot/2.0)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def normalize_url(url: str) -> str:
    """Strip URL fragments, query tracking parameters (utm_*, etc.), and trailing slashes."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Filter out common tracking query params
        query_params = []
        if parsed.query:
            for part in parsed.query.split("&"):
                k = part.split("=")[0].lower()
                if not k.startswith("utm_") and k not in {"fbclid", "gclid", "ref"}:
                    query_params.append(part)
        new_query = "&".join(query_params)
        path = parsed.path.rstrip("/") if parsed.path != "/" else "/"
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", new_query, ""))
    except Exception:
        return url.strip()


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized text."""
    clean = re.sub(r"\s+", " ", (text or "").strip()).casefold()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()


class PageContentFetcher:
    """Production web page content retriever and structured article extractor."""

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or requests.Session()
        self._session.headers.update(DEFAULT_HEADERS)

    def fetch_page(
        self,
        url: str,
        db: Optional[Session] = None,
        source_type: str = "SECONDARY",
        query_log_id: Optional[int] = None,
        company_id: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Fetch and extract clean article text and metadata from a URL with caching."""
        norm_url = normalize_url(url)
        if not norm_url:
            return {
                "url": url,
                "normalized_url": "",
                "fetch_status": STATUS_FETCH_UNSUPPORTED,
                "http_status": None,
                "title": "",
                "publication_date": "",
                "publisher": "",
                "extracted_text": "",
                "content_hash": "",
                "source_type": source_type,
                "cached": False,
            }

        # 1. Freshness Check: Reuse recent cached evidence (< 24h)
        if db is not None and not force_refresh:
            cached = self._check_cache(db, norm_url)
            if cached:
                logger.info("[PAGE_FETCH_CACHE_HIT] %s (hash: %s...)", norm_url, cached["content_hash"][:8])
                return cached

        # 2. Network Fetch with safety bounds
        logger.info("[PAGE_FETCH_STARTED] %s", norm_url)
        fetched_data = self._execute_fetch(norm_url)

        # 3. Persist into PostgreSQL
        if db is not None:
            self._persist_record(
                db=db,
                data=fetched_data,
                source_type=source_type,
                query_log_id=query_log_id,
                company_id=company_id,
            )

        status = fetched_data.get("fetch_status")
        if status == STATUS_FETCH_SUCCESS:
            logger.info("[PAGE_FETCH_SUCCESS] %s (%d chars extracted)", norm_url, len(fetched_data.get("extracted_text", "")))
        else:
            logger.info("[PAGE_FETCH_%s] %s (HTTP %s)", status.replace("FETCH_", ""), norm_url, fetched_data.get("http_status"))

        return fetched_data

    def _check_cache(self, db: Session, norm_url: str) -> Optional[Dict[str, Any]]:
        """Check for existing successful evidence fetched within the freshness window."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_CACHE_HOURS)
            rec = (
                db.query(ResearchEvidenceRecord)
                .filter(
                    ResearchEvidenceRecord.normalized_url == norm_url,
                    ResearchEvidenceRecord.fetch_status == STATUS_FETCH_SUCCESS,
                    ResearchEvidenceRecord.retrieved_at >= cutoff,
                )
                .order_by(ResearchEvidenceRecord.id.desc())
                .first()
            )
            if rec:
                return {
                    "url": rec.url,
                    "normalized_url": rec.normalized_url,
                    "fetch_status": rec.fetch_status,
                    "http_status": rec.http_status,
                    "title": rec.title or "",
                    "publication_date": rec.publication_date or "",
                    "publisher": rec.publisher or "",
                    "author": rec.author or "",
                    "extracted_text": rec.extracted_text or "",
                    "content_hash": rec.content_hash or "",
                    "source_type": rec.source_type,
                    "evidence_json": rec.evidence_json or {},
                    "cached": True,
                    "record_id": rec.id,
                }
        except Exception as exc:
            logger.debug("Evidence cache lookup failed: %s", exc)
        return None

    def _execute_fetch(self, url: str) -> Dict[str, Any]:
        """Perform bounded HTTP retrieval and parsing."""
        result: Dict[str, Any] = {
            "url": url,
            "normalized_url": url,
            "fetch_status": STATUS_FETCH_SUCCESS,
            "http_status": None,
            "title": "",
            "publication_date": "",
            "publisher": "",
            "author": "",
            "extracted_text": "",
            "content_hash": "",
            "cached": False,
        }

        # Check for obvious non-HTML file extensions
        path_lower = urlparse(url).path.lower()
        if path_lower.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".tar", ".gz", ".mp4", ".png", ".jpg")):
            result["fetch_status"] = STATUS_FETCH_UNSUPPORTED
            return result

        try:
            with self._session.get(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                stream=True,
                allow_redirects=True,
            ) as response:
                result["http_status"] = response.status_code
                final_url = str(response.url or url)
                result["normalized_url"] = normalize_url(final_url)

                if response.status_code in {401, 403, 429}:
                    result["fetch_status"] = STATUS_FETCH_BLOCKED
                    return result
                if response.status_code >= 400:
                    result["fetch_status"] = STATUS_FETCH_BLOCKED if response.status_code in {401, 403} else STATUS_FETCH_EMPTY
                    return result

                content_type = response.headers.get("Content-Type", "").lower().split(";")[0].strip()
                if content_type and content_type not in ALLOWED_CONTENT_TYPES:
                    result["fetch_status"] = STATUS_FETCH_UNSUPPORTED
                    return result

                # Read bounded bytes
                chunks = []
                bytes_read = 0
                for chunk in response.iter_content(chunk_size=8192):
                    chunks.append(chunk)
                    bytes_read += len(chunk)
                    if bytes_read > MAX_RESPONSE_BYTES:
                        break

                raw_bytes = b"".join(chunks)
                encoding = response.encoding or "utf-8"
                try:
                    html_text = raw_bytes.decode(encoding, errors="replace")
                except Exception:
                    html_text = raw_bytes.decode("utf-8", errors="replace")

        except (requests.exceptions.Timeout, requests.exceptions.ConnectTimeout):
            result["fetch_status"] = STATUS_FETCH_TIMEOUT
            return result
        except requests.exceptions.RequestException as e:
            err_str = str(e).lower()
            if "timeout" in err_str:
                result["fetch_status"] = STATUS_FETCH_TIMEOUT
            elif "403" in err_str or "blocked" in err_str:
                result["fetch_status"] = STATUS_FETCH_BLOCKED
            else:
                result["fetch_status"] = STATUS_FETCH_BLOCKED
            return result
        except Exception:
            result["fetch_status"] = STATUS_FETCH_BLOCKED
            return result

        # Parse HTML and extract clean readable text
        extracted = self.extract_clean_content(html_text, base_url=url)
        result.update(extracted)

        if not result["extracted_text"] or len(result["extracted_text"]) < 50:
            result["fetch_status"] = STATUS_FETCH_EMPTY

        result["content_hash"] = compute_content_hash(result["extracted_text"])
        return result

    def extract_clean_content(self, html: str, base_url: str = "") -> Dict[str, Any]:
        """Clean HTML, strip noise/nav/boilerplate, and extract title, publication date, and main text."""
        if not html:
            return {"title": "", "publication_date": "", "publisher": "", "author": "", "extracted_text": ""}

        soup = BeautifulSoup(html, "html.parser")

        # 1. Metadata Extraction
        title = ""
        pub_date = ""
        publisher = ""
        author = ""

        # Title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = str(og_title["content"]).strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text().strip()

        # Publisher / Site Name
        og_site = soup.find("meta", property="og:site_name")
        if og_site and og_site.get("content"):
            publisher = str(og_site["content"]).strip()
        else:
            domain = urlparse(base_url).netloc.replace("www.", "")
            publisher = domain.split(".")[0].capitalize() if domain else ""

        # Author
        author_meta = soup.find("meta", attrs={"name": "author"}) or soup.find("meta", property="article:author")
        if author_meta and author_meta.get("content"):
            author = str(author_meta["content"]).strip()

        # Publication Date extraction from metadata
        pub_date_meta = (
            soup.find("meta", property="article:published_time")
            or soup.find("meta", property="article:published")
            or soup.find("meta", attrs={"name": "publication_date"})
            or soup.find("meta", attrs={"name": "publish-date"})
            or soup.find("meta", attrs={"name": "pubdate"})
            or soup.find("meta", attrs={"name": "date"})
        )
        if pub_date_meta and pub_date_meta.get("content"):
            raw_date = str(pub_date_meta["content"]).strip()
            # Clean up ISO date: e.g. 2026-08-14T09:30:00Z -> 2026-08-14
            match = re.search(r"(202[0-9]-[01][0-9]-[0-3][0-9])", raw_date)
            if match:
                pub_date = match.group(1)
            else:
                pub_date = raw_date[:25]

        # JSON-LD Schema.org extraction for date and publisher
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict):
                        date_str = item.get("datePublished") or item.get("dateCreated")
                        if date_str and not pub_date:
                            m = re.search(r"(202[0-9]-[01][0-9]-[0-3][0-9])", str(date_str))
                            if m:
                                pub_date = m.group(1)
                        pub_info = item.get("publisher")
                        if isinstance(pub_info, dict) and pub_info.get("name") and not publisher:
                            publisher = str(pub_info["name"]).strip()
            except Exception:
                pass

        # Fallback to <time> tag
        if not pub_date:
            time_tag = soup.find("time")
            if time_tag:
                dt_val = time_tag.get("datetime") or time_tag.get_text()
                m = re.search(r"(202[0-9]-[01][0-9]-[0-3][0-9])", str(dt_val))
                if m:
                    pub_date = m.group(1)

        # 2. Strip Noise Elements
        noise_selectors = [
            "script", "style", "noscript", "iframe", "svg",
            "nav", "header", "footer", "aside",
            ".nav", ".navbar", ".menu", ".footer", ".header",
            ".sidebar", ".cookie-banner", ".cookie-consent",
            ".advertisement", ".ad-container", ".banner",
            "#cookie-banner", "#footer", "#header", "#sidebar",
        ]
        for selector in noise_selectors:
            for el in soup.select(selector):
                el.decompose()

        # 3. Extract Main Article Body Text
        # Prefer <article>, or content containers, otherwise body
        content_container = (
            soup.find("article")
            or soup.find("main")
            or soup.find(class_=re.compile(r"(article[-_]?body|story[-_]?content|post[-_]?content|entry[-_]?content|main[-_]?content)", re.I))
            or soup.body
        )
        if content_container is None:
            content_container = soup

        # Extract meaningful paragraphs and headings
        blocks = []
        for tag in content_container.find_all(["p", "h1", "h2", "h3", "h4", "li"]):
            text = tag.get_text(separator=" ", strip=True)
            # Filter out boilerplate micro-text
            if len(text) > 25 and not self._is_boilerplate_phrase(text):
                blocks.append(text)

        cleaned_text = "\n\n".join(blocks)
        if len(cleaned_text) > MAX_EXTRACTED_CHARS:
            cleaned_text = cleaned_text[:MAX_EXTRACTED_CHARS] + "..."

        return {
            "title": title,
            "publication_date": pub_date,
            "publisher": publisher,
            "author": author,
            "extracted_text": cleaned_text,
        }

    @staticmethod
    def _is_boilerplate_phrase(text: str) -> bool:
        """Filter out common news website boilerplate phrases."""
        lower = text.lower()
        boilerplate = (
            "all rights reserved",
            "terms of service",
            "privacy policy",
            "subscribe to our newsletter",
            "cookie policy",
            "sign up for free",
            "click here to read",
            "follow us on twitter",
            "download the app",
            "advertisement",
        )
        return any(bp in lower for bp in boilerplate)

    def _persist_record(
        self,
        db: Session,
        data: Dict[str, Any],
        source_type: str,
        query_log_id: Optional[int],
        company_id: Optional[int],
    ) -> None:
        """Persist evidence record into PostgreSQL."""
        try:
            record = ResearchEvidenceRecord(
                url=data["url"],
                normalized_url=data.get("normalized_url", data["url"]),
                content_hash=data.get("content_hash", ""),
                title=data.get("title"),
                publication_date=data.get("publication_date"),
                author=data.get("author"),
                publisher=data.get("publisher"),
                fetch_status=data.get("fetch_status", STATUS_FETCH_SUCCESS),
                http_status=data.get("http_status"),
                source_type=source_type,
                extracted_text=data.get("extracted_text", ""),
                evidence_json=data.get("evidence_json") or {},
                company_id=company_id,
                query_log_id=query_log_id,
            )
            db.add(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Could not persist research evidence record: %s", exc)


page_content_fetcher = PageContentFetcher()
