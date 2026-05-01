from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from delivery_tracker.adapters.base import TrackingError, TrackingNotFoundError, TrackingResult
from delivery_tracker.config import get_settings

logger = logging.getLogger(__name__)


class BaseAggregatorClient(ABC):
    provider_name: str = "unknown"

    @abstractmethod
    def track(self, tracking_number: str) -> TrackingResult:
        raise NotImplementedError


class SeventeenTrackClient(BaseAggregatorClient):
    provider_name = "17track"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.timeout = httpx.Timeout(self.settings.aggregator_timeout_seconds)

    def track(self, tracking_number: str) -> TrackingResult:
        if not self.settings.aggregator_api_key:
            raise TrackingError("Aggregator API key is not configured")

        url = f"{self.settings.aggregator_base_url.rstrip('/')}/gettrackinfo"
        headers = {
            "17token": self.settings.aggregator_api_key,
            "Content-Type": "application/json",
        }
        payload = [{"number": tracking_number}]

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TrackingError(f"Aggregator request failed: {exc}") from exc

        body = response.json()
        logger.debug("Aggregator response for %s: %s", tracking_number, body)
        data = self._extract_first_track(body)
        if not data:
            raise TrackingNotFoundError(f"Tracking number {tracking_number} not found in aggregator")

        status_raw = (
            data.get("track_info", {})
            .get("latest_status", {})
            .get("status")
            or data.get("track_info", {}).get("latest_status", {}).get("description")
            or data.get("status")
            or "Unknown"
        )

        pickup_code = None
        pickup_location_url = None
        extra = data.get("track_info", {}).get("z1", []) or data.get("track", {}).get("z1", [])
        for item in extra:
            label = str(item.get("z", "")).lower()
            value = item.get("v")
            if "pickup" in label and "http" in str(value):
                pickup_location_url = str(value)
            if "pin" in label or "code" in label:
                pickup_code = str(value)

        return TrackingResult(
            tracking_number=tracking_number,
            carrier=data.get("carrier", self.provider_name),
            status_raw=status_raw,
            pickup_code=pickup_code,
            pickup_location_url=pickup_location_url,
            metadata={"provider": self.provider_name},
        )

    @staticmethod
    def _extract_first_track(body: dict) -> dict | None:
        if isinstance(body, list) and body:
            return body[0]
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict):
                accepted = data.get("accepted") or data.get("track_info")
                if isinstance(accepted, list) and accepted:
                    return accepted[0]
                if isinstance(accepted, dict):
                    return accepted
        return None


def build_aggregator_client() -> BaseAggregatorClient:
    settings = get_settings()
    provider = settings.aggregator_provider.strip().lower()
    if provider == "17track":
        return SeventeenTrackClient()
    raise TrackingError(f"Unsupported aggregator provider: {settings.aggregator_provider}")
