from __future__ import annotations

import argparse
import logging

from delivery_tracker.config import get_settings
from delivery_tracker.db import init_db
from delivery_tracker.logging_config import setup_logging
from delivery_tracker.scheduler import run_scheduler
from delivery_tracker.services.tracker import TrackingService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Multi-carrier delivery tracker with Telegram notifications")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add-shipment", help="Add a shipment to tracking")
    add_parser.add_argument("--tracking-number", required=True)
    add_parser.add_argument("--pickup-location-url")
    add_parser.add_argument("--pickup-code")
    add_parser.add_argument("--recipient-name")
    add_parser.add_argument("--recipient-username")

    subparsers.add_parser("run-once", help="Run one tracking cycle")
    subparsers.add_parser("scheduler", help="Run scheduler loop")

    test_parser = subparsers.add_parser("send-test-notification", help="Send a Telegram test message")
    test_parser.add_argument(
        "--text",
        default="Тест: бот доставки подключен и уведомления работают.",
        help="Plain-text message to send to Telegram",
    )

    ready_parser = subparsers.add_parser(
        "mark-ready-for-pickup",
        help="Manually mark a shipment as ready for pickup and send notifications",
    )
    ready_parser.add_argument("--tracking-number", required=True)
    ready_parser.add_argument("--carrier", required=True)
    ready_parser.add_argument("--status-raw", required=True)
    ready_parser.add_argument("--pickup-location-url")
    ready_parser.add_argument("--pickup-code")
    ready_parser.add_argument("--recipient-name")
    ready_parser.add_argument("--recipient-username")

    subparsers.add_parser("list-shipments", help="List all shipments in the database")

    deactivate_parser = subparsers.add_parser("deactivate-shipment", help="Deactivate a shipment")
    deactivate_parser.add_argument("--tracking-number", required=True)

    activate_parser = subparsers.add_parser("activate-shipment", help="Activate a shipment")
    activate_parser.add_argument("--tracking-number", required=True)

    delete_parser = subparsers.add_parser("delete-shipment", help="Delete a shipment")
    delete_parser.add_argument("--tracking-number", required=True)
    return parser


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_db()

    parser = build_parser()
    args = parser.parse_args()
    service = TrackingService()

    if args.command == "add-shipment":
        shipment = service.add_shipment(
            tracking_number=args.tracking_number,
            pickup_location_url=args.pickup_location_url,
            pickup_code=args.pickup_code,
            recipient_name=args.recipient_name,
            recipient_username=args.recipient_username,
        )
        logger.info("Shipment added: id=%s tracking=%s carrier=%s", shipment.id, shipment.tracking_number, shipment.carrier)
        return

    if args.command == "run-once":
        service.run_once()
        return

    if args.command == "scheduler":
        run_scheduler()
        return

    if args.command == "send-test-notification":
        service.notifier.send_text(args.text)
        logger.info("Test notification sent")
        return

    if args.command == "mark-ready-for-pickup":
        shipment = service.mark_ready_for_pickup(
            tracking_number=args.tracking_number,
            carrier=args.carrier,
            status_raw=args.status_raw,
            pickup_location_url=args.pickup_location_url,
            pickup_code=args.pickup_code,
            recipient_name=args.recipient_name,
            recipient_username=args.recipient_username,
        )
        logger.info(
            "Shipment marked ready for pickup: id=%s tracking=%s carrier=%s",
            shipment.id,
            shipment.tracking_number,
            shipment.carrier,
        )
        return

    if args.command == "list-shipments":
        shipments = service.list_shipments()
        if not shipments:
            logger.info("No shipments found")
            return
        for shipment in shipments:
            logger.info(
                "id=%s tracking=%s carrier=%s status=%s active=%s pickup_notified=%s",
                shipment.id,
                shipment.tracking_number,
                shipment.carrier,
                shipment.last_status,
                shipment.is_active,
                shipment.pickup_notified,
            )
        return

    if args.command == "deactivate-shipment":
        shipment = service.deactivate_shipment(args.tracking_number)
        logger.info("Shipment deactivated: tracking=%s active=%s", shipment.tracking_number, shipment.is_active)
        return

    if args.command == "activate-shipment":
        shipment = service.activate_shipment(args.tracking_number)
        logger.info("Shipment activated: tracking=%s active=%s", shipment.tracking_number, shipment.is_active)
        return

    if args.command == "delete-shipment":
        service.delete_shipment(args.tracking_number)
        logger.info("Shipment deleted: tracking=%s", args.tracking_number)
        return


if __name__ == "__main__":
    main()
