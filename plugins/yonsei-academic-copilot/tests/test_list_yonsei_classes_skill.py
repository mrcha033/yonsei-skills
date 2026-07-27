import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "list-yonsei-classes"
    / "scripts"
    / "list_classes.py"
)


def run_script(payload):
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


class ListYonseiClassesSkillTests(unittest.TestCase):
    def test_normalizes_supplied_classes_without_live_claim(self):
        result = run_script(
            {
                "captured_at": "2026-07-27T09:00:00+09:00",
                "term": "2026-1",
                "classes": [
                    {
                        "학정번호": "yca1001",
                        "분반": "01",
                        "교과목명": "글쓰기",
                        "담당교수": "홍길동",
                        "학점": "3",
                        "meetings": [
                            {
                                "day": "수",
                                "start": "10:00",
                                "end": "11:00",
                                "location": "백양관 101",
                            },
                            {
                                "day": "월",
                                "start": "10:00",
                                "end": "11:00",
                                "location": "백양관 101",
                            },
                        ],
                    }
                ],
                "student_number": "not-preserved",
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["schema"], "yonsei-academic-class-list/v1")
        self.assertEqual(output["classes"][0]["id"], "YCA1001-01")
        self.assertEqual(
            [meeting["day"] for meeting in output["classes"][0]["meetings"]],
            ["mon", "wed"],
        )
        self.assertTrue(output["complete"])
        self.assertFalse(output["provenance"]["live_system_queried"])
        self.assertNotIn("student_number", result.stdout)
        self.assertNotIn("not-preserved", result.stdout)

    def test_unparsed_schedule_text_is_preserved_but_incomplete(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "classes": [
                    {
                        "course_code": "YCA1001",
                        "title": "글쓰기",
                        "강의시간": "월1,2",
                    }
                ],
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertFalse(output["complete"])
        self.assertEqual(output["classes"][0]["schedule_text"], "월1,2")
        self.assertEqual(output["warnings"][0]["code"], "structured-meetings-missing")

    def test_duplicate_class_id_fails_closed(self):
        row = {"course_code": "YCA1001", "section": "01", "title": "글쓰기"}
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "classes": [row, row],
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "duplicate-class-id")

    def test_rejects_credentials_without_echoing_value(self):
        result = run_script(
            {
                "captured_at": "2026-07-27",
                "term": "2026-1",
                "classes": [],
                "password": "do-not-echo",
            }
        )
        self.assertEqual(result.returncode, 2)
        output = json.loads(result.stdout)
        self.assertEqual(output["error"]["code"], "credential-field-not-allowed")
        self.assertNotIn("do-not-echo", result.stdout)


if __name__ == "__main__":
    unittest.main()
