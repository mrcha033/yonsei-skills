---
name: issue-yonsei-certificate
description: Complete Yonsei internet-certificate issuance on Windows, macOS, or Linux from certificate selection and browser authentication through the platform-appropriate official ReportX or compatibility PDF path, result inspection, and optional confirmed physical printing. Use when a student asks to actually issue a Yonsei certificate end to end.
---

# Issue Yonsei Certificate

Complete the student's own issuance without collecting credentials or altering
certificate content. Use the official native free-print path on Windows and the
local compatibility-PDF path on macOS/Linux. Read
`references/cross-platform.md` before acting.

## Workflow

1. Collect certificate type, language, copies, purpose, and whether the desired
   result is a reviewed PDF or a named physical printer. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_certificate_issue.py" --input "<temporary-json>"
   ```

2. Stop unless the result is `ready`. Follow the returned `issuance_path`.
3. On Windows, run the environment check, reuse the student's persistent
   browser profile, and open the official internet-certificate page:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" doctor
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" open
   ```

   If the official ReportX listener is absent, guide the student through the
   university-provided installer in the official page. Select the exact
   certificate, ask for final confirmation, print once through the native
   ReportX window, and verify the official result. Do not start the local agent
   by default. Then stop.
4. On macOS or Linux, check the environment and prepare pinned official runtime
   assets:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" doctor
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" prepare-assets
   ```

5. Start the local compatibility agent in a continuing terminal session:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" \
     agent --allow-fetch --reserve-document-number
   ```

6. Reuse the student's persistent Yonsei browser profile and open the official
   internet-certificate page. If login is required, leave that exact page open,
   ask the student once to sign in there, and resume in the same profile. Never
   request the password in chat or inspect cookies, local storage, or saved
   passwords.
7. Select the exact certificate, language, copies, and purpose. Before clicking
   **프린터 출력**, confirm the certificate type, copies, free-print path, and
   that one verification number will be reserved.
8. Arm one originless handoff:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" arm
   ```

9. Click **프린터 출력** once within 120 seconds. Do not retry an uncertain
   document-number reservation.
10. Wait for the terminal result:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" wait-job
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" status
   ```

11. Require `server_report_rendered_pdf_unverified` or
    `server_pdf_saved_unverified`, inspect the PDF page count and visible
    certificate identity fields, and provide the local file.
12. For physical printing on macOS/Linux, recheck the PDF digest, name the
    action-time confirmation, and run the existing `print-job ... --confirm`
    command once.

## Boundaries

- Never create, edit, substitute, or forge certificate fields.
- Never call the compatibility PDF an official electronic original.
- Never automate paid electronic-certificate payment in this skill.
- Never retry a document-number reservation or an uncertain printer submission.
- A rendered PDF is the end-to-end free-print result. Institutional verification
  and submission to a third party remain separate.
