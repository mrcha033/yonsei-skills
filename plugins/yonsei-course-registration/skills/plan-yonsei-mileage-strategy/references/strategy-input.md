# Mileage strategy input

Use:

- `total_mileage`: current budget shown to the student.
- `courses`: one object per desired section.
- `course_id`, `course_code`, `title`, and `credits`.
- `capacity`, `applicants`, `past_cutoff`, and `mileage_cap` when supplied.
- `importance`: integer 1–5.
- `required_for_graduation`: boolean.
- `alternatives`: course IDs that can replace the course.
- `history_as_of`: term or date attached to historical figures.
- `underwood_history`: authorized rows read from Underwood with `term`,
  `course_id` or `course_code`, `section`, `mileage`, and `successful` or
  `status`.
- Optional history detail fields: `applied_course_count`, `first_time`,
  `major_status`, `year`, `earned_credit_ratio`,
  `total_earned_credit_ratio`, and `graduation_context`.

The optimizer uses current demand and historical cutoff only as planning
signals. It reports unknown evidence explicitly and never predicts admission
as certain. Confirm current policy, quotas, and tie-break ordering on the
official registration screen for the student's term.

Personal history is evidence about this student's prior outcome, not a true
population cutoff. Show it separately from published or observed section
cutoffs. Do not turn tie-break fields into a fabricated numerical score.

Official starting points:

- current authenticated course catalogue:
  `https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=handbList&locale=ko`
- Yonsei course registration portal:
  `https://portal.yonsei.ac.kr/`

Prefer the current term's official registration guide over an older guide.
Attach a term or checked date to every historical cutoff and applicant count.
