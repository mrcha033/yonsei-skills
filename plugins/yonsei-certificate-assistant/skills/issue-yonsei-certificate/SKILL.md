---
name: issue-yonsei-certificate
description: Complete Yonsei 무료 인터넷즉시발급 on Windows, macOS, or Linux by selecting the certificate, choosing 프린터 출력, and saving that free-print result through a PDF virtual printer or compatible local PDF printer; optionally print the saved result physically after confirmation. Use when a student asks 증명서 무료 PDF 발급, PDF로 가상 인쇄, or to issue a Yonsei certificate end to end.
---

# Issue Yonsei Certificate

The primary outcome is the student's own **무료 인터넷즉시발급 → 프린터 출력
→ PDF 가상 인쇄** result. Do not collect credentials or alter certificate
content. For a PDF result, use the packaged ReportX-compatible local PDF
printer on Windows, macOS, and Linux because the university ReportX component
rejects ordinary PDF virtual printers. Use native ReportX on Windows only when
the student explicitly requests a named physical printer. Read
`references/cross-platform.md` before acting.

## One-pause workflow

Start the cold setup immediately, before asking questions. Keep the command
running while the student answers and, if necessary, signs in:

```bash
python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" start
```

`start` emits one `yonsei-certificate-start/v1` handoff with the official Portal
URL, validates or prepares the pinned official assets, and starts the fully
enabled local agent under `~/.cache/yonsei-certificate-assistant`. It does not
launch, focus, resize, or cover a browser window. Use **Codex Computer Use** to
reuse the student's current browser, navigate to the emitted URL, and inspect
the visible page. Do not use Orca, AppleScript, JXA, coordinate clicks, a new
CLI-launched browser, or a separate profile.

Ask one batch containing every missing user choice and the issuance
authorization:

- certificate type: enrollment, transcript, graduation,
  expected graduation, leave, or completion
- language: Korean or English
- copies: the compatibility issuance supports exactly one
- output: PDF, or a named physical printer
- transcript only: rank included or excluded; conversion included or excluded;
  when included, the currently verified portal scale is 4.5
- purpose only if the student wants it recorded; it is optional and does not
  control issuance
- unless the fully specified original prompt already commands issuance,
  authorize one document-number reservation, requested PDF export, and any
  named physical print

At the same initial pause, leave the official login screen visible and ask the
student to finish login there if needed. Never ask for a password or OTP in
chat. Runtime login state comes from the visible current browser, not from the
student filling another request field.

Build the complete request once:

```json
{
  "certificate_type": "transcript",
  "language": "en",
  "copies": 1,
  "output": "pdf",
  "include_rank": false,
  "include_conversion": true,
  "conversion_scale": "4.5",
  "login_state": "connected"
}
```

Run `prepare_certificate_issue.py` after that single reply. Its `review` is an
internal validation artifact, not another question. The `login_state` value is
set only after Computer Use sees authenticated official content. If
`missing_user_fields` is unexpectedly nonempty, the initial batch was
incomplete; collect every listed field together before issuance. A fully
specified original prompt that explicitly commands issuance is itself the
authorization. Otherwise the authorization captured in the initial batch
covers the free-print issuance, one document-number reservation, requested PDF
export, and explicitly named physical print. Never ask the student to approve
the generated review again.

With that initial authorization there are no routine questions or separate
doctor, open, arm, status, copy, or wait commands. Run one continuing command:

```bash
python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" \
  issue --request "<request-json>" \
  --output "<new-user-facing-pdf-path>" \
  --confirm
```

Read the emitted `yonsei-certificate-computer-use-handoff/v1` and perform only
those visible browser actions with Codex Computer Use. Match the certificate,
language, copies, rank, and conversion fields exactly. Reuse an exact existing
request row where possible. Click **프린터 출력** at most once. The same command
has already armed the agent and tracks only the job whose `correlation_id`
equals that exact `arm_id`; pre-click IDs are only an additional ambiguity
check. It verifies the private PDF digest and exports it without overwriting
different destination bytes.

The one-minute target is measured from the confirmed, visibly logged-in,
cached-assets hot path to a verified export. First-use asset download and
extraction are cold setup and run during the initial intake/login pause; never
cross the document-number reservation boundary before they finish.
`issue` never performs a cold download. Its single overall budget begins at
command start and is capped at 55 seconds, leaving the remainder of the minute
for digest-verified export. This is a design budget, not a claim of live timing
until a representative issuance is measured.

Require `server_report_rendered_pdf_unverified`,
`server_pdf_saved_unverified`, or a digest-backed
`server_document_reused_unverified`; inspect the PDF page count and visible
certificate identity fields, verify that the result lists the selected
`YonseiB`/`YonseiL` font hashes when those faces occur in the FP3, and require
`completion_notified: true` before calling the official print
transaction complete. The result remains a compatibility PDF with
institutional verification not performed. On Windows, an explicitly requested
named physical printer continues to use the official native ReportX path.

## Boundaries

- Never create, edit, substitute, or forge certificate fields.
- The requested result is the free-print PDF virtual-print result. Do not route
  to or charge for the separate paid electronic-certificate product.
- Never call the virtual-print PDF a paid signed electronic-certificate file.
- Never retry a document-number reservation or an uncertain printer submission.
- Never substitute AppleGothic, Nanum, or another Korean font for a live
  certificate. Stop before reservation when the bundled title/body faces are
  missing or fail their pinned hashes.
- A rendered PDF is the end-to-end free-print result. Institutional verification
  and submission to a third party remain separate.
