"""
Status resolution, return reason detection, and milestone calculation.
"""

from typing import List, Dict, Any, Tuple, Optional

MILESTONE_NAMES = ["Booked", "Dispatched", "In Transit", "Out for Delivery", "Delivered"]

def detect_return_info(routing_steps: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Detects if article was returned to sender and extracts specific reason."""
    for step in routing_steps:
        ev_lower = step["event"].lower()
        if "returned to sender" in ev_lower:
            reason = step["event"].split("-", 1)[1].strip() if "-" in step["event"] else step["event"].strip()
            return True, reason
    return False, None

def detect_delivery_info(
    routing_steps: List[Dict[str, Any]],
    header_delivered: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Detects whether item was delivered and captures timestamp."""
    delivered_on = header_delivered
    is_delivered = bool(header_delivered)

    for step in routing_steps:
        if "delivered" in step["event"].lower():
            is_delivered = True
            if not delivered_on:
                delivered_on = step["timestamp"]

    return is_delivered, delivered_on

def build_milestones(
    routing_steps: List[Dict[str, Any]],
    has_booked_date: bool,
    is_delivered: bool
) -> List[Dict[str, Any]]:
    """Calculates active state for each milestone in the tracking lifecycle."""
    has_booked = has_booked_date or any("induct" in s["event"].lower() or "book" in s["event"].lower() for s in routing_steps)
    has_dispatched = any("dispatch" in s["event"].lower() for s in routing_steps)
    has_transit = any("transit" in s["event"].lower() or "bagged" in s["event"].lower() or "received" in s["event"].lower() for s in routing_steps)
    has_out = any("out for delivery" in s["event"].lower() or "invoiced" in s["event"].lower() for s in routing_steps)

    status_flags = {
        "Booked": has_booked,
        "Dispatched": has_dispatched,
        "In Transit": has_transit,
        "Out for Delivery": has_out,
        "Delivered": is_delivered
    }

    return [{"name": name, "completed": status_flags.get(name, False)} for name in MILESTONE_NAMES]

def format_status_label(
    is_returned: bool,
    return_reason: Optional[str],
    is_delivered: bool,
    current_status: Optional[str]
) -> str:
    """Produces the human-readable summary status badge string."""
    if is_returned:
        return f"Returned to Sender ({return_reason})" if return_reason else "Returned to Sender"
    if is_delivered:
        return "Delivered"
    if current_status:
        return current_status
    return "In Transit"
