from __future__ import annotations

from delivery_tracker.adapters.aggregator_clients import BaseAggregatorClient, build_aggregator_client
from delivery_tracker.adapters.base import CarrierAdapter, TrackingResult


class AggregatorAdapter(CarrierAdapter):
    carrier_name = "aggregator"

    def __init__(self, client: BaseAggregatorClient | None = None) -> None:
        self.client = client or build_aggregator_client()

    def is_enabled(self) -> bool:
        api_key = getattr(getattr(self.client, "settings", None), "aggregator_api_key", "")
        return bool(api_key)

    def track(self, tracking_number: str) -> TrackingResult:
        return self.client.track(tracking_number)
