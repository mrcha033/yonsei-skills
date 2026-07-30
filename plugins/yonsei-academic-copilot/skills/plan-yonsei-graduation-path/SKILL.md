---
name: plan-yonsei-graduation-path
description: Turn a Yonsei graduation-progress report and supplied future course offerings into a semester-by-semester completion plan. Use when a student asks what to take next semester, how many semesters remain, or how prerequisites and annual offerings affect graduation timing.
---

# Plan Yonsei Graduation Path

Run this only after `$calculate-yonsei-graduation-progress`.

## Workflow

1. Use the calculator's remaining requirements.
2. Collect candidate courses from the current official course catalogue or a student-supplied course list. Record credits, requirement IDs satisfied, prerequisites, and offered terms. Do not invent future offerings.
3. Record maximum credits, preferred minimum credits, planned terms, completed course codes, and optional workload preferences.
4. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/plan_graduation_path.py" --input "<temporary-json>"
   ```

5. Explain the earliest feasible plan, unscheduled requirements, prerequisite bottlenecks, and courses whose future offering is only assumed.
6. Pass the next-term candidates to `$plan-yonsei-mileage-strategy` when registration competition matters.

## Boundaries

- Treat future offerings and graduation timing as plans, not guarantees.
- Do not count a course toward a requirement unless the official rule mapping is supplied.
- Do not submit a course registration.
- Recommend department-office confirmation when exceptions, transfer credits, repeated courses, or substitutions affect the result.
