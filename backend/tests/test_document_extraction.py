import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.document_extraction import (
    extract_local_pdf_with_docling,
    extract_pdf_bytes,
    extract_url_with_crawl4ai,
)


class DocumentExtractionTests(unittest.TestCase):
    def test_pdf_boundary_uses_existing_pypdf_for_local_pdf_fixture(self):
        # Minimal local PDF fixture. It is intentionally blank; pypdf should report
        # an uncertain extraction rather than inventing text.
        fixture = b"%PDF-1.4\n1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n2 0 obj<< /Type /Pages /Kids [] /Count 0 >>endobj\ntrailer<< /Root 1 0 R >>\n%%EOF"
        result = extract_pdf_bytes(fixture, "fixture.pdf")
        self.assertEqual(result.adapter, "pypdf")
        self.assertIn(result.status, {"EXTRACTION_UNCERTAIN", "FAILED"})

    def test_docling_is_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "fixture.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF")
            result = extract_local_pdf_with_docling(pdf, enabled=False)
            self.assertEqual(result.status, "DISABLED")
            self.assertEqual(result.adapter, "docling")

    def test_docling_uses_injected_converter_without_import_or_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "fixture.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF")

            class Document:
                def export_to_markdown(self):
                    return "# Extracted locally"

            class Converted:
                document = Document()

            class Converter:
                def convert(self, path):
                    assert path.endswith("fixture.pdf")
                    return Converted()

            result = extract_local_pdf_with_docling(pdf, enabled=True, converter=Converter())
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(result.text, "# Extracted locally")

    def test_crawl4ai_rejects_non_public_and_non_http_urls(self):
        result = asyncio.run(extract_url_with_crawl4ai("file:///etc/passwd", enabled=True))
        self.assertEqual(result.status, "REJECTED")

    def test_crawl4ai_uses_injected_async_crawler_for_public_url(self):
        class Outcome:
            markdown = "Public page"

        class Crawler:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def arun(self, *, url):
                assert url == "https://example.com/page"
                return Outcome()

        # Avoid DNS in this unit test; the URL policy itself is covered by rejection.
        with patch("services.document_extraction._public_http_url", return_value=(True, "")):
            result = asyncio.run(extract_url_with_crawl4ai("https://example.com/page", enabled=True, crawler=Crawler()))
            self.assertEqual(result.status, "SUCCESS")
            self.assertEqual(result.text, "Public page")


if __name__ == "__main__":
    unittest.main()

