from __future__ import annotations

import logging

import httpx

from delivery_tracker.config import get_settings
from delivery_tracker.models.shipment import Shipment
from delivery_tracker.services.templates import (
    build_cycle_summary_message,
    build_pickup_ready_message,
    build_status_update_message,
)

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_enabled(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send_status_update(self, shipment: Shipment, status: str) -> None:
        self._send_message(build_status_update_message(shipment, status, shipment.last_checked_at))

    def send_pickup_ready(self, shipment: Shipment) -> None:
        self._send_message(build_pickup_ready_message(shipment))

    def send_text(self, text: str) -> None:
        self._send_message(text)

    def send_cycle_summary(self, items: list[dict[str, str]]) -> None:
        if not items:
            return
        self._send_message(build_cycle_summary_message(items))

    def _send_message(self, text: str) -> None:
        if not self.is_enabled():
            logger.warning("Telegram is not configured, skipping notification: %s", text)
            return

        url = (
            f"{self.settings.telegram_api_base.rstrip('/')}/bot"
            f"{self.settings.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": self.settings.telegram_chat_id,
            "text": text,
            "disable_web_page_preview": False,
        }
        with httpx.Client(timeout=15) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
