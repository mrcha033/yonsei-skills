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

## Preferred command path

Call `yonsei_student` with `intent: "documents"` and put document type,
language, copies, and output format in `request`. Review `primary_result`, then
repeat with `action: "issue"` and `confirmed: true`. A PDF request uses the
bundled local PDF printer and authorized fonts on all three desktop platforms.

## Workflow

1. Collect certificate type, language, copies, and purpose. Default to a PDF
   virtual-print result; ask for a named physical printer only when the student
   explicitly wants paper. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_certificate_issue.py" --input "<temporary-json>"
   ```

2. Stop unless the result is `ready`. Follow the returned `issuance_path`.
3. On Windows, macOS, or Linux, run the environment check, reuse the student's
   persistent browser profile, and open the official internet-certificate page:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" doctor
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" open
   ```

4. Prepare pinned official runtime assets on every supported platform. On
   Windows, the helper first reuses a verified installed `REPORTX.exe`; if it
   is absent, install the official component once and rerun the check. Use the
   bundled, redistribution-authorized `연세제목.TTF` and
   `연세본문.TTF` files automatically. Validate their pinned hashes before any
   live request; do not ask the student to install fonts.

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" doctor
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" prepare-assets
   ```

5. Start the local PDF virtual-printer compatibility agent in a continuing
   terminal session:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" \
     agent --allow-fetch --reserve-document-number --notify-print-completion
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
    certificate identity fields, verify that the result lists the selected
    `YonseiB`/`YonseiL` font hashes when those faces occur in the FP3, and
    require `completion_notified: true` before calling the official print
    transaction complete. Then provide the local file.
12. For physical printing on macOS/Linux, recheck the PDF digest, name the
    action-time confirmation, and run the existing `print-job ... --confirm`
    command once. On Windows, an explicitly requested named physical printer
    may instead use the official native ReportX print path.

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
