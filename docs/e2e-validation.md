# End-to-end validation

Last checked: 2026-08-04

This page separates an actual official-service run from local implementation
and cross-platform checks. It contains no student name, student number,
document contents, browser cookie, or certificate file.

## Actual official-service results

| Workflow | Result | Evidence |
| --- | --- | --- |
| Certificate free-print PDF | Completed | Authenticated Portal → internet certificate → immediate issue → free printer output; one document-number reservation; durable local PDF save; digest reread; official completion acknowledgement HTTP 200 |
| Certificate typography | Completed | One A4 page, 540,885 bytes; template-used Yonsei body face embedded as `/FontFile2`; bundled title and body font files both matched their pinned hashes; no generic substitute font accepted |
| Certificate replay | Completed | Saved PDF SHA-256 `eab91545b8dda64a72d41e0c89b5cffaca2117e43ac62f53fabe1230aa80469e`; deterministic replay matched |
| Certificate 0.11.0 regression | Local checks completed | Two-page page/object-specific logo and serial bindings, full render before reservation, exact `arm_id` job tracking, cached startup, and the 55-second hot-path budget are covered without reserving another live document number |
| Portal daily read | Completed before session expiry | Portal plus available scholarships, mileage, classes, graduation, teaching, LearnUs, and attendance sources were queried through the managed browser profile |
| Underwood course handbook | Completed before session expiry | Authenticated course rows were returned outside the registration period; the unauthenticated URL was confirmed to expose only an empty application shell |
| Public notice search | Completed | Both bounded official notice feeds returned 50 current entries without partial-fetch errors; detail pages and deadline extraction were checked |

## Cross-platform and package results

| Check | Result |
| --- | --- |
| Windows/macOS/Linux action routing | Certificate PDF, Windows named physical-printer routing, shuttle, and space paths covered by the three-OS CI matrix |
| Repository tests | All 192 tests pass locally; the optional strict `pypdf` parse is skipped only when that dependency is unavailable |
| Plugin-local tests | All 14 discovered plugin test directories pass |
| Skill structure | All 52 skill folders pass the official `quick_validate.py`; all 52 UI metadata files contain a matching invocation prompt |
| Student downloads | Four deterministic archives build successfully; all 40 student workflows and both authorized Yonsei fonts are present; published checksums are verified |
| Marketplace | All 13 plugin entries validate as installable; 9 student plugins contain 40 student skills and 4 research/administration plugins contain 12 skills |

## Login-dependent acceptance still requiring a live student session

The managed browser session expired after the authenticated reads and
certificate run. The implementation now reports `login_required` instead of a
false empty or completed result. A current eligible shuttle trip and an
available space request therefore still require the student to complete the
official login screen and provide the exact trip/room, date, time, purpose, and
other required details. No guessed reservation or application was submitted.

Windows and Linux CI proves package and runtime compatibility, not a real
student-account transaction on those operating systems. A live reservation,
cancellation, space application, or physical-printer acceptance must be
reported only after the official history screen confirms it.
