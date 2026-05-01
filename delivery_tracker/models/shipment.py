from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from delivery_tracker.db import Base


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_number: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    carrier: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    last_status: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN")
    last_status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_location_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pickup_notified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    google_sheet_row_number: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    history = relationship("StatusHistory", back_populates="shipment", cascade="all, delete-orphan")
