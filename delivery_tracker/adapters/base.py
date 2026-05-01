from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone


class TrackingError(Exception):
    pass


class TrackingNotFoundError(TrackingError):
    pass


class TrackingUnavailableError(TrackingError):
    pass


@dataclass(slots=True)
class TrackingEvent:
    status_raw: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    location: str | None = None
    description: str | None = None


@dataclass(slots=True)
class TrackingResult:
    tracking_number: str
    carrier: str
    status_raw: str
    events: list[TrackingEvent] = field(default_factory=list)
    pickup_location_url: str | None = None
    pickup_code: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, str] = field(default_factory=dict)


class CarrierAdapter(ABC):
    carrier_name: str = "unknown"

    @abstractmethod
    def track(self, tracking_number: str) -> TrackingResult:
        raise NotImplementedError
