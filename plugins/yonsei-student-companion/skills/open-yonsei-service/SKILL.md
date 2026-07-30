---
name: open-yonsei-service
description: Find and open the correct current Yonsei Portal service from a plain-language request while preserving the student's existing browser login. Use when a student asks 어디서 해, 포털에서 찾아 줘, 바로 열어 줘, or names academic information, registration, grades, LearnUs, attendance, certificates, mail, shuttle, space, library, career, counseling, student ID, dormitory, chapel, IT help, or another Yonsei portal function.
---

# Open Yonsei Service

Route the student's words to the current official portal entry and open it in
the browser profile already used for Yonsei.

## Workflow

1. Read `references/portal-services.md`.
2. Resolve the student's phrase against the packaged student routes:

   ```bash
   python3 "$SKILL_DIR/scripts/resolve_portal_service.py" \
     "<student request>" [--campus sinchon|mirae]
   ```

3. Resolve campus only when the requested service differs between
   Sinchon/International and Mirae. Do not ask for campus when the service is
   common.
4. Start from the live portal page:

   `https://portal.yonsei.ac.kr/ui/index.html`

5. Prefer the service name rendered by the current portal over a copied
   `href="#"` or an old deep link. Portal anchors are placeholders resolved by
   the portal's current link map.
6. Reuse the current browser profile. If authentication appears, follow the
   sibling `$connect-yonsei-session` workflow and then resume this route.
7. Verify the destination by its visible service title and main function. If it
   lands on an unrelated page, maintenance notice, or credential form, report
   that state instead of claiming the service opened.
8. Stop after opening and orienting the requested screen unless the student also
   asked to search, reserve, apply, issue, or submit something.

## Boundaries

- Never route to development, private-IP, localhost, or copied SSO callback
  addresses.
- Do not infer that a service needs VPN merely because an authenticated page is
  unavailable.
- Do not submit forms or start payments just because the correct screen opened.
- Do not expose account identifiers or authentication parameters in the result.
