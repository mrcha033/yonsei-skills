#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).with_name("list_materials.py")
SPEC = importlib.util.spec_from_file_location("list_materials", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def main() -> int:
    checks = 0
    fixture = (ROOT / "fixtures" / "course-materials.html").read_text(encoding="utf-8")
    result = MODULE.analyze(
        fixture,
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert result["status"] == "authenticated"
    checks += 1
    assert result["course_title"] == "운영체제"
    checks += 1
    assert [item["label"] for item in result["materials"]] == [
        "1주차 슬라이드",
        "읽기자료 폴더",
        "1주차 녹화",
    ]
    checks += 1
    assert [item["kind"] for item in result["materials"]] == ["file", "folder", "media"]
    checks += 1
    assert [item["availability"] for item in result["materials"]] == [
        "visible",
        "visible",
        "unavailable",
    ]
    checks += 1
    assert "secret" not in json.dumps(result)
    assert "attacker.example" not in json.dumps(result)
    assert "과제 1" not in json.dumps(result, ensure_ascii=False)
    checks += 1

    maintenance = MODULE.analyze(
        "<body class='loggedin'><h1>Course</h1>서비스 점검 중</body>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert maintenance["status"] == "blocked" and maintenance["materials"] == []
    checks += 1
    login = MODULE.analyze(
        "<body class='notloggedin'><input type='password'></body>",
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert login["status"] == "login_required"
    checks += 1

    unrelated_unavailable = MODULE.analyze(
        """
        <body class="loggedin"><h1>Course</h1>
          <div class="course-section">
            <li class="activity resource">
              <a href="/pluginfile.php/101/visible.pdf">Visible file</a>
            </li>
            <li class="activity vod">
              <a href="/mod/vod/view.php?id=90">Locked recording</a>
              <span>이용할 수 없음</span>
            </li>
          </div>
        </body>
        """,
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert unrelated_unavailable["materials"][0]["availability"] == "visible"
    assert unrelated_unavailable["materials"][1]["availability"] == "unavailable"
    checks += 1

    generic_parent_unavailable = MODULE.analyze(
        """
        <body class="loggedin"><h1>Course</h1>
          <div>
            <a href="/pluginfile.php/101/visible.pdf">Visible file</a>
            <span>다른 활동은 이용할 수 없음</span>
          </div>
        </body>
        """,
        "https://ys.learnus.org/course/view.php?id=101",
    )
    assert generic_parent_unavailable["materials"][0]["availability"] == "visible"
    checks += 1
    print(json.dumps({"passed": True, "checks": checks}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
