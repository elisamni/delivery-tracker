from __future__ import annotations

from datetime import datetime
from typing import Iterable

from delivery_tracker.models.shipment import Shipment


def build_status_update_message(shipment: Shipment, status: str, updated_at: datetime) -> str:
    return (
        f"Shipment: {shipment.tracking_number}\n"
        f"Carrier: {shipment.carrier}\n"
        f"Status: {status}\n"
        f"Updated: {updated_at.isoformat()}"
    )


def build_pickup_ready_message(shipment: Shipment) -> str:
    lines = [
        f"@{shipment.recipient_username}",
        "",
        f"{shipment.recipient_name}, добрый день!",
        "",
        "Нужно забрать посылку в ближайшее время:",
        "",
        f"Геолокация: {shipment.pickup_location_url}",
        "",
        f"Номер посылки: {shipment.tracking_number}",
    ]
    if shipment.pickup_code:
        lines.append(f"ПИН-код: {shipment.pickup_code}")
    return "\n".join(lines)


def build_cycle_summary_message(items: Iterable[dict[str, str]]) -> str:
    lines = ["Current tracking statuses:", ""]
    for item in items:
        lines.append(f"{item['tracking_number']} | {item['carrier']} | {item['status']}")
    return "\n".join(lines)
