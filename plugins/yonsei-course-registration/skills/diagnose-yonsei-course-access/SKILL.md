---
name: diagnose-yonsei-course-access
description: Resolve and probe official Yonsei course-catalogue and undergraduate or graduate registration entry points without credentials or mutations. Use when diagnosing ysweb.yonsei.ac.kr or underwood1.yonsei.ac.kr reachability, stale requestTimeStr links, redirects, authentication boundaries, or unproven VPN assumptions.
---

# Diagnose Yonsei Course Access

Return one access diagnosis. Distinguish the year-round authenticated
Underwood handbook from period-limited registration entry points.

## Workflow

1. For course discovery, follow `$connect-yonsei-session` and try Underwood
   `수업 → 수강편람 → 조회` first. Report `catalog_available` only after the
   result grid returns course rows.
2. For an undergraduate or graduate registration failure, diagnose that entry
   separately. A closed registration window does not imply that the handbook
   is unavailable.
3. For unauthenticated connectivity diagnosis, resolve and probe the stable
   entry; never persist a copied `requestTimeStr` value:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" list
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe course-catalog --json
   ```

4. Report the HTTP classification, effective Yonsei host, and whether direct connectivity was established.
5. State separately whether authentication, handbook row access, registration
   period, or a VPN requirement remains unverified.

The unauthenticated probe proves only that an official UI shell is reachable.
The authenticated Underwood command is the course-row path; it is not a public
course API.

## Boundaries

- Never claim that a successful probe fetched course rows or seat counts.
- Never ask the student to capture the handbook before trying its authenticated
  direct query.
- Never request a Yonsei password or OTP.
- Diagnose authenticated network failure before considering any VPN requirement; do not launch a VPN client.
- Never submit, cancel, waitlist, poll, or modify a registration.
