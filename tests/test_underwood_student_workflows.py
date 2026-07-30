import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    path = ROOT / relative
    name = "test_" + "_".join(path.parts[-4:]).replace(".", "_").replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


APPLICATIONS = load(
    "plugins/yonsei-academic-copilot/skills/track-yonsei-academic-applications/"
    "scripts/build_application_radar.py"
)
DORM = load(
    "plugins/yonsei-student-companion/skills/manage-yonsei-dorm-life/"
    "scripts/prepare_dorm_action.py"
)
SCHOLARSHIPS = load(
    "plugins/yonsei-student-companion/skills/manage-yonsei-scholarships/"
    "scripts/rank_scholarships.py"
)
EXCHANGE = load(
    "plugins/yonsei-student-companion/skills/manage-yonsei-exchange-journey/"
    "scripts/track_exchange_journey.py"
)
DOCUMENTS = load(
    "plugins/yonsei-certificate-assistant/skills/issue-yonsei-student-activity-documents/"
    "scripts/prepare_student_document.py"
)
TEACHING = load(
    "plugins/yonsei-academic-copilot/skills/manage-yonsei-teaching-credential/"
    "scripts/calculate_teaching_credential.py"
)
MILEAGE = load(
    "plugins/yonsei-course-registration/skills/plan-yonsei-mileage-strategy/"
    "scripts/plan_mileage_strategy.py"
)
SHUTTLE = load(
    "plugins/yonsei-shuttle-booking/skills/book-yonsei-shuttle/"
    "scripts/prepare_shuttle_booking.py"
)
GRADUATION = load(
    "plugins/yonsei-academic-copilot/skills/calculate-yonsei-graduation-progress/"
    "scripts/calculate_graduation_progress.py"
)


class UnderwoodStudentWorkflowTests(unittest.TestCase):
    def test_application_radar_prioritizes_near_deadline(self):
        result = APPLICATIONS.run(
            {
                "now": "2026-07-30T09:00:00+09:00",
                "applications": [
                    {
                        "name": "복수전공 신청",
                        "category": "academic",
                        "opens_at": "2026-07-29T09:00:00+09:00",
                        "closes_at": "2026-08-01T17:00:00+09:00",
                        "eligible": True,
                        "missing_items": [],
                    }
                ],
            }
        )
        self.assertEqual(result["sections"]["closing_soon"][0]["name"], "복수전공 신청")
        self.assertFalse(result["submission_performed"])

    def test_dorm_action_prepares_but_does_not_submit(self):
        result = DORM.run(
            {
                "action": "overnight",
                "campus": "International",
                "dorm": "Songdo 2",
                "date": "2026-08-01",
                "reason": "family visit",
            }
        )
        self.assertTrue(result["ready_for_confirmation"])
        self.assertFalse(result["action_performed"])

    def test_scholarship_ranking_keeps_unknown_eligibility_uncertain(self):
        result = SCHOLARSHIPS.run(
            {
                "now": "2026-07-30T09:00:00+09:00",
                "scholarships": [
                    {
                        "name": "A 장학금",
                        "deadline": "2026-08-03T17:00:00+09:00",
                        "eligible": None,
                        "missing_documents": [],
                    }
                ],
            }
        )
        self.assertEqual(result["opportunities"][0]["next_action"], "confirm-eligibility")
        self.assertFalse(result["eligibility_guaranteed"])

    def test_exchange_journey_reports_first_incomplete_stage(self):
        result = EXCHANGE.run(
            {
                "stages": [
                    {"stage": "eligibility", "status": "completed"},
                    {
                        "stage": "yonsei_application",
                        "status": "in_progress",
                        "deadline": "2026-08-10",
                    },
                ]
            }
        )
        self.assertEqual(result["current_stage"]["stage"], "yonsei_application")
        self.assertFalse(result["action_performed"])

    def test_student_document_requires_final_confirmation(self):
        result = DOCUMENTS.run(
            {
                "document_type": "education_practicum",
                "language": "ko",
                "purpose": "employment",
                "output_format": "pdf",
            }
        )
        self.assertTrue(result["ready_for_confirmation"])
        self.assertTrue(result["font_check_required"])
        self.assertFalse(result["issuance_performed"])

    def test_teaching_progress_never_triggers_official_diagnosis(self):
        result = TEACHING.run(
            {
                "requirements": [
                    {"name": "교육실습", "status": "scheduled", "deadline": "2026-09-01"}
                ]
            }
        )
        self.assertEqual(result["next_dated_action"]["name"], "교육실습")
        self.assertFalse(result["official_diagnosis_triggered"])

    def test_mileage_uses_authorized_personal_history_as_uncertain_signal(self):
        result = MILEAGE.run(
            {
                "total_mileage": 36,
                "underwood_history": [
                    {
                        "term": "2026-1",
                        "course_code": "YCA1001",
                        "mileage": 20,
                        "status": "성공",
                        "major_status": "전공",
                    }
                ],
                "courses": [
                    {
                        "course_id": "YCA1001-01",
                        "course_code": "YCA1001",
                        "mileage_cap": 36,
                        "importance": 5,
                    }
                ],
            }
        )
        item = result["recommendations"][0]
        self.assertEqual(item["cutoff_basis"], "personal-success-observation")
        self.assertEqual(item["personal_history_count"], 1)
        self.assertFalse(result["guaranteed"])

    def test_shuttle_requires_reason_and_checks_daily_limit(self):
        result = SHUTTLE.run(
            {
                "query": {
                    "origin": "신촌",
                    "destination": "국제",
                    "date": "2026-08-01",
                    "preferred_time": "09:00",
                    "reason": "수업",
                    "active_trips_on_date": 0,
                },
                "trips": [
                    {
                        "areaDivCd": "S",
                        "busCd": "B1",
                        "busNm": "1호차",
                        "stdrDt": "20260801",
                        "beginTm": "0900",
                        "endTm": "1000",
                        "thrstNm": "신촌-국제",
                        "remndSeat": 3,
                        "resveYn": True,
                        "resveWaitYn": True,
                    }
                ],
            }
        )
        self.assertTrue(result["ready_for_confirmation"])
        self.assertEqual(result["official_rules"]["change_or_cancel_until"], "20 minutes before departure")

    def test_graduation_keeps_official_progress_advisory(self):
        result = GRADUATION.run(
            {
                "profile": {
                    "campus": "Sinchon",
                    "college": "Engineering",
                    "major": "Computer Science",
                    "admission_year": "2024",
                },
                "sources": [
                    {
                        "id": "catalog",
                        "url": "https://www.yonsei.ac.kr/sc/389/subview.do",
                        "checked_on": "2026-07-30",
                    }
                ],
                "courses": [],
                "facts": {"chapel": True},
                "requirements": [
                    {
                        "id": "chapel",
                        "label": "채플",
                        "type": "fact",
                        "key": "chapel",
                        "expected": True,
                        "source_id": "catalog",
                    }
                ],
                "official_progress": [
                    {
                        "program": "first_major",
                        "requirement": 48,
                        "earned": 36,
                        "in_progress": 3,
                        "recognized": 0,
                        "substituted": 0,
                        "cross_recognized": 0,
                        "missing": 9,
                    }
                ],
            }
        )
        self.assertEqual(result["official_progress_total_remaining"], 9)
        self.assertFalse(result["official_self_diagnosis_triggered"])
        self.assertTrue(result["advisory_only"])


if __name__ == "__main__":
    unittest.main()
