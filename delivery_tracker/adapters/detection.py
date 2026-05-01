from __future__ import annotations

import re


CYPRUS_POST_PATTERNS = (
    re.compile(r"^[A-Z]{2}\d{9}[A-Z]{2}$", re.IGNORECASE),
    re.compile(r"^CPY\d{10,}$", re.IGNORECASE),
)
ACS_PATTERNS = (
    re.compile(r"^\d{10,16}$"),
    re.compile(r"^ACS[A-Z0-9]{8,}$", re.IGNORECASE),
)


def detect_carrier(tracking_number: str) -> str:
    normalized = tracking_number.strip().upper()
    if any(pattern.match(normalized) for pattern in CYPRUS_POST_PATTERNS):
        return "cyprus_post"
    if any(pattern.match(normalized) for pattern in ACS_PATTERNS):
        return "acs"
    return "unknown"
