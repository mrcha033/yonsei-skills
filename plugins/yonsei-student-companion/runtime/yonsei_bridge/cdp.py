#!/usr/bin/env python3
"""Small standard-library Chrome DevTools Protocol client."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any


class BridgeError(RuntimeError):
    """Controlled bridge failure."""


class CdpError(BridgeError):
    """Chrome DevTools Protocol failure."""


def bridge_home() -> Path:
    override = os.environ.get("YONSEI_BRIDGE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "YonseiSkills"
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "YonseiSkills"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "yonsei-skills"


def find_chrome() -> str:
    override = os.environ.get("YONSEI_CHROME_PATH")
    if override and Path(override).is_file():
        return override
    system = platform.system()
    candidates: list[str] = []
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    elif system == "Windows":
        roots = [
            os.environ.get("PROGRAMFILES"),
            os.environ.get("PROGRAMFILES(X86)"),
            os.environ.get("LOCALAPPDATA"),
        ]
        for root in roots:
            if root:
                candidates.extend(
                    [
                        str(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                        str(Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                    ]
                )
    else:
        for command in ("google-chrome", "google-chrome-stable", "microsoft-edge", "chromium", "chromium-browser"):
            located = shutil.which(command)
            if located:
                candidates.append(located)
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    raise BridgeError("Chrome, Edge, or Chromium was not found. Set YONSEI_CHROME_PATH.")


def _http_json(url: str, *, method: str = "GET", timeout: float = 3.0) -> Any:
    request = urllib.request.Request(url, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class WebSocket:
    """Minimal RFC 6455 client for a local DevTools endpoint."""

    def __init__(self, url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise CdpError("Only a local ws:// DevTools endpoint is allowed.")
        port = parsed.port or 80
        try:
            self.socket = socket.create_connection(
                (parsed.hostname, port),
                timeout=2,
            )
            self.socket.settimeout(0.75)
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            path = urllib.parse.urlunsplit(
                ("", "", parsed.path or "/", parsed.query, "")
            )
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {parsed.hostname}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            self.socket.sendall(request.encode("ascii"))
            response = self._read_headers()
            expected = base64.b64encode(
                hashlib.sha1(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()
                ).digest()
            ).decode()
            if (
                " 101 " not in response.splitlines()[0]
                or expected.lower() not in response.lower()
            ):
                raise CdpError(
                    "Chrome rejected the local DevTools WebSocket connection."
                )
            self.socket.settimeout(0.5)
        except CdpError:
            if hasattr(self, "socket"):
                self.socket.close()
            raise
        except OSError as error:
            if hasattr(self, "socket"):
                self.socket.close()
            raise CdpError(
                "Chrome's local browser connection was temporarily unavailable."
            ) from error
        self._send_lock = threading.Lock()

    def _read_headers(self) -> str:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self.socket.recv(4096)
            if not chunk:
                raise CdpError("DevTools WebSocket closed during handshake.")
            data.extend(chunk)
            if len(data) > 65536:
                raise CdpError("Oversized DevTools WebSocket handshake.")
        return data.decode("latin-1")

    def _read_exact(self, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = self.socket.recv(length - len(data))
            if not chunk:
                raise EOFError("DevTools WebSocket closed.")
            data.extend(chunk)
        return bytes(data)

    def send(self, payload: str, opcode: int = 1) -> None:
        data = payload.encode("utf-8")
        mask = os.urandom(4)
        first = 0x80 | opcode
        length = len(data)
        if length < 126:
            header = struct.pack("!BB", first, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", first, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", first, 0x80 | 127, length)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(data))
        with self._send_lock:
            self.socket.sendall(header + mask + masked)

    def receive(self) -> tuple[int, bytes]:
        header = self._read_exact(2)
        first, second = header
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._read_exact(8))[0]
        if second & 0x80:
            mask = self._read_exact(4)
        else:
            mask = None
        payload = self._read_exact(length)
        if mask:
            payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        return opcode, payload

    def close(self) -> None:
        try:
            self.send("", opcode=8)
        except OSError:
            pass
        self.socket.close()


class CdpConnection:
    def __init__(self, websocket_url: str) -> None:
        self.websocket = WebSocket(websocket_url)
        self._next_id = 1
        self._pending: dict[int, tuple[threading.Event, dict[str, Any]]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=4000)
        self._condition = threading.Condition()
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        fragments = bytearray()
        fragment_opcode = 1
        try:
            while not self._closed:
                try:
                    opcode, payload = self.websocket.receive()
                except socket.timeout:
                    continue
                if opcode == 8:
                    break
                if opcode == 9:
                    self.websocket.send(payload.decode("latin-1"), opcode=10)
                    continue
                if opcode in (1, 2):
                    fragments = bytearray(payload)
                    fragment_opcode = opcode
                elif opcode == 0:
                    fragments.extend(payload)
                else:
                    continue
                try:
                    message = json.loads(bytes(fragments).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if "id" in message:
                    pending = self._pending.get(int(message["id"]))
                    if pending:
                        pending[1].update(message)
                        pending[0].set()
                elif "method" in message:
                    with self._condition:
                        self._events.append(message)
                        self._condition.notify_all()
                fragments.clear()
                fragment_opcode = 1
        except (EOFError, OSError):
            pass
        finally:
            self._closed = True
            for event, response in self._pending.values():
                response["error"] = {"message": "Chrome DevTools connection closed."}
                event.set()

    def command(self, method: str, params: dict[str, Any] | None = None, timeout: float = 15.0) -> Any:
        if self._closed:
            raise CdpError("Chrome DevTools connection is closed.")
        command_id = self._next_id
        self._next_id += 1
        event = threading.Event()
        response: dict[str, Any] = {}
        self._pending[command_id] = (event, response)
        self.websocket.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
        if not event.wait(timeout):
            self._pending.pop(command_id, None)
            raise CdpError(f"Timed out waiting for {method}.")
        self._pending.pop(command_id, None)
        if "error" in response:
            raise CdpError(str(response["error"].get("message", response["error"])))
        return response.get("result")

    def event_cursor(self) -> int:
        with self._condition:
            return len(self._events)

    def events_since(self, cursor: int, methods: set[str] | None = None) -> list[dict[str, Any]]:
        with self._condition:
            events = list(self._events)
        selected = events[cursor:] if cursor <= len(events) else events
        if methods is not None:
            selected = [event for event in selected if event.get("method") in methods]
        return selected

    def close(self) -> None:
        self._closed = True
        self.websocket.close()


class ChromeRuntime:
    PORTAL_URL = "https://portal.yonsei.ac.kr/ui/index.html"

    def __init__(self) -> None:
        self.home = bridge_home()
        self.profile = self.home / "browser-profile"
        self.profile.mkdir(parents=True, exist_ok=True)
        self.process: subprocess.Popen[bytes] | None = None
        self.endpoint: str | None = None
        self.external_endpoint = os.environ.get("YONSEI_CDP_URL")

    def _external_active_endpoint(self) -> str | None:
        if not self.external_endpoint:
            return None
        parsed = urllib.parse.urlsplit(self.external_endpoint)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise BridgeError("YONSEI_CDP_URL must be a local http://127.0.0.1 endpoint.")
        endpoint = self.external_endpoint.rstrip("/")
        try:
            _http_json(f"{endpoint}/json/version", timeout=0.8)
        except OSError as error:
            raise BridgeError("The configured local browser endpoint is not available.") from error
        return endpoint

    def _active_endpoint(self) -> str | None:
        port_file = self.profile / "DevToolsActivePort"
        try:
            port = int(port_file.read_text(encoding="utf-8").splitlines()[0])
            endpoint = f"http://127.0.0.1:{port}"
            _http_json(f"{endpoint}/json/version", timeout=0.8)
            return endpoint
        except (OSError, ValueError, IndexError):
            return None

    def ensure(self, *, visible: bool = True) -> str:
        endpoint = self._external_active_endpoint()
        if endpoint:
            self.endpoint = endpoint
            return endpoint
        endpoint = self._active_endpoint()
        if endpoint:
            self.endpoint = endpoint
            return endpoint
        chrome = find_chrome()
        command = [
            chrome,
            f"--user-data-dir={self.profile}",
            "--remote-debugging-port=0",
            "--remote-allow-origins=http://127.0.0.1",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            self.PORTAL_URL,
        ]
        if not visible:
            command.insert(-1, "--headless=new")
        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            endpoint = self._active_endpoint()
            if endpoint:
                self.endpoint = endpoint
                return endpoint
            if self.process.poll() is not None:
                break
            time.sleep(0.15)
        raise BridgeError("Chrome did not expose its local automation endpoint.")

    def targets(self) -> list[dict[str, Any]]:
        endpoint = self.ensure()
        return _http_json(f"{endpoint}/json/list")

    def target_ids(self) -> set[str]:
        return {
            str(target.get("id"))
            for target in self.targets()
            if target.get("type") == "page" and target.get("id")
        }

    @staticmethod
    def _connect_target(target: dict[str, Any]) -> CdpConnection:
        last_error: CdpError | None = None
        for attempt in range(2):
            try:
                return CdpConnection(str(target["webSocketDebuggerUrl"]))
            except (CdpError, KeyError) as error:
                last_error = (
                    error
                    if isinstance(error, CdpError)
                    else CdpError(
                        "Chrome target did not expose a browser connection."
                    )
                )
                if attempt == 0:
                    time.sleep(0.15)
        assert last_error is not None
        raise last_error

    def connection_for_host(
        self,
        hostname: str,
        *,
        previous_target_ids: set[str] | None = None,
        timeout: float = 8.0,
    ) -> CdpConnection | None:
        """Attach to a same-session page opened by an official portal action."""
        previous_target_ids = previous_target_ids or set()
        deadline = time.monotonic() + timeout
        fallback: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            for target in reversed(self.targets()):
                parsed = urllib.parse.urlsplit(str(target.get("url", "")))
                if target.get("type") != "page" or parsed.hostname != hostname:
                    continue
                if str(target.get("id", "")) not in previous_target_ids:
                    try:
                        return self._connect_target(target)
                    except CdpError:
                        continue
                fallback = target
            time.sleep(0.15)
        if fallback is not None:
            try:
                return self._connect_target(fallback)
            except CdpError:
                return None
        return None

    def open(self, url: str, *, reuse_hosts: set[str] | None = None) -> CdpConnection:
        endpoint = self.ensure()
        reuse_hosts = reuse_hosts or set()
        requested_host = urllib.parse.urlsplit(url).hostname
        reusable: list[tuple[bool, dict[str, Any]]] = []
        for target in self.targets():
            parsed = urllib.parse.urlsplit(str(target.get("url", "")))
            if target.get("type") == "page" and parsed.hostname in reuse_hosts:
                reusable.append((parsed.hostname != requested_host, target))
        for _not_requested_host, target in sorted(
            reusable,
            key=lambda item: item[0],
        ):
            try:
                return self._connect_target(target)
            except CdpError:
                continue
        encoded = urllib.parse.quote(url, safe="")
        target = _http_json(f"{endpoint}/json/new?{encoded}", method="PUT")
        return self._connect_target(target)
