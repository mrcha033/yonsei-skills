#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("analyze_learnus_snapshot.py")
HEADLESS_SCRIPT = Path(__file__).with_name("learnus_headless.py")


def analyze(path: Path, base: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--html", str(path), "--base-url", base],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def headless_self_test() -> dict:
    result = subprocess.run(
        [sys.executable, "-B", str(HEADLESS_SCRIPT), "self-test"],
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="learnus-test-") as temporary:
        root = Path(temporary)
        login = root / "login.html"
        login.write_text("<title>LearnUs</title><a>Portal Login</a><input type=password>", encoding="utf-8")
        assert analyze(login, "https://ys.learnus.org/login.php")["status"] == "login_required"
        course = root / "course.html"
        course.write_text(
            """
            <title>LearnUs: Systems</title><h1>Systems Research</h1>
            <a href="/pluginfile.php/1/week1.pdf?token=secret">1주차 PDF</a>
            <a href="/mod/assign/view.php?id=2">과제 1 마감 2026-08-03 23:59</a>
            <a href="/mod/vod/view.php?id=3">1주차 녹화</a>
            """,
            encoding="utf-8",
        )
        result = analyze(course, "https://ys.learnus.org/course/view.php?id=7")
        assert result["status"] == "authenticated"
        assert len(result["materials"]) == len(result["assignments"]) == len(result["videos"]) == 1
        assert "secret" not in json.dumps(result)
        assert result["assignments"][0]["visible_date"] == "2026-08-03 23:59"
    headless = headless_self_test()
    assert headless["passed"] is True
    print(json.dumps({"passed": True, "checks": 5 + int(headless["checks"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
