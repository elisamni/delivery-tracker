from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from delivery_tracker.config import get_settings

logger = logging.getLogger(__name__)

SHEETS_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
DEFAULT_HEADERS = [
    "tracking_number",
    "carrier",
    "recipient_name",
    "recipient_username",
    "pickup_location_url",
    "pickup_code",
    "active",
    "last_status",
    "last_status_raw",
    "last_checked_at",
    "pickup_notified",
    "sync_state",
    "error_message",
]


@dataclass(slots=True)
class SheetShipmentRecord:
    row_number: int
    tracking_number: str
    carrier: str | None = None
    recipient_name: str | None = None
    recipient_username: str | None = None
    pickup_location_url: str | None = None
    pickup_code: str | None = None
    active: bool = True


class GoogleSheetsClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._service = None

    def is_enabled(self) -> bool:
        if not self.settings.google_sheets_enabled:
            return False
        if not self.settings.google_sheets_spreadsheet_id:
            return False
        return Path(self.settings.google_sheets_credentials_file).exists()

    def list_shipments(self) -> list[SheetShipmentRecord]:
        if not self.is_enabled():
            return []

        values = self._sheet().values().get(
            spreadsheetId=self.settings.google_sheets_spreadsheet_id,
            range=f"{self.settings.google_sheets_worksheet_name}!A1:Z",
        ).execute().get("values", [])

        if not values:
            self._ensure_headers()
            return []

        headers = [self._normalize_header(header) for header in values[0]]
        records: list[SheetShipmentRecord] = []
        for offset, row in enumerate(values[1:], start=2):
            payload = self._row_to_payload(headers, row)
            tracking_number = str(payload.get("tracking_number", "")).strip()
            if not tracking_number:
                continue

            active = str(payload.get("active", "true")).strip().lower()
            is_active = active not in {"false", "0", "no", "inactive"}
            if not is_active:
                continue

            records.append(
                SheetShipmentRecord(
                    row_number=offset,
                    tracking_number=tracking_number,
                    carrier=self._clean(payload.get("carrier")),
                    recipient_name=self._clean(payload.get("recipient_name")),
                    recipient_username=self._clean(payload.get("recipient_username")),
                    pickup_location_url=self._clean(payload.get("pickup_location_url")),
                    pickup_code=self._clean(payload.get("pickup_code")),
                    active=is_active,
                )
            )
        return records

    def ensure_sheet_shape(self) -> None:
        if not self.is_enabled():
            return
        self._ensure_headers()

    def update_status(
        self,
        row_number: int,
        *,
        carrier: str,
        last_status: str,
        last_status_raw: str | None,
        last_checked_at: datetime | None,
        pickup_location_url: str | None,
        pickup_code: str | None,
        pickup_notified: bool,
        sync_state: str,
        error_message: str | None = None,
    ) -> None:
        if not self.is_enabled():
            return

        values = [[
            carrier,
            last_status,
            last_status_raw or "",
            last_checked_at.isoformat() if last_checked_at else "",
            pickup_location_url or "",
            pickup_code or "",
            "true" if pickup_notified else "false",
            sync_state,
            error_message or "",
        ]]
        self._sheet().values().update(
            spreadsheetId=self.settings.google_sheets_spreadsheet_id,
            range=f"{self.settings.google_sheets_worksheet_name}!B{row_number}:M{row_number}",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

    def update_error(self, row_number: int, *, sync_state: str, error_message: str) -> None:
        if not self.is_enabled():
            return
        self._sheet().values().update(
            spreadsheetId=self.settings.google_sheets_spreadsheet_id,
            range=f"{self.settings.google_sheets_worksheet_name}!L{row_number}:M{row_number}",
            valueInputOption="RAW",
            body={"values": [[sync_state, error_message]]},
        ).execute()

    def _sheet(self):
        if self._service is None:
            credentials = Credentials.from_service_account_file(
                self.settings.google_sheets_credentials_file,
                scopes=SHEETS_SCOPE,
            )
            self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return self._service.spreadsheets()

    def _ensure_headers(self) -> None:
        current = self._sheet().values().get(
            spreadsheetId=self.settings.google_sheets_spreadsheet_id,
            range=f"{self.settings.google_sheets_worksheet_name}!A1:M1",
        ).execute().get("values", [])

        if current and current[0][: len(DEFAULT_HEADERS)] == DEFAULT_HEADERS:
            return

        logger.info("Initializing Google Sheet header row")
        self._sheet().values().update(
            spreadsheetId=self.settings.google_sheets_spreadsheet_id,
            range=f"{self.settings.google_sheets_worksheet_name}!A1:M1",
            valueInputOption="RAW",
            body={"values": [DEFAULT_HEADERS]},
        ).execute()

    @staticmethod
    def _normalize_header(value: str) -> str:
        return value.strip().lower()

    @staticmethod
    def _row_to_payload(headers: list[str], row: list[str]) -> dict[str, str]:
        payload: dict[str, str] = {}
        for index, header in enumerate(headers):
            payload[header] = row[index] if index < len(row) else ""
        return payload

    @staticmethod
    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None
