---
name: yonsei-course-registration
description: Inspect Yonsei undergraduate or graduate course offerings, build schedules, and detect conflicts without submitting registrations in version 0.1. Use for course catalogue lookup, syllabus review, timetable planning, credit totals, duplicate times, prerequisites, or diagnosing ysweb.yonsei.ac.kr access.
---

# Yonsei Course Registration

Provide a planning and verification workflow. Do not click enrollment, cancellation, waitlist, or preference-submission controls in version 0.1.

## Workflow

1. Choose undergraduate, graduate, or catalogue-only mode.
2. Resolve the stable entry; never persist a copied `requestTimeStr` value:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" list
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe course-catalog --json
   ```

3. Use the official catalogue or authenticated browser to collect course code, section, title, instructor, credits, meeting times, campus, capacity status when shown, prerequisites, and source page.
4. Check exact time overlap, travel feasibility between campuses, duplicate course or section, total credits, and user-stated constraints.
5. Present a proposed schedule and unresolved assumptions. Keep live seat counts timestamped because they can change immediately.

## Boundaries

- Never automate rapid polling, seat grabbing, CAPTCHA handling, queue evasion, enrollment submission, or cancellation.
- Never request a Yonsei password or OTP in chat.
- Do not infer that a class is available from an old snapshot.
- Diagnose authenticated network failure before considering any VPN requirement; do not launch a VPN client.
