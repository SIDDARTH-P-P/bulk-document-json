"""
Orchestrator: Composes header, booking, routing, and status functions to parse a tracking PDF.
"""

import os
from typing import Union, Dict, Any
from parsers.extractor import extract_text_from_pdf_path, extract_text_from_pdf_bytes, get_clean_lines
from parsers.header import (
    extract_consignment_number,
    extract_article_number,
    extract_article_type,
    extract_tariff
)
from parsers.booking import (
    extract_booking_office,
    extract_booking_date,
    extract_destination_pin,
    extract_destination_office,
    extract_delivered_on_header
)
from parsers.routing import extract_routing_steps
from parsers.status import (
    detect_return_info,
    detect_delivery_info,
    build_milestones,
    format_status_label
)

def parse_tracking_pdf(source: Union[str, bytes], filename: str = "") -> Dict[str, Any]:
    """
    Parses an India Post speed post consignment tracking PDF.
    Accepts either a file path (str) or raw PDF bytes (bytes).
    Returns a clean, structured dictionary suitable for JSON serialization.
    """
    if isinstance(source, bytes):
        raw_text = extract_text_from_pdf_bytes(source)
        source_name = filename or "uploaded_document.pdf"
    elif isinstance(source, str):
        if not os.path.isfile(source):
            raise FileNotFoundError(f"File not found: {source}")
        raw_text = extract_text_from_pdf_path(source)
        source_name = filename or os.path.basename(source)
    else:
        raise TypeError("Source must be either a file path (str) or bytes")

    lines = raw_text.splitlines()

    # 1. Header extraction
    consignment_no = extract_consignment_number(raw_text)
    article_no = extract_article_number(lines, fallback=consignment_no)
    if not consignment_no and article_no:
        consignment_no = article_no
    article_type = extract_article_type(lines)
    tariff = extract_tariff(lines)

    # 2. Booking extraction
    booked_at = extract_booking_office(lines)
    booked_on = extract_booking_date(lines)
    destination_pin = extract_destination_pin(lines)
    destination_office = extract_destination_office(lines)
    header_delivered = extract_delivered_on_header(lines)

    # 3. Routing steps extraction
    routing_steps = extract_routing_steps(raw_text)

    # 4. Status and milestone resolution
    is_returned, return_reason = detect_return_info(routing_steps)
    is_delivered, delivered_on = detect_delivery_info(routing_steps, header_delivered=header_delivered)
    milestones = build_milestones(routing_steps, has_booked_date=bool(booked_on), is_delivered=is_delivered)

    current_status = routing_steps[-1]["event"] if routing_steps else ("Delivered" if is_delivered else None)
    origin_office = routing_steps[0]["office"] if routing_steps else booked_at
    last_office = routing_steps[-1]["office"] if routing_steps else destination_office

    delivery_status = format_status_label(
        is_returned=is_returned,
        return_reason=return_reason,
        is_delivered=is_delivered,
        current_status=current_status
    )

    return {
        "source_file": source_name,
        "document_type": "india_post_tracking",
        "consignment_number": consignment_no,
        "article_number": article_no,
        "article_type": article_type,
        "tariff": tariff,
        "booked_at": booked_at,
        "booked_on": booked_on,
        "destination_pincode": destination_pin,
        "destination": destination_office,
        "delivered_on": delivered_on,
        "current_status": current_status,
        "delivery_status": delivery_status,
        "is_delivered": is_delivered,
        "is_returned_to_sender": is_returned,
        "return_reason": return_reason,
        "origin_office": origin_office,
        "destination_office": last_office,
        "milestones": milestones,
        "routing_steps": routing_steps
    }
