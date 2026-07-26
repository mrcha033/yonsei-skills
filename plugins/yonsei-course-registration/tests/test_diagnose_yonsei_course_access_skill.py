import importlib.util
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "diagnose-yonsei-course-access"
    / "scripts"
    / "yonsei_service.py"
)
SPEC = importlib.util.spec_from_file_location("yonsei_course_access", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def catalog_for(url):
    return {
        "schema": MODULE.SCHEMA,
        "services": {
            "course": {
                "label": "Course",
                "entry_url": url,
                "access": "public",
                "mutation_policy": "read-only",
                "vpn_policy": "probe-direct-first",
            }
        },
    }


class DiagnoseYonseiCourseAccessSkillTests(unittest.TestCase):
    def test_catalog_rejects_non_yonsei_entry(self):
        with self.assertRaises(MODULE.CatalogError):
            MODULE.validate_catalog(catalog_for("https://example.com/course"))

    def test_redirect_rejects_nonstandard_port(self):
        self.assertFalse(
            MODULE.is_allowed_redirect(
                "https://underwood1.yonsei.ac.kr:444/course"
            )
        )
        self.assertTrue(
            MODULE.is_allowed_redirect(
                "https://underwood1.yonsei.ac.kr/course"
            )
        )


if __name__ == "__main__":
    unittest.main()
