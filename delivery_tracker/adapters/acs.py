from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from playwright.sync_api import Page

from delivery_tracker.adapters.base import TrackingError, TrackingEvent, TrackingNotFoundError, TrackingResult, TrackingUnavailableError
from delivery_tracker.adapters.playwright_base import PlaywrightCarrierAdapter
from delivery_tracker.config import get_settings
from delivery_tracker.services.pickup_locations import resolve_pickup_location_url

logger = logging.getLogger(__name__)


class ACSAdapter(PlaywrightCarrierAdapter):
    carrier_name = "acs"

    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()

    def track(self, tracking_number: str) -> TrackingResult:
        logger.info("ACS adapter started for %s", tracking_number)
        try:
            result = super().track(tracking_number)
            logger.info(
                "ACS adapter resolved %s with status_raw=%s pickup_code=%s metadata=%s",
                tracking_number,
                result.status_raw,
                result.pickup_code,
                result.metadata,
            )
            return result
        except TrackingNotFoundError:
            logger.warning("ACS adapter reported tracking number %s as not found", tracking_number)
            raise
        except TrackingUnavailableError:
            logger.warning("ACS adapter reported tracking number %s as temporarily unavailable", tracking_number)
            raise
        except TrackingError:
            logger.warning("ACS adapter raised a tracking error for %s", tracking_number)
            raise
        except Exception as exc:  # noqa: BLE001
            raise TrackingError(f"ACS tracking failed: {exc}") from exc

    def _open_tracking_page(self, page: Page, tracking_number: str) -> None:
        logger.info("ACS adapter opening page %s for %s", self.settings.acs_tracking_url, tracking_number)
        page.goto(self.settings.acs_tracking_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2_000)
        self._dismiss_overlays(page)
        self._raise_if_service_unavailable(page)

        locator = page.locator("input[name='trackingNumbers']").first
        count = page.locator("input[name='trackingNumbers']").count()
        logger.info("ACS adapter found %s tracking input(s) for %s", count, tracking_number)
        if not locator.count():
            raise TrackingUnavailableError("ACS tracking form is not available on the page")
        locator.fill(tracking_number)
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        logger.info("ACS adapter filled tracking number %s into ACS form", tracking_number)
        payload = self._submit_search_and_capture_payload(page, tracking_number)
        setattr(page, "_acs_search_payload", payload)
        logger.info("ACS adapter submitted ACS search form for %s", tracking_number)
        self._wait_for_result_table(page, tracking_number)
        self._raise_if_service_unavailable(page)

    def _parse_result(self, page: Page, tracking_number: str) -> TrackingResult:
        history_rows = self._extract_status_history_rows(page)
        payload = getattr(page, "_acs_search_payload", None)
        if not history_rows and payload:
            history_rows = self._extract_status_history_rows_from_payload(payload)
            logger.info(
                "ACS adapter fell back to captured search payload for %s; extracted_rows=%s",
                tracking_number,
                len(history_rows),
            )
        if not history_rows:
            raise TrackingUnavailableError(f"ACS page did not expose ACS result data for {tracking_number}")

        status_line = history_rows[-1]["status"]
        latest_timestamp = history_rows[-1]["timestamp"]
        logger.info(
            "ACS adapter extracted %s history row(s); latest_status=%s latest_timestamp=%s for %s",
            len(history_rows),
            status_line,
            latest_timestamp.isoformat() if latest_timestamp else None,
            tracking_number,
        )

        details_text = " | ".join(
            value
            for row in history_rows
            for value in (row.get("information"),)
            if value and value != "-"
        )
        pickup_code_match = re.search(r"(?:delivery\s+pin|pin|pickup code)[:\s]+([A-Z0-9-]{4,12})", details_text, re.IGNORECASE)
        pickup_link_match = re.search(r"https?://[^\s]+", details_text, re.IGNORECASE)
        location_hint = ""
        if payload:
            destination_description = str(payload.get("destinationDescription", "")).strip()
            location_hint = destination_description
            if destination_description:
                details_text = " | ".join(part for part in (details_text, destination_description) if part)
            pickup_link_match = pickup_link_match or re.search(r"https?://[^\s]+", details_text, re.IGNORECASE)

        pickup_location_url = pickup_link_match.group(0) if pickup_link_match else None
        if not pickup_location_url and payload:
            pickup_location_url = self._resolve_pickup_location_from_payload(payload, status_line)
        if not pickup_location_url and location_hint:
            pickup_location_url = resolve_pickup_location_url(self.carrier_name, f"arrived at acs {location_hint}")

        events = [
            TrackingEvent(
                status_raw=row["status"],
                timestamp=row["timestamp"] or datetime.now(timezone.utc),
                description=row.get("information"),
            )
            for row in history_rows
        ]

        return TrackingResult(
            tracking_number=tracking_number,
            carrier=self.carrier_name,
            status_raw=status_line,
            events=events,
            pickup_code=pickup_code_match.group(1) if pickup_code_match else None,
            pickup_location_url=pickup_location_url,
        )

    @staticmethod
    def _raise_if_service_unavailable(page: Page) -> None:
        title = page.title()
        text = page.locator("body").inner_text()
        if re.search(r"service unavailable|temporarily unavailable|access denied|too many requests", title, re.IGNORECASE):
            raise TrackingUnavailableError("ACS tracking website is currently unavailable")
        if re.search(r"service unavailable|temporarily unavailable|access denied|too many requests", text, re.IGNORECASE):
            raise TrackingUnavailableError("ACS tracking website is currently unavailable")

    @staticmethod
    def _dismiss_overlays(page: Page) -> None:
        page.evaluate(
            """
            () => {
                const cookieBtn = document.querySelector('#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll');
                if (cookieBtn) cookieBtn.click();
                const dialog = document.querySelector('#CybotCookiebotDialog');
                if (dialog) dialog.remove();
                const chat = document.querySelector('#aseto-chat-widget');
                if (chat) chat.remove();
            }
            """
        )
        page.wait_for_timeout(500)

    @staticmethod
    def _submit_search_and_capture_payload(page: Page, tracking_number: str) -> dict[str, Any] | None:
        action = page.get_by_role("button", name="Search").first
        try:
            with page.expect_response(
                lambda response: f"/api/parcels/search/{tracking_number}" in response.url and response.status == 200,
                timeout=20_000,
            ) as response_info:
                if action.count():
                    action.click()
                else:
                    page.evaluate(
                        """
                        () => {
                            const btn = Array.from(document.querySelectorAll('button')).find(
                                el => (el.textContent || '').includes('Search')
                            );
                            if (btn) btn.click();
                        }
                        """
                    )
            response = response_info.value
            payload = response.json()
            items = payload.get("items") or []
            logger.info(
                "ACS adapter captured search payload for %s; status=%s items=%s",
                tracking_number,
                response.status,
                len(items),
            )
            if not items:
                raise TrackingNotFoundError(f"ACS search payload did not contain tracking number {tracking_number}")
            return items[0]
        except TrackingNotFoundError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("ACS adapter could not capture search payload for %s: %s", tracking_number, exc)
            return None

    def _extract_status_history_rows(self, page: Page) -> list[dict[str, object]]:
        rows = page.locator(".table-wrapper table.compact tbody tr")
        count = rows.count()
        logger.info("ACS adapter found %s status-history row(s) in ACS table", count)

        parsed: list[dict[str, object]] = []
        for index in range(count):
            row = rows.nth(index)
            cells = row.locator(".status-history-row")
            logger.info("ACS adapter inspecting row %s with %s status-history cell(s)", index, cells.count())
            if cells.count() < 3:
                logger.info("ACS adapter skipped row %s because it has less than 3 cells", index)
                continue

            try:
                status = cells.nth(0).locator("span").first.inner_text().strip()
            except Exception:  # noqa: BLE001
                status = ""
            try:
                date_text = cells.nth(1).locator("span").first.inner_text().strip()
            except Exception:  # noqa: BLE001
                date_text = ""
            try:
                info_text = cells.nth(2).locator("span").first.inner_text().strip()
            except Exception:  # noqa: BLE001
                info_text = ""

            logger.info(
                "ACS adapter row %s extracted status=%r date=%r info=%r",
                index,
                status,
                date_text,
                info_text,
            )
            if not status:
                logger.info("ACS adapter skipped row %s because status text is empty", index)
                continue
            parsed.append(
                {
                    "status": status,
                    "date_text": date_text,
                    "timestamp": self._parse_acs_date(date_text),
                    "information": info_text,
                }
            )
        return parsed

    def _extract_status_history_rows_from_payload(self, payload: dict[str, Any]) -> list[dict[str, object]]:
        status_history = payload.get("statusHistory") or []
        parsed: list[dict[str, object]] = []
        for index, row in enumerate(status_history):
            status = str(row.get("controlPoint", "")).strip()
            date_text = str(row.get("controlPointDate", "")).strip()
            info_text = str(row.get("info", "")).strip()
            logger.info(
                "ACS adapter payload row %s extracted status=%r date=%r info=%r",
                index,
                status,
                date_text,
                info_text,
            )
            if not status:
                continue
            parsed.append(
                {
                    "status": status,
                    "date_text": date_text,
                    "timestamp": self._parse_acs_date(date_text),
                    "information": info_text,
                }
            )
        return parsed

    def _resolve_pickup_location_from_payload(self, payload: dict[str, Any], status_line: str) -> str | None:
        if "delivered" in status_line.lower():
            return None

        destination_description = str(payload.get("destinationDescription", "")).strip()
        pickup_description = str(payload.get("pickupDescription", "")).strip()

        for location_name in (destination_description, pickup_description):
            if not location_name:
                continue
            resolved = resolve_pickup_location_url(self.carrier_name, f"arrived at acs {location_name}")
            if resolved:
                return resolved

        return None

    @staticmethod
    def _parse_acs_date(date_text: str) -> datetime | None:
        cleaned = (date_text or "").strip()
        if not cleaned or cleaned == "-":
            return None
        for pattern in ("%b %d, %Y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(cleaned, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _wait_for_result_table(self, page: Page, tracking_number: str) -> None:
        logger.info("ACS adapter waiting specifically for result table rows for %s", tracking_number)
        page.wait_for_load_state("networkidle")
        table_locator = page.locator(".table-wrapper table.compact tbody tr")

        try:
            table_locator.first.wait_for(state="visible", timeout=20_000)
        except Exception as exc:  # noqa: BLE001
            payload = getattr(page, "_acs_search_payload", None)
            if payload:
                logger.info(
                    "ACS adapter did not see result table rows for %s, but search payload is available; continuing without DOM table",
                    tracking_number,
                )
                return
            body_text = page.locator("body").inner_text()
            logger.warning(
                "ACS adapter did not see result table rows for %s within timeout; body_length=%s contains_tracking=%s",
                tracking_number,
                len(body_text),
                tracking_number.lower() in body_text.lower(),
            )
            raise TrackingUnavailableError("ACS result table did not render after search") from exc

        logger.info(
            "ACS adapter detected result table rows for %s; row_count=%s",
            tracking_number,
            table_locator.count(),
        )

    @staticmethod
    def _extract_pickup_code(status_raw: str) -> str | None:
        match = re.search(r"(?:delivery\s+pin|pin|pickup code)[:\s]+([A-Z0-9-]{4,12})", status_raw, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
