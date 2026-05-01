from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from delivery_tracker.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    from delivery_tracker.models.shipment import Shipment
    from delivery_tracker.models.status_history import StatusHistory

    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations()


def _run_sqlite_migrations() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "shipments" not in tables:
        return

    shipment_columns = {column["name"] for column in inspector.get_columns("shipments")}
    statements: list[str] = []

    if "is_active" not in shipment_columns:
        statements.append("ALTER TABLE shipments ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
    if "google_sheet_row_number" not in shipment_columns:
        statements.append("ALTER TABLE shipments ADD COLUMN google_sheet_row_number INTEGER")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
