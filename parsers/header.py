"""
Header field extraction: Consignment ID, Article Number, Article Type, Tariff.
"""

import re
from typing import Optional, List

def extract_consignment_number(text: str) -> Optional[str]:
    """Finds Consignment No from the top of the tracking receipt."""
    m = re.search(r"Consignment No:\s*([A-Z0-9]+)", text)
    return m.group(1).strip() if m else None

def extract_article_number(lines: List[str], fallback: Optional[str] = None) -> Optional[str]:
    """Finds Article Number from the header table."""
    for i, line in enumerate(lines):
        if "Article Number:" in line and i + 1 < len(lines):
            m = re.search(r"([A-Z0-9]{10,15})", lines[i + 1])
            if m:
                return m.group(1).strip()
    return fallback

def extract_article_type(lines: List[str]) -> Optional[str]:
    """Finds Article Type (e.g., SP_INLAND_DOC) from the header table."""
    for i, line in enumerate(lines):
        if "Article Number:" in line and i + 1 < len(lines):
            row = lines[i + 1]
            segment = row[25:65] if len(row) > 25 else ""
            m = re.search(r"(SP_[A-Z0-9_]+|[A-Za-z_]{3,25})", segment)
            if m:
                return m.group(1).strip()
    return None

def extract_tariff(lines: List[str]) -> Optional[str]:
    """Finds Tariff amount (e.g., ₹55) from the header table."""
    for i, line in enumerate(lines):
        if "Article Number:" in line and i + 1 < len(lines):
            row = lines[i + 1]
            segment = row[60:] if len(row) > 60 else ""
            m = re.search(r"(₹\s*\d+|\d+\s*INR|\b\d+\b)", segment)
            if m:
                return m.group(1).strip()
    return None
