#!/usr/bin/env python3
"""Run Yonsei Bridge commands without requiring students to use browser menus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from yonsei_bridge.bridge import BridgeError, YonseiBridge
    from yonsei_bridge.router import INTENTS, StudentRouter
else:
    from .bridge import BridgeError, YonseiBridge
    from .router import INTENTS, StudentRouter


def configure_utf8_stdio() -> None:
    """Keep Korean command output lossless on every desktop OS."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("connect")
    student = sub.add_parser("student", help="Run one student-language Yonsei request.")
    student.add_argument("intent", choices=INTENTS)
    student.add_argument("--action", default="status")
    student.add_argument("--request", default="{}", help="JSON object with student-language details.")
    student.add_argument("--selection-id")
    student.add_argument("--confirmed", action="store_true")
    today = sub.add_parser("today")
    today.add_argument("--full", action="store_true")
    apps = sub.add_parser("applications")
    apps.add_argument("--category", default="장학")
    apps.add_argument("--application")
    sub.add_parser("mileage")
    graduation = sub.add_parser("graduation")
    graduation.add_argument("--no-teaching", action="store_true")
    shuttle = sub.add_parser("shuttle")
    shuttle.add_argument("--origin", required=True)
    shuttle.add_argument("--date", required=True)
    shuttle.add_argument("--destination")
    shuttle.add_argument("--preferred-time")
    shuttle.add_argument("--depart-after")
    shuttle.add_argument("--depart-before")
    shuttle.add_argument("--action", choices=("search", "reserve", "waitlist", "cancel"), default="search")
    shuttle.add_argument("--selection-id")
    shuttle.add_argument("--reason")
    shuttle.add_argument("--confirmed", action="store_true")
    services = sub.add_parser("service")
    services.add_argument("service", choices=("space", "dorm", "learnus", "attendance"))
    services.add_argument("--menu")
    services.add_argument("--action", default="status")
    services.add_argument(
        "--request",
        default="{}",
        help="JSON object with student-language details.",
    )
    services.add_argument("--selection-id")
    services.add_argument("--confirmed", action="store_true")
    documents = sub.add_parser("document")
    documents.add_argument("document_type")
    documents.add_argument("--issue", action="store_true")
    documents.add_argument("--output-format", choices=("pdf", "print"), default="pdf")
    documents.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()
    bridge = YonseiBridge()
    router = StudentRouter(bridge)
    try:
        if args.command == "connect":
            result = bridge.status()
        elif args.command == "student":
            request = json.loads(args.request)
            if not isinstance(request, dict):
                raise BridgeError("--request must be a JSON object.")
            result = router.run(
                intent=args.intent,
                action=args.action,
                request=request,
                selection_id=args.selection_id,
                confirmed=args.confirmed,
            )
        elif args.command == "today":
            result = bridge.today(full=args.full)
        elif args.command == "applications":
            result = bridge.academic_applications(category=args.category, application=args.application)
        elif args.command == "mileage":
            result = bridge.mileage()
        elif args.command == "graduation":
            result = bridge.graduation_teaching(include_teaching=not args.no_teaching)
        elif args.command == "shuttle":
            result = bridge.shuttle(
                origin=args.origin,
                date=args.date,
                destination=args.destination,
                preferred_time=args.preferred_time,
                depart_after=args.depart_after,
                depart_before=args.depart_before,
                action=args.action,
                selection_id=args.selection_id,
                reason=args.reason,
                confirmed=args.confirmed,
            )
        elif args.command == "service" and args.service in {"space", "dorm"}:
            request = json.loads(args.request)
            if not isinstance(request, dict):
                raise BridgeError("--request must be a JSON object.")
            result = bridge.space_dorm(
                service=args.service,
                menu=args.menu,
                action=args.action,
                request=request,
                selection_id=args.selection_id,
                confirmed=args.confirmed,
            )
        elif args.command == "service":
            result = bridge.learnus_attendance(service=args.service)
        else:
            result = bridge.documents(
                document_type=args.document_type,
                action="issue" if args.issue else "open",
                output_format=args.output_format,
                confirmed=args.confirmed,
            )
    except (BridgeError, json.JSONDecodeError) as error:
        print(json.dumps({"schema": "yonsei-bridge-error/v1", "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
