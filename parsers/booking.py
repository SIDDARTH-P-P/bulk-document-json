"""
Booking origin, booking date, destination pincode, and office extractors.
"""

import re
from typing import Optional, List

def extract_booking_office(lines: List[str]) -> Optional[str]:
    """Finds origin booking post office name."""
    for i, line in enumerate(lines):
        if "Booked At:" in line and i + 1 < len(lines):
            val = lines[i + 1][:30].strip()
            if val:
                return val
    return None

def extract_booking_date(lines: List[str]) -> Optional[str]:
    """Finds booking date in DD/MM/YYYY format."""
    for i, line in enumerate(lines):
        if "Booked At:" in line and i + 1 < len(lines):
            segment = lines[i + 1][30:65] if len(lines[i + 1]) > 30 else ""
            m = re.search(r"(\d{2}/\d{2}/\d{4})", segment)
            if m:
                return m.group(1).strip()
    return None

def extract_destination_pin(lines: List[str]) -> Optional[str]:
    """Finds 6-digit destination pincode."""
    for i, line in enumerate(lines):
        if "Destination Pincode:" in line and i + 1 < len(lines):
            segment = lines[i + 1][:30]
            m = re.search(r"\b(\d{6})\b", segment)
            if m:
                return m.group(1).strip()
    return None

def extract_destination_office(lines: List[str]) -> Optional[str]:
    """Finds destination office text if provided in header."""
    for i, line in enumerate(lines):
        if "Booked At:" in line and i + 1 < len(lines):
            dest = lines[i + 1][65:].strip() if len(lines[i + 1]) > 65 else ""
            if dest and not dest.startswith("Routing"):
                return dest
    return None

def extract_delivered_on_header(lines: List[str]) -> Optional[str]:
    """Finds delivered timestamp from header table if present."""
    for i, line in enumerate(lines):
        if "Destination Pincode:" in line and i + 1 < len(lines):
            segment = lines[i + 1][25:]
            m = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}|\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", segment)
            if m:
                return m.group(1).strip()
    return None
