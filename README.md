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
- `yonsei-academic-copilot`
  - `list-yonsei-classes`: normalized class list from an authorized supplied snapshot
  - `summarize-yonsei-grades`: conservative 4.3-scale term summary with completeness checks
  - `check-yonsei-enrollment`: enrollment and term-registration status audit
- `yonsei-attendance-copilot`
  - `summarize-yonsei-attendance`: per-course and overall supplied-record totals
  - `find-yonsei-attendance-discrepancies`: user-review candidates without presence inference
  - `draft-yonsei-attendance-correction`: unsent correction draft and evidence checklist
- `yonsei-shuttle-booking`
  - `list-yonsei-shuttle-options`: filter official-screen snapshots using documented shuttle fields
  - `check-yonsei-shuttle-seats`: conservative seat, waitlist, sold-out, or unknown verdict
  - `diagnose-yonsei-shuttle-access`: public entry and official client-contract diagnosis
- `yonsei-space-reservation`
  - `search-yonsei-spaces`: filter a supplied room-availability snapshot
  - `check-yonsei-space-rules`: official public lead-time, duration, count, and restricted-period checks
  - `prepare-yonsei-space-request`: complete but unsent request and review checklist
- `yonsei-yri`
  - `list-yri-achievements`: normalized authorized YRI export
  - `find-missing-yri-achievements`: conservative export-to-reference reconciliation
  - `draft-yri-change`: field-level unsaved change draft
- `yonsei-rms`
  - `summarize-rms-project`: project, period, participant, and supplied-budget summary
  - `check-rms-budget`: budget arithmetic and inconsistency report
  - `check-rms-participants`: role and participation-period validation
- `yonsei-erp`
  - `list-erp-requests`: filtered supplied administrative-request status list
  - `list-erp-approvals`: supplied approval-inbox triage
  - `check-erp-payment-status`: supplied payment lifecycle audit
- `yonsei-groupware`
  - `list-groupware-approvals`: supplied approval-inbox triage
  - `search-groupware-documents`: local search over an explicit authorized export
  - `draft-groupware-message`: unsent message and recipient/attachment checklist
- `yonsei-certificate-assistant`: developed and validated separately.

The marketplace exposes every set above except LearnUs, which remains a local
alpha until its current SSO flow, authenticated DOM, and expiry recovery pass a
live authorized test.

## Evidence and release boundaries

An installable plugin is not automatically a live authenticated integration.
Academic, attendance, shuttle-seat, space-availability, YRI, RMS, ERP, and
groupware result skills process an explicit user-supplied authorized snapshot or
export and label it as such. They are useful before authenticated adapters exist,
but they do not claim current server state.

Public evidence is used where it exists:

- the current portal link map resolves distinct service keys rather than
  treating copied `main.jsp#` links as service addresses;
- the public shuttle client identifies its trip, remaining-seat, waitlist,
  reservation, and cancellation contracts;
- the public space guide defines the implemented booking rules;
- the YRI manual documents role-scoped records, Excel export, KRI checks,
  approval status, and modification requests;
- current RMS guidance documents project, participant, budget, document, and
  multi-stage approval workflows.

The durable service-by-service evidence, authenticated gaps, and write
boundaries are recorded in `docs/service-evidence-matrix.md`.

Live record retrieval remains pending authenticated, role-authorized mapping.
Reservation, cancellation, approval, payment, submission, attendance check-in,
record modification, message sending, and document sharing remain disabled.
The observed ERP SSO chain also contains an HTTPS-to-HTTP legacy redirect, so no
live credential adapter is released for ERP even though its offline snapshot
tools are installable.

No skill accepts a Yonsei password in chat. The VPN adapter is intentionally not
packaged while its underlying client is being repaired. The public front doors
for the investigated services were reachable without VPN; role-specific
post-login VPN need remains `unknown` and must be diagnosed per service rather
than inferred from SSO or a portal redirect.

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
