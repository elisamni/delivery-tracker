from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from delivery_tracker.models.shipment import Shipment
from delivery_tracker.models.status_history import StatusHistory


class ShipmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_shipments(self, limit: int | None = None) -> list[Shipment]:
        stmt = select(Shipment).order_by(Shipment.id.asc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def list_active_shipments(self, limit: int | None = None) -> list[Shipment]:
        stmt = select(Shipment).where(Shipment.is_active.is_(True)).order_by(Shipment.id.asc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def list_active_sheet_shipments(self, limit: int | None = None) -> list[Shipment]:
        stmt = (
            select(Shipment)
            .where(Shipment.is_active.is_(True), Shipment.google_sheet_row_number.is_not(None))
            .order_by(Shipment.google_sheet_row_number.asc(), Shipment.id.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def list_sheet_linked_shipments(self) -> list[Shipment]:
        stmt = select(Shipment).where(Shipment.google_sheet_row_number.is_not(None)).order_by(Shipment.google_sheet_row_number.asc())
        return list(self.session.scalars(stmt))

    def get_by_tracking_number(self, tracking_number: str) -> Shipment | None:
        stmt = select(Shipment).where(Shipment.tracking_number == tracking_number)
        return self.session.scalars(stmt).first()

    def get_by_google_sheet_row_number(self, row_number: int) -> Shipment | None:
        stmt = select(Shipment).where(Shipment.google_sheet_row_number == row_number)
        return self.session.scalars(stmt).first()

    def create_shipment(
        self,
        tracking_number: str,
        carrier: str,
        pickup_location_url: str | None = None,
        pickup_code: str | None = None,
        recipient_name: str | None = None,
        recipient_username: str | None = None,
    ) -> Shipment:
        shipment = Shipment(
            tracking_number=tracking_number,
            carrier=carrier,
            pickup_location_url=pickup_location_url,
            pickup_code=pickup_code,
            recipient_name=recipient_name,
            recipient_username=recipient_username,
        )
        self.session.add(shipment)
        self.session.commit()
        self.session.refresh(shipment)
        return shipment

    def add_status_history(
        self,
        shipment: Shipment,
        status_raw: str | None,
        status_normalized: str,
        timestamp: datetime | None = None,
    ) -> StatusHistory:
        history = StatusHistory(
            shipment_id=shipment.id,
            status_raw=status_raw,
            status_normalized=status_normalized,
            timestamp=timestamp or datetime.now(timezone.utc),
        )
        self.session.add(history)
        self.session.flush()
        return history

    def update_status(self, shipment: Shipment, status_raw: str | None, status_normalized: str) -> Shipment:
        shipment.last_status_raw = status_raw
        shipment.last_status = status_normalized
        shipment.last_checked_at = datetime.now(timezone.utc)
        self.session.add(shipment)
        self.session.commit()
        self.session.refresh(shipment)
        return shipment

    def touch_checked_at(self, shipment: Shipment) -> None:
        shipment.last_checked_at = datetime.now(timezone.utc)
        self.session.add(shipment)
        self.session.commit()

    def save_shipment(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        self.session.commit()
        self.session.refresh(shipment)
        return shipment

    def mark_pickup_notified(self, shipment: Shipment) -> Shipment:
        shipment.pickup_notified = True
        shipment.updated_at = datetime.now(timezone.utc)
        self.session.add(shipment)
        self.session.commit()
        self.session.refresh(shipment)
        return shipment

    def set_active(self, shipment: Shipment, is_active: bool) -> Shipment:
        shipment.is_active = is_active
        self.session.add(shipment)
        self.session.commit()
        self.session.refresh(shipment)
        return shipment

    def delete_shipment(self, shipment: Shipment) -> None:
        self.session.delete(shipment)
        self.session.commit()
