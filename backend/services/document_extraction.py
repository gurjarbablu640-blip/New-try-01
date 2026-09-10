"""Optional, isolated document extraction adapters.

The existing :mod:`document_extractor` remains the dependency-safe fallback.  This
module deliberately does not add Docling or Crawl4AI to the requirements file;
callers can opt in through feature flags and dependency injection.
"""
from __future__ import annotations

import asyncio
import inspect
import ipaddress
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000


@dataclass(frozen=True)
class ExtractionResult:
    """Stable result contract for parent workflows."""

    status: str
    text: str = ""
    source: str = ""
    adapter: str = ""
    warning: str | None = None
    metadata: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _result(status: str, *, source: str = "", adapter: str = "", text: str = "", warning: str | None = None, metadata: Mapping[str, Any] | None = None) -> ExtractionResult:
    return ExtractionResult(status, text[:MAX_TEXT_CHARS], source, adapter, warning, metadata)


def extract_pdf_bytes(file_bytes: bytes, filename: str = "document.pdf") -> ExtractionResult:
    """Use the installed pypdf extractor with a bounded byte input.

    This is the safe default and never loads an optional package.
    """
    if not isinstance(file_bytes, (bytes, bytearray)):
        return _result("FAILED", source=filename, adapter="pypdf", warning="PDF input must be bytes.")
    if len(file_bytes) > MAX_DOCUMENT_BYTES:
        return _result("REJECTED", source=filename, adapter="pypdf", warning=f"PDF exceeds {MAX_DOCUMENT_BYTES} byte limit.")
    try:
        from .document_extractor import extract_text_from_bytes

        parsed = extract_text_from_bytes(bytes(file_bytes), filename)
        return _result(parsed.get("status", "FAILED"), source=filename, adapter="pypdf", text=parsed.get("text", ""), warning=parsed.get("warning"), metadata={"total_pages": parsed.get("total_pages", 0), "file_type": parsed.get("file_type", "PDF")})
    except Exception as exc:  # defensive boundary for malformed/hostile PDFs
        return _result("FAILED", source=filename, adapter="pypdf", warning=f"pypdf adapter failed: {str(exc)[:160]}")


def extract_local_pdf_with_docling(path: str | os.PathLike[str], *, enabled: bool | None = None, converter: Any = None) -> ExtractionResult:
    """Convert one local PDF with an injected or explicitly enabled Docling converter.

    The default is disabled.  A converter must be injected by the application (or
    the caller must explicitly enable the adapter); this prevents an accidental
    import from downloading ML artifacts.  Production wiring should provide a
    converter configured with a pre-populated local artifact cache.
    """
    source = str(path)
    if enabled is None:
        enabled = os.getenv("SALESOORJA_DOCLING_ENABLED", "0").lower() in {"1", "true", "yes"}
    if not enabled:
        return _result("DISABLED", source=source, adapter="docling", warning="Docling adapter is disabled.")
    pdf = Path(path)
    if pdf.suffix.lower() != ".pdf":
        return _result("REJECTED", source=source, adapter="docling", warning="Docling adapter accepts local PDF files only.")
    try:
        if not pdf.is_file():
            return _result("FAILED", source=source, adapter="docling", warning="Local PDF does not exist.")
        if pdf.stat().st_size > MAX_DOCUMENT_BYTES:
            return _result("REJECTED", source=source, adapter="docling", warning=f"PDF exceeds {MAX_DOCUMENT_BYTES} byte limit.")
    except OSError as exc:
        return _result("FAILED", source=source, adapter="docling", warning=f"Cannot inspect local PDF: {exc}")
    try:
        if converter is None:
            from docling.document_converter import DocumentConverter  # optional import

            # Do not request or trigger model installation here.  Callers should
            # inject a converter whose model cache was provisioned out of band.
            converter = DocumentConverter()
        converted = converter.convert(str(pdf))
        document = getattr(converted, "document", converted)
        text = document.export_to_markdown() if hasattr(document, "export_to_markdown") else str(document)
        return _result("SUCCESS" if text.strip() else "EXTRACTION_UNCERTAIN", source=source, adapter="docling", text=text, warning=None if text.strip() else "Docling returned no text.")
    except ImportError:
        return _result("UNAVAILABLE", source=source, adapter="docling", warning="Optional Docling package is not installed.")
    except Exception as exc:
        return _result("FAILED", source=source, adapter="docling", warning=f"Docling conversion failed: {str(exc)[:160]}")


def _public_http_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return False, "Only credential-free http(s) URLs are allowed."
        if parsed.port not in (None, 80, 443):
            return False, "Non-standard URL ports are blocked."
        host = parsed.hostname.rstrip(".")
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global:
                return False, "Private, loopback, link-local, and reserved destinations are blocked."
        except ValueError:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            if not infos or any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
                return False, "URL resolves to a non-public destination."
        return True, ""
    except (OSError, ValueError):
        return False, "URL host could not be validated."


async def extract_url_with_crawl4ai(url: str, *, enabled: bool | None = None, crawler: Any = None, crawler_factory: Callable[[], Any] | None = None) -> ExtractionResult:
    """Run Crawl4AI in-process for one validated public URL.

    The Crawl4AI Docker/API server is intentionally unsupported by this boundary.
    """
    if enabled is None:
        enabled = os.getenv("SALESOORJA_CRAWL4AI_ENABLED", "0").lower() in {"1", "true", "yes"}
    if not enabled:
        return _result("DISABLED", source=url, adapter="crawl4ai", warning="Crawl4AI adapter is disabled.")
    valid, reason = _public_http_url(url)
    if not valid:
        return _result("REJECTED", source=url, adapter="crawl4ai", warning=reason)
    try:
        if crawler is None:
            if crawler_factory is None:
                from crawl4ai import AsyncWebCrawler  # optional import

                crawler_factory = AsyncWebCrawler
            crawler = crawler_factory()
        async def run() -> Any:
            async with crawler as active:
                return await active.arun(url=url)
        outcome = await run()
        text = getattr(outcome, "markdown", None) or getattr(outcome, "extracted_content", None) or str(outcome)
        return _result("SUCCESS" if text.strip() else "EXTRACTION_UNCERTAIN", source=url, adapter="crawl4ai", text=text, warning=None if text.strip() else "Crawl4AI returned no text.")
    except ImportError:
        return _result("UNAVAILABLE", source=url, adapter="crawl4ai", warning="Optional Crawl4AI package is not installed.")
    except Exception as exc:
        return _result("FAILED", source=url, adapter="crawl4ai", warning=f"Crawl4AI extraction failed: {str(exc)[:160]}")


def extract_url_with_crawl4ai_sync(url: str, **kwargs: Any) -> ExtractionResult:
    """Synchronous convenience wrapper for non-async parent code."""
    if inspect.iscoroutinefunction(extract_url_with_crawl4ai):
        return asyncio.run(extract_url_with_crawl4ai(url, **kwargs))
    raise RuntimeError("Unexpected Crawl4AI adapter state")
