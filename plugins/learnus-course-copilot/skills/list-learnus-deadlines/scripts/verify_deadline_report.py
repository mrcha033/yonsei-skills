#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("list_deadlines.py")
SPEC = importlib.util.spec_from_file_location("list_deadlines", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    checks = 0
    fixture = (ROOT / "fixtures" / "course-deadlines.html").read_text(encoding="utf-8")
    result = MODULE.analyze(
        fixture,
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert result["status"] == "authenticated"
    checks += 1
    assert result["course_title"] == "운영체제"
    checks += 1
    assert [item["assignment"] for item in result["deadlines"]] == [
        "프로젝트 제안서",
        "논문 요약",
    ]
    checks += 1
    assert result["deadlines"][0]["deadline"] == "2026-08-03 23:59"
    assert result["deadlines"][0]["association"] == "visible_due_label"
    checks += 1
    assert result["deadlines"][1]["deadline"] == "2026년 8월 10일 오후 11:00"
    assert result["deadlines"][1]["association"] == "single_date_in_activity"
    checks += 1
    assert result["undated_assignments"] == [
        {
            "assignment": "실험 보고서",
            "url": "https://ys.learnus.org/mod/assign/view.php?id=13&token=REDACTED",
            "association": "ambiguous_dates_in_activity",
        }
    ]
    checks += 1
    assert "2026-12-31" not in json.dumps(result["deadlines"], ensure_ascii=False)
    assert "secret" not in json.dumps(result)
    checks += 1

    denied = MODULE.analyze(
        "<body class='loggedin'><h1>Course</h1>Access denied</body>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert denied["status"] == "blocked" and denied["deadlines"] == []
    checks += 1
    unsupported = MODULE.analyze(
        "<title>Plain</title>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert unsupported["status"] == "unsupported"
    checks += 1

    unrelated_sibling_date = MODULE.analyze(
        """
        <body class="loggedin"><h1>Course</h1>
          <div class="course-section">
            <li class="activity assign">
              <a href="/mod/assign/view.php?id=21">Essay</a>
            </li>
            <li class="activity feedback">강의평가 2026-12-31</li>
          </div>
        </body>
        """,
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert unrelated_sibling_date["deadlines"] == []
    assert unrelated_sibling_date["undated_assignments"] == [
        {
            "assignment": "Essay",
            "url": "https://ys.learnus.org/mod/assign/view.php?id=21",
            "association": "no_date_in_activity",
        }
    ]
    checks += 1

    generic_parent_date = MODULE.analyze(
        """
        <body class="loggedin"><h1>Course</h1>
          <div>
            <a href="/mod/assign/view.php?id=22">Essay without activity root</a>
            강의평가 2026-12-31
          </div>
        </body>
        """,
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert generic_parent_date["deadlines"] == []
    assert generic_parent_date["undated_assignments"][0]["association"] == "no_date_in_activity"
    checks += 1
    print(json.dumps({"passed": True, "checks": checks}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
