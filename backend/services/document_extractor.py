"""High-Fidelity Document & PDF Text Extractor for NABL Scopes and Quotations.

Handles PDF, XLSX, CSV, and plain text files with encoding recovery, page-by-page
extraction, and quality/confidence scoring without corrupting or losing original text.
"""
from __future__ import annotations

import io
import re
import csv
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from pypdf import PdfReader
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


def extract_text_from_bytes(
    file_bytes: bytes,
    filename: str = "document.pdf",
) -> Dict[str, Any]:
    """Extracts clean text and metadata from uploaded file bytes.

    Returns:
        {
            "status": "SUCCESS" | "EXTRACTION_UNCERTAIN" | "FAILED",
            "text": str,
            "pages": [{"page_num": int, "text": str}],
            "total_pages": int,
            "filename": str,
            "file_type": "PDF" | "CSV" | "XLSX" | "TXT" | "UNKNOWN",
            "confidence": float,
            "warning": str | None,
        }
    """
    lower_name = filename.lower()

    # 1. PDF Handling
    if lower_name.endswith(".pdf") or file_bytes.startswith(b"%PDF"):
        return _extract_pdf(file_bytes, filename)

    # 2. Excel Handling (.xlsx / .xls)
    if lower_name.endswith(".xlsx") or lower_name.endswith(".xls"):
        return _extract_excel(file_bytes, filename)

    # 3. CSV Handling (.csv)
    if lower_name.endswith(".csv"):
        return _extract_csv(file_bytes, filename)

    # 4. Text / Plain fallback (.txt, pasted text)
    return _extract_plain_text(file_bytes, filename)


def _extract_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extracts text page-by-page from PDF binary bytes using pypdf."""
    if not PYPDF_AVAILABLE:
        logger.error("pypdf is not available for PDF extraction")
        # Attempt fallback to basic printable ASCII extraction
        ascii_text = _fallback_ascii_extractor(file_bytes)
        return {
            "status": "EXTRACTION_UNCERTAIN",
            "text": ascii_text,
            "pages": [{"page_num": 1, "text": ascii_text}],
            "total_pages": 1,
            "filename": filename,
            "file_type": "PDF",
            "confidence": 0.4,
            "warning": "pypdf not installed. Basic text fallback used.",
        }

    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        pages_data = []
        full_text_parts = []

        for idx, page in enumerate(reader.pages):
            page_num = idx + 1
            try:
                page_text = page.extract_text() or ""
                # Normalize line breaks and remove unprintable control chars
                cleaned_page_text = _clean_extracted_text(page_text)
                pages_data.append({
                    "page_num": page_num,
                    "text": cleaned_page_text,
                })
                if cleaned_page_text:
                    full_text_parts.append(f"--- PAGE {page_num} ---\n{cleaned_page_text}")
            except Exception as pe:
                logger.warning("Failed to extract page %d from %s: %s", page_num, filename, pe)
                pages_data.append({"page_num": page_num, "text": ""})

        full_text = "\n\n".join(full_text_parts)

        # Quality check
        if not full_text.strip() or len(full_text.strip()) < 50:
            return {
                "status": "EXTRACTION_UNCERTAIN",
                "text": full_text,
                "pages": pages_data,
                "total_pages": total_pages,
                "filename": filename,
                "file_type": "PDF",
                "confidence": 0.3,
                "warning": "PDF appears to be scanned or image-only. Text extraction yielded minimal text. Manual parameter review required.",
            }

        return {
            "status": "SUCCESS",
            "text": full_text,
            "pages": pages_data,
            "total_pages": total_pages,
            "filename": filename,
            "file_type": "PDF",
            "confidence": 0.95,
            "warning": None,
        }

    except Exception as e:
        logger.error("PDF extraction error on %s: %s", filename, e)
        return {
            "status": "FAILED",
            "text": "",
            "pages": [],
            "total_pages": 0,
            "filename": filename,
            "file_type": "PDF",
            "confidence": 0.0,
            "warning": f"PDF parsing error: {str(e)[:150]}",
        }


def _extract_excel(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extracts tabular data from Excel worksheets."""
    try:
        import pandas as pd
        excel_file = io.BytesIO(file_bytes)
        xls = pd.ExcelFile(excel_file)
        lines = []
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            lines.append(f"=== Sheet: {sheet_name} ===")
            lines.append(df.to_string(index=False))

        full_text = "\n\n".join(lines)
        return {
            "status": "SUCCESS",
            "text": full_text,
            "pages": [{"page_num": 1, "text": full_text}],
            "total_pages": len(xls.sheet_names),
            "filename": filename,
            "file_type": "XLSX",
            "confidence": 0.95,
            "warning": None,
        }
    except Exception as e:
        logger.warning("Excel extraction error: %s", e)
        return _extract_plain_text(file_bytes, filename)


def _extract_csv(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extracts CSV data safely handling common encodings."""
    decoded = _decode_bytes(file_bytes)
    return {
        "status": "SUCCESS",
        "text": decoded,
        "pages": [{"page_num": 1, "text": decoded}],
        "total_pages": 1,
        "filename": filename,
        "file_type": "CSV",
        "confidence": 0.95,
        "warning": None,
    }


def _extract_plain_text(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extracts plain text with multi-encoding fallback."""
    decoded = _decode_bytes(file_bytes)
    return {
        "status": "SUCCESS" if decoded.strip() else "EXTRACTION_UNCERTAIN",
        "text": decoded,
        "pages": [{"page_num": 1, "text": decoded}],
        "total_pages": 1,
        "filename": filename,
        "file_type": "TXT",
        "confidence": 0.9 if decoded.strip() else 0.2,
        "warning": None if decoded.strip() else "Empty text document.",
    }


def _decode_bytes(file_bytes: bytes) -> str:
    """Decodes bytes using UTF-8, Latin-1, CP1252, or UTF-16."""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "utf-16"):
        try:
            return file_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


def _clean_extracted_text(raw: str) -> str:
    """Cleans up unprintable characters while preserving layout, table columns, and symbols."""
    # Replace non-printable ASCII (except tab and newline)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", raw)
    # Normalize multiple spaces per line but keep newlines
    lines = []
    for line in cleaned.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def _fallback_ascii_extractor(file_bytes: bytes) -> str:
    """Fallback text recovery for unparsed binary streams."""
    printable = "".join(chr(b) if 32 <= b <= 126 or b in (10, 13, 9) else " " for b in file_bytes)
    return re.sub(r"\s+", " ", printable).strip()
