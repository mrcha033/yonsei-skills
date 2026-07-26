# Yonsei Skills

Independently installable Codex and Claude Code plugins for authorized Yonsei University workflows.

Every marketplace entry is self-contained. Installing `yonsei-yri`, for example, does not require a portal, common, VPN, or LearnUs plugin. Shared resolver code is maintained under `packages/` and vendored into each plugin by the distribution script.

## Initial plugins

- `learnus-course-copilot`: password-prompted, memory-only LearnUs headless session and course analysis
- `yonsei-certificate-assistant`: valid electronic- and paper-original certificate paths
- `yonsei-notice-monitor`: official university and Sinchon IT notices
- `yonsei-academic-copilot`: read-only academic information inspection
- `yonsei-course-registration`: course lookup and schedule planning; submission disabled in v0.1
- `yonsei-attendance-copilot`: read-only attendance review
- `yonsei-shuttle-booking`: confirmation-gated shuttle reservations
- `yonsei-space-reservation`: confirmation-gated space requests
- `yonsei-yri`: YRI diagnostics and confirmation-gated writes
- `yonsei-rms`: RMS diagnostics and confirmation-gated writes
- `yonsei-erp`: ERP diagnostics and confirmation-gated writes
- `yonsei-groupware`: groupware diagnostics and confirmation-gated external actions

The first release uses browser SSO for every service except LearnUs. It never accepts a Yonsei password in chat. The VPN adapter is intentionally not packaged while its underlying client is being repaired; each service probes its official HTTPS endpoint directly first.

## Local installation

```bash
codex plugin marketplace add /Users/mrcha033/Documents/Projects/yonsei-skills
codex plugin add yonsei-notice-monitor@yonsei-skills
```

Install only the plugin needed for the task and start a new Codex task afterward.

For Claude Code:

```bash
claude plugin marketplace add /Users/mrcha033/Documents/Projects/yonsei-skills
claude plugin install yonsei-notice-monitor@yonsei-skills
```

## Development

Regenerate manifests and vendor the shared runtime:

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
