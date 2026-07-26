---
name: diagnose-yonsei-course-access
description: Resolve and probe official Yonsei course-catalogue and undergraduate or graduate registration entry points without credentials or mutations. Use when diagnosing ysweb.yonsei.ac.kr or underwood1.yonsei.ac.kr reachability, stale requestTimeStr links, redirects, authentication boundaries, or unproven VPN assumptions.
---

# Diagnose Yonsei Course Access

Return one access diagnosis. Do not treat landing-page reachability as course-data access.

## Workflow

1. Choose undergraduate, graduate, or catalogue mode.
2. Resolve and probe the stable entry; never persist a copied `requestTimeStr` value:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" list
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe course-catalog --json
   ```

3. Report the HTTP classification, effective Yonsei host, and whether direct connectivity was established.
4. State separately whether authentication, catalogue-data access, or a VPN requirement remains unverified.

The packaged catalogue URL currently proves only that the official unauthenticated UI shell is reachable. It is not a verified public course-row API.

## Boundaries

- Never claim that a successful probe fetched course rows or seat counts.
- Never request a Yonsei password or OTP.
- Diagnose authenticated network failure before considering any VPN requirement; do not launch a VPN client.
- Never submit, cancel, waitlist, poll, or modify a registration.
