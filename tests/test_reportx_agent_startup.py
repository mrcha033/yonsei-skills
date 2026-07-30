from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT = (
    ROOT
    / "plugins"
    / "yonsei-certificate-assistant"
    / "skills"
    / "yonsei-certificate-assistant"
    / "scripts"
    / "reportx_mac_agent.py"
)


def free_port() -> int:
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


class ReportXAgentStartupTests(unittest.TestCase):
    def test_local_agent_health_and_status(self) -> None:
        port = free_port()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(AGENT),
                    "--dir",
                    str(root),
                    "--port",
                    str(port),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                deadline = time.monotonic() + 12
                token = ""
                while time.monotonic() < deadline:
                    token_path = root / "agent.token"
                    if token_path.is_file():
                        token = token_path.read_text(encoding="utf-8").strip()
                    if token:
                        request = urllib.request.Request(
                            f"http://127.0.0.1:{port}/health",
                            headers={"X-Agent-Token": token},
                        )
                        try:
                            opener = urllib.request.build_opener(
                                urllib.request.ProxyHandler({})
                            )
                            with opener.open(
                                request,
                                timeout=1,
                            ) as response:
                                health = json.loads(
                                    response.read().decode("utf-8")
                                )
                        except OSError:
                            time.sleep(0.1)
                            continue
                        self.assertTrue(health["ok"])
                        self.assertEqual("reportx-local", health["agent"])
                        return
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                stderr = process.stderr.read() if process.stderr else ""
                self.fail(f"agent did not become healthy: {stderr}")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                if process.stderr is not None:
                    process.stderr.close()
