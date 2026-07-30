#!/usr/bin/env python3
"""Internal read-only recovery diagnosis for the official Yonsei shuttle."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ENTRY = "https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=shuttle"
MODULE = "https://underwood1.yonsei.ac.kr/ui/contents/sch/shtl/shtlrm/shtlrm0020.clx.js"
MAX_BYTES = 256 * 1024


def fetch(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "yonsei-shuttle-diagnostic/0.1"}, method="GET"
    )
    try:
        with urllib.request.urlopen(
            request, timeout=12, context=ssl.create_default_context()
        ) as response:
            body = response.read(MAX_BYTES + 1)
            return {
                "reachable": True,
                "status": response.status,
                "effective_url": response.geturl(),
                "truncated": len(body) > MAX_BYTES,
                "body": body[:MAX_BYTES].decode("utf-8", "replace"),
            }
    except urllib.error.HTTPError as exc:
        return {
            "reachable": True,
            "status": exc.code,
            "effective_url": exc.geturl(),
            "body": exc.read(MAX_BYTES).decode("utf-8", "replace"),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"reachable": False, "error": type(exc).__name__, "message": str(exc)}


def analyze(entry: dict[str, Any], module: dict[str, Any]) -> dict[str, Any]:
    body = module.get("body", "")
    endpoints = sorted(set(re.findall(r'"/sch/shtl/ShtlrmCtr/([^"]+?\.do)"', body)))
    read_endpoints = [item for item in endpoints if item.startswith("find")]
    write_endpoints = [item for item in endpoints if item.startswith("save")]
    fields = sorted(
        set(
            re.findall(
                r'name:"(areaDivCd|busCd|busNm|seatNo|stdrDt|beginTm|endTm|'
                r'thrstNm|remndSeat|resveWaitPcnt|resveYn|resveWaitYn)"',
                body,
            )
        )
    )
    direct = bool(entry.get("reachable") and module.get("reachable"))
    return {
        "schema": "yonsei-shuttle-access-diagnosis/v1",
        "direct_connectivity": direct,
        "entry": {key: value for key, value in entry.items() if key != "body"},
        "client_module": {key: value for key, value in module.items() if key != "body"},
        "observed_contract": {
            "read_endpoints": read_endpoints,
            "write_endpoints_not_invoked": write_endpoints,
            "fields": fields,
        },
        "authenticated_trip_data_access": "unverified",
        "vpn_required": None,
        "vpn_conclusion": (
            "Direct public resources were reachable; role-specific post-login VPN need remains unverified."
            if direct
            else "Direct connectivity failed; this alone does not prove a VPN is required."
        ),
        "credentials_used": False,
        "mutations_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-file", type=Path)
    args = parser.parse_args()
    entry = fetch(ENTRY) if args.module_file is None else {
        "reachable": True,
        "status": None,
        "effective_url": ENTRY,
        "offline_fixture": True,
    }
    if args.module_file is None:
        module = fetch(MODULE)
    else:
        try:
            module = {
                "reachable": True,
                "status": None,
                "effective_url": MODULE,
                "offline_fixture": True,
                "body": args.module_file.read_text(encoding="utf-8"),
            }
        except OSError as exc:
            print(json.dumps({"error": "read-failed", "message": str(exc)}), file=sys.stderr)
            return 2
    print(json.dumps(analyze(entry, module), ensure_ascii=False, indent=2))
    return 0 if entry.get("reachable") and module.get("reachable") else 1


if __name__ == "__main__":
    raise SystemExit(main())
