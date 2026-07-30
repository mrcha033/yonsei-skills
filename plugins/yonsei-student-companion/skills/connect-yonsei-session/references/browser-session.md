# Browser session rules

## Preferred session

- Prefer the student's persistent Chrome profile for reuse across tasks.
- Reuse an already open official Yonsei tab before creating another tab.
- Use the in-app browser only when it already contains the needed authenticated
  state or persistent Chrome is unavailable.
- Do not copy cookies between browsers or create a local credential store.

## Connected

Treat a service as connected only when the requested service shows authorized
content such as the student's course list, reservation history, loan list, or
academic menu. A portal page returning HTTP 200 is not enough.

## Login required

The following visible states require student action:

- Yonsei ID and password fields
- Portal Login or External Login choice
- MFA, OTP, certificate, or CAPTCHA
- an explicit session-expired message

Leave that official screen open. Ask the student to complete it once and then
resume in the same tab or browser profile.

## Separate login

Yonsei services do not all share one application session. Portal SSO can shorten
the route, but library, LearnUs, mail, student ID, and other services may still
show their own institutional login. Complete each official boundary once per
browser profile; do not promise one cookie works for every domain.

## After expiry

Repeat only the last read-only navigation or data read. Never repeat a final
reservation, application, issuance, cancellation, upload, or payment action
whose result is uncertain.
