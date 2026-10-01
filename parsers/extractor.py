"""
PDF text extraction helper functions using pdftotext.
"""

import subprocess
import tempfile
import os
from typing import List

def extract_text_from_pdf_path(pdf_path: str) -> str:
    """Extracts raw text from a PDF file preserving visual column layout."""
    proc = subprocess.run(['pdftotext', '-layout', pdf_path, '-'], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed on {pdf_path}: {proc.stderr}")
    return proc.stdout

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extracts text from in-memory PDF bytes (e.g. from Postman or HTTP upload)."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        return extract_text_from_pdf_path(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def get_clean_lines(text: str) -> List[str]:
    """Splits text into non-empty stripped lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]
