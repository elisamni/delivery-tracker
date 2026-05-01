from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from playwright.sync_api import Page

from delivery_tracker.adapters.base import (
    TrackingError,
    TrackingEvent,
    TrackingNotFoundError,
    TrackingResult,
    TrackingUnavailableError,
)
from delivery_tracker.adapters.playwright_base import PlaywrightCarrierAdapter
from delivery_tracker.config import get_settings

logger = logging.getLogger(__name__)


class CyprusPostAdapter(PlaywrightCarrierAdapter):
    carrier_name = "cyprus_post"

    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()

    def _open_tracking_page(self, page: Page, tracking_number: str) -> None:
        logger.info("Cyprus Post adapter opening page %s for %s", self.settings.cyprus_post_tracking_url, tracking_number)
        page.goto(self.settings.cyprus_post_tracking_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2_000)
        self._raise_if_service_unavailable(page)
        field = page.locator("#track-n-trace-form input[name='code']").first
        if not field.count():
            raise TrackingError("Cyprus Post tracking form input[name='code'] is not available on the page")

        field.wait_for(state="visible")
        logger.info("Cyprus Post adapter found visible tracking input for %s", tracking_number)
        field.fill(tracking_number)

        action = page.locator("#track-n-trace-form button[type='submit']").first
        if not action.count():
            raise TrackingError("Cyprus Post tracking form submit button is not available on the page")

        logger.info("Cyprus Post adapter submitting tracking form for %s", tracking_number)
        action.click()
        page.wait_for_load_state("networkidle")
        self._raise_if_service_unavailable(page)

    def _parse_result(self, page: Page, tracking_number: str) -> TrackingResult:
        self._raise_if_service_unavailable(page)
        text = page.locator("body").inner_text()
        if re.search(r"not found|no result|invalid|there is no tracking information", text, re.IGNORECASE):
            raise TrackingNotFoundError(f"Cyprus Post does not know tracking number {tracking_number}")

        rows = page.locator(".panel-body .table-responsive table.table tbody tr")
        row_count = rows.count()
        logger.info("Cyprus Post adapter found %s result row(s) for %s", row_count, tracking_number)
        if row_count == 0:
            raise TrackingNotFoundError(f"Cyprus Post result table did not render for {tracking_number}")

        events: list[TrackingEvent] = []
        for index in range(row_count):
            row = rows.nth(index)
            cells = row.locator("td")
            values = [cells.nth(cell_index).inner_text().strip() for cell_index in range(cells.count())]
            if len(values) < 4:
                continue

            event_time = self._parse_event_time(values[0])
            country = values[1] if len(values) > 1 else ""
            location = values[2] if len(values) > 2 else ""
            status = values[3] if len(values) > 3 else ""
            next_office = values[4] if len(values) > 4 else ""
            extra_information = values[5] if len(values) > 5 else ""
            description_parts = [part for part in (country, next_office, extra_information) if part]

            logger.info(
                "Cyprus Post row %s for %s: time=%s location=%s status=%s next_office=%s extra=%s",
                index,
                tracking_number,
                values[0],
                location,
                status,
                next_office,
                extra_information,
            )

            if status:
                event = TrackingEvent(
                    status_raw=status,
                    timestamp=event_time or datetime.now(timezone.utc),
                    location=location or None,
                    description=" | ".join(description_parts) if description_parts else None,
                )
                events.append(event)

        if not events:
            raise TrackingNotFoundError(f"Cyprus Post result table did not expose tracking events for {tracking_number}")

        current_event = events[-1]
        pickup_code_match = re.search(r"(?:PIN|Code)[:\s]+([A-Z0-9-]{4,12})", text, re.IGNORECASE)

        return TrackingResult(
            tracking_number=tracking_number,
            carrier=self.carrier_name,
            status_raw=current_event.status_raw,
            events=events,
            pickup_location_url=None,
            pickup_code=pickup_code_match.group(1) if pickup_code_match else None,
            metadata={"latest_event_date": current_event.timestamp.isoformat()},
        )

    @staticmethod
    def _raise_if_service_unavailable(page: Page) -> None:
        title = page.title()
        text = page.locator("body").inner_text()
        if re.search(r"service currently unavailable|service unavailable|track and trace .* not be possible", title, re.IGNORECASE):
            raise TrackingUnavailableError("Cyprus Post Track & Trace website is currently unavailable")
        if re.search(r"service currently unavailable|service unavailable|track and trace .* not be possible", text, re.IGNORECASE):
            raise TrackingUnavailableError("Cyprus Post Track & Trace website is currently unavailable")

    @staticmethod
    def _parse_event_time(value: str) -> datetime | None:
        value = value.strip()
        for pattern in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(value, pattern)
            except ValueError:
                continue
        return None
