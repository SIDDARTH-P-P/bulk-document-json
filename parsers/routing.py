"""
Routing steps table extractor for chronological tracking events.
"""

import re
from datetime import datetime
from typing import List, Dict, Any

def parse_iso_datetime(date_str: str, time_str: str) -> str:
    """Combines DD/MM/YYYY and HH:MM:SS into ISO 8601 string."""
    try:
        d, mo, y = map(int, date_str.split('/'))
        h, mi, s = map(int, time_str.split(':'))
        return datetime(y, mo, d, h, mi, s).isoformat()
    except Exception:
        return f"{date_str} {time_str}"

def parse_single_routing_step(
    date_str: str,
    event_str: str,
    time_str: str,
    office_str: str,
    step_num: int
) -> Dict[str, Any]:
    """Cleans and standardizes a single routing event dictionary."""
    clean_date = date_str.strip()
    clean_time = time_str.strip()
    clean_event = event_str.strip()
    clean_office = re.sub(r'[\x0c\r]', '', office_str).strip()

    return {
        "step_number": step_num,
        "date": clean_date,
        "time": clean_time,
        "timestamp": parse_iso_datetime(clean_date, clean_time),
        "event": clean_event,
        "office": clean_office
    }

def extract_routing_steps(text: str) -> List[Dict[str, Any]]:
    """Finds all chronological event steps from the routing table."""
    pattern = re.compile(
        r'(\d{2}/\d{2}/\d{4})\s+([^\n\r]+)\s*\n\s*(\d{2}:\d{2}:\d{2})\s+([^\n\r\x0c]+)'
    )
    steps = []
    for idx, match in enumerate(pattern.finditer(text), 1):
        step = parse_single_routing_step(
            date_str=match.group(1),
            event_str=match.group(2),
            time_str=match.group(3),
            office_str=match.group(4),
            step_num=idx
        )
        steps.append(step)

    return steps
