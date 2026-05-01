from __future__ import annotations

import logging
import random
import time
from abc import abstractmethod

from playwright.sync_api import Browser, Page, sync_playwright

from delivery_tracker.adapters.base import (
    CarrierAdapter,
    TrackingError,
    TrackingNotFoundError,
    TrackingResult,
    TrackingUnavailableError,
)
from delivery_tracker.config import get_settings

logger = logging.getLogger(__name__)


class PlaywrightCarrierAdapter(CarrierAdapter):
    def __init__(self) -> None:
        self.settings = get_settings()

    def track(self, tracking_number: str) -> TrackingResult:
        retries = self.settings.playwright_max_retries
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                return self._track_once(tracking_number)
            except TrackingNotFoundError:
                raise
            except TrackingUnavailableError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "Playwright adapter %s failed on attempt %s/%s for %s: %s",
                    self.carrier_name,
                    attempt,
                    retries,
                    tracking_number,
                    exc,
                )
                time.sleep(self._random_delay())

        if last_error and self._looks_like_service_unavailable(last_error):
            raise TrackingUnavailableError(
                f"{self.carrier_name} tracking service is temporarily unavailable: {last_error}"
            ) from last_error

        raise TrackingError(f"{self.carrier_name} tracking failed after retries: {last_error}") from last_error

    def _track_once(self, tracking_number: str) -> TrackingResult:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=self.settings.playwright_headless)
            try:
                context = browser.new_context(
                    user_agent=self.settings.playwright_user_agent,
                    locale=self.settings.playwright_locale,
                )
                page = context.new_page()
                page.set_default_timeout(self.settings.playwright_timeout_ms)
                self._open_tracking_page(page, tracking_number)
                time.sleep(self._random_delay())
                return self._parse_result(page, tracking_number)
            finally:
                self._close_browser(browser)

    def _close_browser(self, browser: Browser) -> None:
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            logger.exception("Unable to close Playwright browser cleanly")

    def _random_delay(self) -> float:
        return random.uniform(1.2, 3.5)

    @staticmethod
    def _looks_like_service_unavailable(error: Exception) -> bool:
        message = str(error).lower()
        return any(
            marker in message
            for marker in (
                "err_connection_closed",
                "err_connection_reset",
                "err_socket_not_connected",
                "service unavailable",
                "service currently unavailable",
            )
        )

    @abstractmethod
    def _open_tracking_page(self, page: Page, tracking_number: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def _parse_result(self, page: Page, tracking_number: str) -> TrackingResult:
        raise NotImplementedError
