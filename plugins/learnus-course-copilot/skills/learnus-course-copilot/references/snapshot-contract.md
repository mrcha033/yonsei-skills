# LearnUs snapshot contract

## Input

Provide an HTML snapshot captured from the page the user is authorized to access and its base URL. Do not include cookies, request headers, local storage, or authentication tokens.

## Status

- `authenticated`: course-shaped content is present and no login marker is found.
- `login_required`: login, SSO, password, or portal-login markers are present.
- `unsupported`: neither login nor course-shaped content can be established.

## Evidence classes

- `materials`: file links, Moodle `mod/resource` links, and `pluginfile.php` resources.
- `assignments`: Moodle assignment links. A deadline is included only when visible date text is captured.
- `videos`: visible media, VOD, recording, or playlist links. A playlist URL is evidence of a reachable reference, not permission to bypass controls.
- `date_mentions`: visible date-like text. Keep it separate from an assignment unless the page associates them.

Deduplicate by normalized absolute URL. Preserve the visible label. Redact query parameters whose names contain `token`, `key`, `signature`, `auth`, or `expires`.
