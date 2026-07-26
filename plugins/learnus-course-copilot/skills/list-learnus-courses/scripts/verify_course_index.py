#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("list_courses.py")
SPEC = importlib.util.spec_from_file_location("list_courses", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    checks = 0
    fixture = (ROOT / "fixtures" / "dashboard.html").read_text(encoding="utf-8")
    result = MODULE.analyze(fixture, "https://ys.learnus.org/my/")
    assert result["status"] == "authenticated"
    checks += 1
    assert [item["course_id"] for item in result["courses"]] == ["101", "202"]
    checks += 1
    assert [item["name"] for item in result["courses"]] == ["운영체제", "연구방법론"]
    checks += 1
    assert "secret" not in json.dumps(result)
    checks += 1

    denied = MODULE.analyze(
        "<body class='loggedin'><main data-region='course-overview'>Access denied</main></body>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert denied["status"] == "blocked" and denied["courses"] == []
    checks += 1
    maintenance = MODULE.analyze(
        "<body class='loggedin'>서비스 점검 중</body>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert maintenance["status"] == "blocked"
    checks += 1
    unsupported = MODULE.analyze(
        "<title>Plain page</title>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert unsupported["status"] == "unsupported"
    checks += 1
    login = MODULE.analyze(
        "<body class='notloggedin'><input type='password'></body>",
        "https://ys.learnus.org/my/",
    )
    assert login["status"] == "login_required"
    checks += 1
    print(json.dumps({"passed": True, "checks": checks}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
