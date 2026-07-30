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
    from yonsei_bridge.router import StudentRouter, friendly_error
else:
    from .bridge import BridgeError, YonseiBridge
    from .router import StudentRouter, friendly_error


TOOLS = [
    {
        "name": "yonsei_bridge_connect",
        "description": "Open or reuse the managed Yonsei browser profile and report whether official login is ready.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "yonsei_student",
        "description": (
            "Use this single student-friendly tool for Yonsei daily tasks, academic applications, "
            "official course-handbook search and mileage, graduation, shuttle, spaces, dorms, "
            "documents, LearnUs, and attendance. "
            "Ask only for missing student information. For a write, show primary_result and call again "
            "with the returned selection_id and confirmed=true after the student confirms."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["intent"],
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": [
                        "today",
                        "applications",
                        "courses",
                        "graduation",
                        "shuttle",
                        "space",
                        "dorm",
                        "documents",
                        "learnus",
                        "attendance"
                    ],
                    "description": "The student's school-life goal.",
                },
                "action": {
                    "type": "string",
                    "enum": [
                        "status",
                        "search",
                        "reserve",
                        "waitlist",
                        "cancel",
                        "apply",
                        "submit",
                        "issue",
                        "print",
                        "open"
                    ],
                    "default": "status",
                },
                "request": {
                    "type": "object",
                    "description": "Student-language details; never use portal field labels or selectors.",
                    "properties": {
                        "full": {"type": "boolean"},
                        "category": {"type": "string"},
                        "application": {"type": "string"},
                        "include_teaching": {"type": "boolean"},
                        "year": {"type": "string"},
                        "semester": {"type": "string"},
                        "course_type": {"type": "string"},
                        "department": {"type": "string"},
                        "keyword": {"type": "string"},
                        "origin": {"type": "string"},
                        "destination": {"type": "string"},
                        "date": {"type": "string"},
                        "preferred_time": {"type": "string"},
                        "depart_after": {"type": "string"},
                        "depart_before": {"type": "string"},
                        "reason": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "headcount": {"type": "integer"},
                        "purpose": {"type": "string"},
                        "building": {"type": "string"},
                        "space_name": {"type": "string"},
                        "equipment": {"type": "string"},
                        "organizer": {"type": "string"},
                        "contact": {"type": "string"},
                        "campus": {"type": "string"},
                        "dorm": {"type": "string"},
                        "facility": {"type": "string"},
                        "roommate": {"type": "string"},
                        "issue": {"type": "string"},
                        "menu": {"type": "string"},
                        "document_type": {
                            "type": "string",
                            "enum": [
                                "enrollment",
                                "transcript",
                                "graduation",
                                "expected_graduation",
                                "leave",
                                "completion",
                                "education_practicum",
                                "teaching"
                            ]
                        },
                        "language": {"type": "string"},
                        "copies": {"type": "integer"},
                        "output_format": {"type": "string", "enum": ["pdf", "print"]}
                    },
                    "additionalProperties": False,
                },
                "selection_id": {
                    "type": "string",
                    "description": "Opaque candidate ID returned by an earlier search.",
                },
                "confirmed": {"type": "boolean", "default": False},
            },
        },
    },
]


class Server:
    def __init__(self, bridge: YonseiBridge | None = None) -> None:
        self.bridge = bridge or YonseiBridge()
        self.router = StudentRouter(self.bridge)
        self.lock = threading.Lock()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "yonsei_bridge_connect": self.bridge.status,
            "yonsei_student": self.router.run,
            # Kept callable for older installed skills; new clients see only the
            # single student-language router in tools/list.
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
                        "serverInfo": {"name": "yonsei-bridge", "version": "0.6.0"},
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
            friendly = friendly_error(error)
            response(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(friendly, ensure_ascii=False)}],
                    "structuredContent": friendly,
                    "isError": True,
                },
            )
        except Exception as error:
            friendly = friendly_error(error)
            response(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(friendly, ensure_ascii=False)}],
                    "structuredContent": friendly,
                    "isError": True,
                },
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
