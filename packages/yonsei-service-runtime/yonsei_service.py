#!/usr/bin/env python3
"""Inspect a packaged Yonsei service catalog and probe public network reachability.

This helper deliberately does not accept credentials, mutate service state, or
connect a VPN. Authentication and user-confirmed mutations remain browser
workflows in the individual skill.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


SCHEMA = "yonsei-service-catalog/v1"
DEFAULT_TIMEOUT_SECONDS = 12.0
MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "yonsei-skills-service-probe/0.1"


class CatalogError(RuntimeError):
    """A controlled catalog or invocation error."""


class RedirectBoundaryError(RuntimeError):
    """A redirect left the allowed HTTPS Yonsei boundary."""


def is_allowed_redirect(url: str) -> bool:
    parts = urlsplit(url)
    hostname = (parts.hostname or "").lower()
    return (
        parts.scheme == "https"
        and (hostname == "yonsei.ac.kr" or hostname.endswith(".yonsei.ac.kr"))
        and parts.username is None
        and parts.password is None
    )


class HTTPSYonseiRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> urllib.request.Request | None:
        if not is_allowed_redirect(newurl):
            raise RedirectBoundaryError(
                f"Refused redirect outside the HTTPS Yonsei boundary: {redact_url(newurl)}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "references" / "services.json"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    selected = path or catalog_path()
    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"Could not load the packaged service catalog: {error}") from error
    validate_catalog(payload)
    return payload


def validate_catalog(payload: dict[str, Any]) -> None:
    if payload.get("schema") != SCHEMA:
        raise CatalogError(f"Unsupported service catalog schema: {payload.get('schema')!r}")
    services = payload.get("services")
    if not isinstance(services, dict) or not services:
        raise CatalogError("The service catalog must contain at least one service.")
    for service_id, service in services.items():
        if not isinstance(service_id, str) or not service_id:
            raise CatalogError("Every service ID must be a non-empty string.")
        if not isinstance(service, dict):
            raise CatalogError(f"Service {service_id!r} must be an object.")
        for key in ("label", "entry_url", "access", "mutation_policy", "vpn_policy"):
            if not isinstance(service.get(key), str) or not service[key]:
                raise CatalogError(f"Service {service_id!r} is missing {key!r}.")
        validate_https_url(service["entry_url"], service_id)
        for optional_url in ("direct_url", "portal_url", "portal_catalog_url"):
            if service.get(optional_url):
                validate_https_url(service[optional_url], service_id)


def validate_https_url(url: str, service_id: str) -> None:
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as error:
        raise CatalogError(f"Service {service_id!r} has an invalid port.") from error
    if (
        parts.scheme != "https"
        or not parts.hostname
        or port not in (None, 443)
        or parts.username is not None
        or parts.password is not None
    ):
        raise CatalogError(f"Service {service_id!r} must use a plain HTTPS URL.")


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))


def selected_service(catalog: dict[str, Any], service_id: str) -> dict[str, Any]:
    services = catalog["services"]
    if service_id not in services:
        options = ", ".join(sorted(services))
        raise CatalogError(f"Unknown service {service_id!r}. Available: {options}")
    return services[service_id]


def classify_status(status: int) -> str:
    if 200 <= status < 400:
        return "reachable"
    if status in (401, 403):
        return "authentication-boundary"
    if status == 404:
        return "not-found"
    if status >= 500:
        return "service-error"
    return "http-error"


def probe(service_id: str, service: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        service["entry_url"],
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        method="GET",
    )
    context = ssl.create_default_context()
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        HTTPSYonseiRedirectHandler(),
    )
    status = 0
    effective_url = service["entry_url"]
    try:
        with opener.open(request, timeout=timeout) as response:
            status = int(getattr(response, "status", response.getcode()))
            effective_url = response.geturl()
            response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as error:
        status = int(error.code)
        effective_url = error.geturl()
        error.read(MAX_RESPONSE_BYTES)
    except RedirectBoundaryError as error:
        return {
            "schema": "yonsei-service-probe/v1",
            "service": service_id,
            "label": service["label"],
            "classification": "redirect-boundary",
            "reachable_without_vpn": True,
            "vpn_requirement": "not-established",
            "error": str(error),
        }
    except (urllib.error.URLError, TimeoutError, socket.timeout, ssl.SSLError) as error:
        reason = getattr(error, "reason", error)
        return {
            "schema": "yonsei-service-probe/v1",
            "service": service_id,
            "label": service["label"],
            "classification": "network-error",
            "reachable_without_vpn": False,
            "vpn_requirement": "not-established",
            "error": type(reason).__name__,
        }
    classification = classify_status(status)
    return {
        "schema": "yonsei-service-probe/v1",
        "service": service_id,
        "label": service["label"],
        "classification": classification,
        "reachable_without_vpn": classification in {
            "reachable",
            "authentication-boundary",
        },
        "vpn_requirement": "not-established",
        "status": status,
        "effective_url": redact_url(effective_url),
    }


def print_payload(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if isinstance(payload, list):
        for item in payload:
            print(f"{item['id']}\t{item['label']}\t{item['entry_url']}")
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
            else:
                print(f"{key}: {value}")
        return
    print(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve and probe the Yonsei services packaged with this plugin."
    )
    parser.add_argument("--catalog", type=Path, help=argparse.SUPPRESS)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List packaged services.")
    list_parser.add_argument("--json", action="store_true")

    show_parser = subparsers.add_parser("show", help="Show one packaged service.")
    show_parser.add_argument("service")
    show_parser.add_argument("--json", action="store_true")

    url_parser = subparsers.add_parser("url", help="Print one service entry URL.")
    url_parser.add_argument("service")

    probe_parser = subparsers.add_parser(
        "probe",
        help="Probe direct HTTPS reachability without credentials or VPN changes.",
    )
    probe_parser.add_argument("service")
    probe_parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    probe_parser.add_argument("--json", action="store_true")

    doctor_parser = subparsers.add_parser("doctor", help="Validate the packaged catalog.")
    doctor_parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        catalog = load_catalog(args.catalog)
        if args.command == "list":
            result = [
                {"id": service_id, **service}
                for service_id, service in sorted(catalog["services"].items())
            ]
            print_payload(result, as_json=args.json)
            return 0
        if args.command == "doctor":
            result = {
                "schema": SCHEMA,
                "status": "ok",
                "services": sorted(catalog["services"]),
            }
            print_payload(result, as_json=args.json)
            return 0
        service = selected_service(catalog, args.service)
        if args.command == "show":
            print_payload({"id": args.service, **service}, as_json=args.json)
            return 0
        if args.command == "url":
            print(service["entry_url"])
            return 0
        if args.command == "probe":
            if args.timeout <= 0 or args.timeout > 60:
                raise CatalogError("Probe timeout must be greater than 0 and at most 60 seconds.")
            result = probe(args.service, service, args.timeout)
            print_payload(result, as_json=args.json)
            return 0 if result["classification"] != "network-error" else 2
        raise CatalogError(f"Unsupported command: {args.command}")
    except CatalogError as error:
        print(f"yonsei-service: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
