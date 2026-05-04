from __future__ import annotations

import logging
from datetime import datetime

from delivery_tracker.adapters import ACSAdapter, AggregatorAdapter, CyprusPostAdapter
from delivery_tracker.adapters.base import (
    CarrierAdapter,
    TrackingError,
    TrackingNotFoundError,
    TrackingResult,
    TrackingUnavailableError,
)
from delivery_tracker.adapters.detection import detect_carrier
from delivery_tracker.config import get_settings
from delivery_tracker.db import SessionLocal
from delivery_tracker.models.shipment import Shipment
from delivery_tracker.repositories.shipments import ShipmentRepository
from delivery_tracker.services.google_sheets import GoogleSheetsClient
from delivery_tracker.services.normalizer import normalize_status
from delivery_tracker.services.notifier import TelegramNotifier
from delivery_tracker.services.pickup_locations import resolve_pickup_location_url

logger = logging.getLogger(__name__)


class TrackingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.notifier = TelegramNotifier()
        self.aggregator = AggregatorAdapter()
        self.google_sheets = GoogleSheetsClient()
        self.carrier_adapters: dict[str, CarrierAdapter] = {
            "cyprus_post": CyprusPostAdapter(),
            "acs": ACSAdapter(),
        }

    def add_shipment(
        self,
        tracking_number: str,
        pickup_location_url: str | None = None,
        pickup_code: str | None = None,
        recipient_name: str | None = None,
        recipient_username: str | None = None,
    ) -> Shipment:
        carrier = detect_carrier(tracking_number)
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            existing = repo.get_by_tracking_number(tracking_number)
            if existing:
                raise ValueError(f"Shipment {tracking_number} already exists")
            return repo.create_shipment(
                tracking_number=tracking_number,
                carrier=carrier,
                pickup_location_url=pickup_location_url,
                pickup_code=pickup_code,
                recipient_name=recipient_name,
                recipient_username=recipient_username,
            )

    def run_once(self, *, send_cycle_summary: bool = True) -> None:
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            self.google_sheets.ensure_sheet_shape()
            self._sync_shipments_from_sheet(repo)
            if self.google_sheets.is_enabled():
                shipments = repo.list_active_sheet_shipments(limit=self.settings.tracker_batch_size)
            else:
                shipments = repo.list_active_shipments(limit=self.settings.tracker_batch_size)
            logger.info("Tracker cycle started. Shipments to process: %s", len(shipments))
            cycle_summary: list[dict[str, str]] = []
            for shipment in shipments:
                summary_item = self._process_shipment(repo, shipment)
                if summary_item:
                    cycle_summary.append(summary_item)
            if send_cycle_summary:
                self.notifier.send_cycle_summary(cycle_summary)

    def list_shipments(self) -> list[Shipment]:
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            return repo.list_shipments()

    def deactivate_shipment(self, tracking_number: str) -> Shipment:
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            shipment = repo.get_by_tracking_number(tracking_number)
            if shipment is None:
                raise ValueError(f"Shipment {tracking_number} not found")
            return repo.set_active(shipment, False)

    def activate_shipment(self, tracking_number: str) -> Shipment:
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            shipment = repo.get_by_tracking_number(tracking_number)
            if shipment is None:
                raise ValueError(f"Shipment {tracking_number} not found")
            return repo.set_active(shipment, True)

    def delete_shipment(self, tracking_number: str) -> None:
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            shipment = repo.get_by_tracking_number(tracking_number)
            if shipment is None:
                raise ValueError(f"Shipment {tracking_number} not found")
            repo.delete_shipment(shipment)

    def mark_ready_for_pickup(
        self,
        tracking_number: str,
        carrier: str,
        status_raw: str,
        pickup_location_url: str | None = None,
        pickup_code: str | None = None,
        recipient_name: str | None = None,
        recipient_username: str | None = None,
    ) -> Shipment:
        with SessionLocal() as session:
            repo = ShipmentRepository(session)
            resolved_pickup_location_url = pickup_location_url or resolve_pickup_location_url(carrier, status_raw)
            shipment = repo.get_by_tracking_number(tracking_number)
            if shipment is None:
                shipment = repo.create_shipment(
                    tracking_number=tracking_number,
                    carrier=carrier,
                    pickup_location_url=resolved_pickup_location_url,
                    pickup_code=pickup_code,
                    recipient_name=recipient_name,
                    recipient_username=recipient_username,
                )
            else:
                shipment.carrier = carrier
                shipment.pickup_location_url = resolved_pickup_location_url or shipment.pickup_location_url
                shipment.pickup_code = pickup_code or shipment.pickup_code
                shipment.recipient_name = recipient_name or shipment.recipient_name
                shipment.recipient_username = recipient_username or shipment.recipient_username

            normalized = normalize_status(status_raw)
            repo.add_status_history(shipment, status_raw, normalized)
            repo.update_status(shipment, status_raw, normalized)
            logger.info(
                "Shipment %s manually updated to %s (%s)",
                tracking_number,
                normalized,
                status_raw,
            )
            self.notifier.send_status_update(shipment, normalized)
            self._maybe_send_pickup_notification(repo, shipment, normalized)
            self._update_sheet_from_shipment(shipment, sync_state="manual_update")
            return shipment

    def _process_shipment(self, repo: ShipmentRepository, shipment: Shipment) -> dict[str, str]:
        row_number = getattr(shipment, "_sheet_row_number", None)
        try:
            result = self._track_with_fallback(shipment.tracking_number, shipment.carrier)
        except TrackingNotFoundError as exc:
            logger.warning("Tracking number %s not found: %s", shipment.tracking_number, exc)
            repo.touch_checked_at(shipment)
            self._update_sheet_error(row_number, "not_found", str(exc))
            return {
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "status": "NOT_FOUND",
            }
        except TrackingUnavailableError as exc:
            logger.warning("Tracking temporarily unavailable for %s: %s", shipment.tracking_number, exc)
            repo.touch_checked_at(shipment)
            self._update_sheet_error(row_number, "unavailable", str(exc))
            return {
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "status": "UNAVAILABLE",
            }
        except TrackingError as exc:
            logger.exception("Unable to track %s: %s", shipment.tracking_number, exc)
            repo.touch_checked_at(shipment)
            self._update_sheet_error(row_number, "error", str(exc))
            return {
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "status": "ERROR",
            }

        normalized = normalize_status(result.status_raw)
        shipment.carrier = result.carrier or shipment.carrier
        shipment.pickup_location_url = (
            result.pickup_location_url
            or resolve_pickup_location_url(shipment.carrier, result.status_raw)
            or shipment.pickup_location_url
        )
        shipment.pickup_code = result.pickup_code or shipment.pickup_code
        previous_status = shipment.last_status
        latest_event_timestamp = self._extract_latest_event_timestamp(result)

        if normalized != previous_status:
            repo.add_status_history(shipment, result.status_raw, normalized, timestamp=latest_event_timestamp)
            repo.update_status(shipment, result.status_raw, normalized)
            logger.info(
                "Status changed for %s: %s -> %s (%s)",
                shipment.tracking_number,
                previous_status,
                normalized,
                result.status_raw,
            )
            self.notifier.send_status_update(shipment, normalized)
        else:
            shipment.last_checked_at = result.fetched_at
            repo.touch_checked_at(shipment)
            logger.info("No status change for %s, still %s", shipment.tracking_number, normalized)

        self._maybe_send_pickup_notification(repo, shipment, normalized)
        self._update_sheet_from_shipment(shipment, sync_state="ok")
        return {
            "tracking_number": shipment.tracking_number,
            "carrier": shipment.carrier,
            "status": normalized,
        }

    def _track_with_fallback(self, tracking_number: str, detected_carrier: str) -> TrackingResult:
        if self.aggregator.is_enabled():
            try:
                logger.info("Trying aggregator for %s", tracking_number)
                result = self.aggregator.track(tracking_number)
                if detected_carrier != "unknown":
                    result.carrier = detected_carrier
                return result
            except TrackingError as exc:
                logger.warning("Aggregator failed for %s: %s", tracking_number, exc)
        else:
            logger.info("Aggregator disabled for %s because AGGREGATOR_API_KEY is empty", tracking_number)

        fallback_order = [detected_carrier] if detected_carrier != "unknown" else ["cyprus_post", "acs"]
        logger.info(
            "Fallback order for %s resolved to %s (detected_carrier=%s)",
            tracking_number,
            fallback_order,
            detected_carrier,
        )
        if detected_carrier == "unknown":
            logger.info("Carrier unknown for %s, probing all fallback adapters", tracking_number)

        unavailable_errors: list[str] = []
        for carrier_name in fallback_order:
            adapter = self.carrier_adapters.get(carrier_name)
            if not adapter:
                continue
            logger.info("Trying %s adapter for %s", carrier_name, tracking_number)
            try:
                return adapter.track(tracking_number)
            except TrackingNotFoundError:
                raise
            except TrackingUnavailableError as exc:
                unavailable_errors.append(f"{carrier_name}: {exc}")
                logger.warning("%s adapter unavailable for %s: %s", carrier_name, tracking_number, exc)
            except TrackingError as exc:
                logger.warning("%s adapter failed for %s: %s", carrier_name, tracking_number, exc)

        if unavailable_errors:
            logger.warning(
                "All fallback adapters for %s ended as unavailable. Errors: %s",
                tracking_number,
                unavailable_errors,
            )
            raise TrackingUnavailableError("; ".join(unavailable_errors))

        logger.warning("No fallback adapter returned a result for %s", tracking_number)
        raise TrackingNotFoundError(f"No adapter succeeded for {tracking_number}")

    def _maybe_send_pickup_notification(self, repo: ShipmentRepository, shipment: Shipment, normalized: str) -> None:
        if normalized != "READY_FOR_PICKUP":
            return
        if shipment.pickup_notified:
            return
        if not shipment.recipient_name or not shipment.recipient_username or not shipment.pickup_location_url:
            logger.warning(
                "Shipment %s is ready for pickup but recipient metadata is incomplete; skipping personal message",
                shipment.tracking_number,
            )
            return

        self.notifier.send_pickup_ready(shipment)
        repo.mark_pickup_notified(shipment)
        logger.info("Pickup notification sent for %s", shipment.tracking_number)

    @staticmethod
    def _extract_latest_event_timestamp(result: TrackingResult) -> datetime | None:
        if not result.events:
            return None
        return result.events[-1].timestamp

    def _sync_shipments_from_sheet(self, repo: ShipmentRepository) -> None:
        records = self.google_sheets.list_shipments()
        active_row_numbers = {record.row_number for record in records}

        for record in records:
            shipment = repo.get_by_google_sheet_row_number(record.row_number)
            if shipment is None:
                shipment = repo.get_by_tracking_number(record.tracking_number)

            if shipment is None:
                shipment = repo.create_shipment(
                    tracking_number=record.tracking_number,
                    carrier=record.carrier or detect_carrier(record.tracking_number),
                    pickup_location_url=record.pickup_location_url,
                    pickup_code=record.pickup_code,
                    recipient_name=record.recipient_name,
                    recipient_username=record.recipient_username,
                )
                logger.info("Imported shipment %s from Google Sheet", record.tracking_number)
            else:
                shipment.tracking_number = record.tracking_number
                shipment.carrier = record.carrier or shipment.carrier
                shipment.pickup_location_url = record.pickup_location_url or shipment.pickup_location_url
                shipment.pickup_code = record.pickup_code or shipment.pickup_code
                shipment.recipient_name = record.recipient_name or shipment.recipient_name
                shipment.recipient_username = record.recipient_username or shipment.recipient_username
            shipment.google_sheet_row_number = record.row_number
            shipment.is_active = record.active
            repo.save_shipment(shipment)
            setattr(shipment, "_sheet_row_number", record.row_number)

        for shipment in repo.list_sheet_linked_shipments():
            if shipment.google_sheet_row_number not in active_row_numbers:
                shipment.is_active = False
                repo.save_shipment(shipment)

    def _update_sheet_from_shipment(self, shipment: Shipment, *, sync_state: str) -> None:
        row_number = getattr(shipment, "_sheet_row_number", None)
        if row_number is None:
            return
        self.google_sheets.update_status(
            row_number,
            carrier=shipment.carrier,
            last_status=shipment.last_status,
            last_status_raw=shipment.last_status_raw,
            last_checked_at=shipment.last_checked_at,
            pickup_location_url=shipment.pickup_location_url,
            pickup_code=shipment.pickup_code,
            pickup_notified=shipment.pickup_notified,
            sync_state=sync_state,
        )

    def _update_sheet_error(self, row_number: int | None, sync_state: str, error_message: str) -> None:
        if row_number is None:
            return
        self.google_sheets.update_error(row_number, sync_state=sync_state, error_message=error_message)
