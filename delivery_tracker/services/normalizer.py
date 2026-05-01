from __future__ import annotations


STATUS_MAP: dict[str, tuple[str, ...]] = {
    "CREATED": (
        "created",
        "posted",
        "accepted",
        "shipment information received",
        "label created",
        "receive item from customer",
    ),
    "IN_TRANSIT": (
        "in transit",
        "transit",
        "departed",
        "arrived at facility",
        "processing",
        "transporting",
        "receive item at office of exchange",
        "insert item into bag",
        "send item to domestic location",
        "return item from customs",
    ),
    "OUT_FOR_DELIVERY": ("out for delivery", "with courier", "delivery today"),
    "READY_FOR_PICKUP": (
        "ready for pickup",
        "available for collection",
        "awaiting collection",
        "collection point",
        "arrived at acs",
        "delivery pin",
        "please present id",
    ),
    "DELIVERED": ("delivered", "signed", "collected"),
    "EXCEPTION": (
        "exception",
        "failed",
        "returned",
        "unable",
        "not found",
        "error",
        "expired",
        "hold item at office of exchange",
        "held by import customs",
        "insufficient / incomplete / incorrect documentation",
        "item held for inspection",
    ),
}


def normalize_status(status_raw: str | None) -> str:
    if not status_raw:
        return "UNKNOWN"

    haystack = status_raw.strip().lower()
    for normalized, variants in STATUS_MAP.items():
        if any(variant in haystack for variant in variants):
            return normalized

    inferred = _infer_status_heuristically(haystack)
    if inferred:
        return inferred
    return "UNKNOWN"


def _infer_status_heuristically(haystack: str) -> str | None:
    if "deliver" in haystack and "item" in haystack:
        return "DELIVERED"

    if "collection point" in haystack or "pick-up" in haystack or "pickup point" in haystack:
        return "READY_FOR_PICKUP"

    if "out for delivery" in haystack or ("delivery" in haystack and "courier" in haystack):
        return "OUT_FOR_DELIVERY"

    if any(marker in haystack for marker in ("customs", "held", "not delivered", "pending delivery")):
        return "EXCEPTION"

    if any(
        marker in haystack
        for marker in (
            "receive item at office of exchange",
            "receive item at location",
            "send item to domestic location",
            "insert item into bag",
            "return item from customs",
            "receive item from customer",
        )
    ):
        return "IN_TRANSIT"

    return None
