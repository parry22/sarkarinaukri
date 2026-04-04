from __future__ import annotations
"""
PDF parser for government job notification documents.
Uses pdfplumber as primary extractor with PyMuPDF (fitz) as fallback.
"""

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pdfplumber
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def extract_text_pdfplumber(pdf_path: str) -> str | None:
    """Extract text from a PDF using pdfplumber (best for text-based PDFs)."""
    try:
        text_parts: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                else:
                    logger.debug("pdfplumber: no text on page %d", i + 1)

        if text_parts:
            return "\n\n".join(text_parts)
        return None
    except Exception as e:
        logger.warning("pdfplumber extraction failed for %s: %s", pdf_path, e)
        return None


def extract_text_pymupdf(pdf_path: str) -> str | None:
    """Extract text from a PDF using PyMuPDF (fallback for problematic PDFs)."""
    try:
        text_parts: list[str] = []
        doc = fitz.open(pdf_path)
        for i, page in enumerate(doc):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(page_text)
            else:
                logger.debug("PyMuPDF: no text on page %d", i + 1)
        doc.close()

        if text_parts:
            return "\n\n".join(text_parts)
        return None
    except Exception as e:
        logger.warning("PyMuPDF extraction failed for %s: %s", pdf_path, e)
        return None


def _is_url(path: str) -> bool:
    """Check if the given path is a URL."""
    try:
        parsed = urlparse(path)
        return parsed.scheme in ("http", "https")
    except Exception:
        return False


def _download_pdf_to_temp(url: str) -> str | None:
    """Download a PDF from a URL to a temporary file. Returns the temp file path or None."""
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()

        suffix = ".pdf"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp.write(response.content)
        tmp.close()
        logger.info("Downloaded PDF from %s to %s", url, tmp.name)
        return tmp.name
    except Exception as e:
        logger.error("Failed to download PDF from %s: %s", url, e)
        return None


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from a notification PDF.

    Accepts either a local file path or a URL. If a URL is provided, the PDF
    is downloaded to a temporary file first.

    Tries pdfplumber first (better table/layout handling), then falls back
    to PyMuPDF for PDFs that pdfplumber cannot handle. Returns empty string
    if both fail (image-based PDFs would need OCR via Tesseract in future).

    Args:
        pdf_path: Path to the PDF file on disk, or a URL to download.

    Returns:
        Extracted text as a string. Empty string if extraction fails.
    """
    temp_file: str | None = None

    # If it's a URL, download to a temp file first
    if _is_url(pdf_path):
        temp_file = _download_pdf_to_temp(pdf_path)
        if not temp_file:
            return ""
        local_path = temp_file
    else:
        local_path = pdf_path

    try:
        path = Path(local_path)
        if not path.exists():
            logger.error("PDF file not found: %s", local_path)
            return ""

        if not path.suffix.lower() == ".pdf":
            logger.error("Not a PDF file: %s", local_path)
            return ""

        # Primary: pdfplumber
        text = extract_text_pdfplumber(local_path)
        if text and len(text.strip()) > 50:
            logger.info("Extracted %d chars via pdfplumber from %s", len(text), path.name)
            return text.strip()

        # Fallback: PyMuPDF
        logger.info("pdfplumber insufficient, trying PyMuPDF for %s", path.name)
        text = extract_text_pymupdf(local_path)
        if text and len(text.strip()) > 50:
            logger.info("Extracted %d chars via PyMuPDF from %s", len(text), path.name)
            return text.strip()

        # Both failed — likely an image-based / scanned PDF
        logger.warning(
            "Both extractors failed for %s. PDF may be image-based (OCR not yet implemented).",
            path.name,
        )
        return ""
    finally:
        # Clean up temp file if we downloaded one
        if temp_file:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception:
                pass
