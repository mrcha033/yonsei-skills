# Yonsei Skills

Independently installable Codex and Claude Code plugins for authorized Yonsei University workflows. A plugin contains result-specific skills and never depends on a separate portal, common, VPN, or LearnUs plugin.

## Implemented plugin sets

- `learnus-course-copilot` (local alpha; marketplace installation disabled until live SSO and expiry recovery pass)
  - `manage-learnus-session`: hidden-terminal password prompt and memory-only reauthentication
  - `list-learnus-courses`: authorized dashboard course index
  - `list-learnus-deadlines`: visibly associated assignment deadlines
  - `list-learnus-materials`: visible files, folders, resources, and media
- `yonsei-notice-monitor`
  - `search-yonsei-notices`: current official university and Sinchon IT notices
  - `list-yonsei-notice-deadlines`: contextual date mentions from bounded notice details
  - `watch-yonsei-notices`: added and changed notices against an explicit state file
- `yonsei-course-registration`
  - `normalize-yonsei-courses`: canonicalize supplied course rows
  - `check-yonsei-schedule`: time, blocked-time, and campus-transfer conflicts
  - `audit-yonsei-course-plan`: one selected plan against explicit credit, course, campus, and time constraints
  - `build-yonsei-timetable`: ranked conflict-free schedule candidates
  - `diagnose-yonsei-course-access`: bounded official entry-point diagnosis
- `yonsei-certificate-assistant`: developed and validated separately.

The marketplace currently exposes the certificate assistant, notice tools, and course planner. LearnUs remains a local alpha until its current SSO flow, authenticated DOM, and expiry recovery pass a live authorized test. Course planning uses supplied snapshots and does not claim live catalogue rows or seat availability. Notice results are bounded by the official source windows and identify partial fetches.

## Held from installation

Academic records, attendance, shuttle, space reservation, YRI, RMS, ERP, and groupware plugins remain `NOT_AVAILABLE`. Their intended fine-grained outcomes are recorded in `contracts/skill-outcomes.json`, but they will not be published as working skills until service-specific authenticated fixtures and authorized live tests exist.

No skill accepts a Yonsei password in chat. The VPN adapter is intentionally not packaged while its underlying client is being repaired, and VPN need is not inferred from a generic portal redirect.

## Local installation

```bash
codex plugin marketplace add <path-to-cloned-yonsei-skills>
codex plugin add yonsei-notice-monitor@yonsei-skills
```

Install only the plugin needed for the task and start a new Codex task afterward.

For Claude Code:

```bash
claude plugin marketplace add <path-to-cloned-yonsei-skills>
claude plugin install yonsei-notice-monitor@yonsei-skills
```

## Development

Regenerate manifests and vendor the legacy service diagnostics:

```bash
python3 scripts/render_manifests.py
python3 scripts/sync_runtime.py
```

Run local and live-catalog validation:

```bash
python3 scripts/validate_repo.py
python3 scripts/check_portal_catalog.py
python3 -m unittest discover -s tests -v
```

Plugin manifests and skills must also pass the Codex `validate_plugin.py` and `quick_validate.py` validators before release.
