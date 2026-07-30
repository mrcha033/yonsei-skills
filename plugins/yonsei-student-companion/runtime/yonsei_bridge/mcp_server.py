#!/usr/bin/env python3
"""Stdio MCP server exposing the shared Yonsei Bridge commands."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from yonsei_bridge.bridge import BridgeError, YonseiBridge
else:
    from .bridge import BridgeError, YonseiBridge


TOOLS = [
    {
        "name": "yonsei_bridge_connect",
        "description": "Open or reuse the managed Yonsei browser profile and report whether official login is ready.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "yonsei_today",
        "description": "Read the Yonsei Portal dashboard and optionally the main Underwood student states in one command.",
        "inputSchema": {
            "type": "object",
            "properties": {"full": {"type": "boolean", "default": False}},
        },
    },
    {
        "name": "yonsei_academic_applications",
        "description": "Read an Underwood academic-application category or the active scholarship application screen.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "default": "장학"},
                "application": {"type": "string"},
            },
        },
    },
    {
        "name": "yonsei_mileage_history",
        "description": "Read the authenticated Underwood mileage application history for strategic course planning.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "yonsei_graduation_teaching",
        "description": "Read the Underwood earned-credit progress and teaching-credential completion screens without triggering self-diagnosis.",
        "inputSchema": {
            "type": "object",
            "properties": {"include_teaching": {"type": "boolean", "default": True}},
        },
    },
    {
        "name": "yonsei_shuttle",
        "description": "Search, prepare, reserve, waitlist, or cancel an official Yonsei shuttle trip. Writes require confirmed=true.",
        "inputSchema": {
            "type": "object",
            "required": ["origin", "date"],
            "properties": {
                "origin": {"type": "string"},
                "date": {"type": "string"},
                "destination": {"type": "string"},
                "preferred_time": {"type": "string", "description": "Preferred HH:MM departure time."},
                "depart_after": {"type": "string"},
                "depart_before": {"type": "string"},
                "action": {"type": "string", "enum": ["search", "reserve", "waitlist", "cancel"], "default": "search"},
                "row_terms": {"type": "array", "items": {"type": "string"}},
                "reason": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "yonsei_space_dorm",
        "description": "Open and read the official space or dorm workflow, or prepare a confirmed action for the official form.",
        "inputSchema": {
            "type": "object",
            "required": ["service"],
            "properties": {
                "service": {"type": "string", "enum": ["space", "dorm"]},
                "action": {"type": "string", "default": "status"},
                "category": {"type": "string", "default": "기숙사"},
                "menu": {"type": "string"},
                "fields": {
                    "type": "object",
                    "additionalProperties": {"type": ["string", "number", "boolean"]},
                    "description": "Reviewed form values keyed by the exact visible or accessible field label.",
                },
                "row_terms": {"type": "array", "items": {"type": "string"}},
                "submit_button": {"type": "string"},
                "confirmed": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "yonsei_documents",
        "description": "Open the exact official certificate, teaching-practicum, or student-activity document route and prepare issuance.",
        "inputSchema": {
            "type": "object",
            "required": ["document_type"],
            "properties": {
                "document_type": {"type": "string"},
                "action": {"type": "string", "enum": ["open", "issue"], "default": "open"},
                "output_format": {"type": "string", "enum": ["pdf", "print"], "default": "pdf"},
                "confirmed": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "yonsei_learnus_attendance",
        "description": "Read the authenticated LearnUs dashboard or electronic-attendance page without submitting attendance.",
        "inputSchema": {
            "type": "object",
            "required": ["service"],
            "properties": {"service": {"type": "string", "enum": ["learnus", "attendance"]}},
        },
    },
]


class Server:
    def __init__(self, bridge: YonseiBridge | None = None) -> None:
        self.bridge = bridge or YonseiBridge()
        self.lock = threading.Lock()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "yonsei_bridge_connect": self.bridge.status,
            "yonsei_today": self.bridge.today,
            "yonsei_academic_applications": self.bridge.academic_applications,
            "yonsei_mileage_history": self.bridge.mileage,
            "yonsei_graduation_teaching": self.bridge.graduation_teaching,
            "yonsei_shuttle": self.bridge.shuttle,
            "yonsei_space_dorm": self.bridge.space_dorm,
            "yonsei_documents": self.bridge.documents,
            "yonsei_learnus_attendance": self.bridge.learnus_attendance,
        }
        if name not in handlers:
            raise BridgeError(f"Unknown tool: {name}.")
        with self.lock:
            return handlers[name](**arguments)


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def main() -> int:
    server = Server()
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in message:
            continue
        request_id = message["id"]
        method = message.get("method")
        try:
            if method == "initialize":
                response(
                    request_id,
                    {
                        "protocolVersion": message.get("params", {}).get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "yonsei-bridge", "version": "0.3.0"},
                    },
                )
            elif method == "ping":
                response(request_id, {})
            elif method == "tools/list":
                response(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = message.get("params", {})
                result = server.call(str(params.get("name", "")), params.get("arguments", {}))
                response(
                    request_id,
                    {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                        "structuredContent": result,
                        "isError": False,
                    },
                )
            else:
                response(request_id, error={"code": -32601, "message": f"Method not found: {method}"})
        except (BridgeError, TypeError, ValueError) as error:
            response(
                request_id,
                {
                    "content": [{"type": "text", "text": str(error)}],
                    "isError": True,
                },
            )
        except Exception as error:
            response(
                request_id,
                {
                    "content": [{"type": "text", "text": f"Yonsei Bridge failed: {type(error).__name__}"}],
                    "isError": True,
                },
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
