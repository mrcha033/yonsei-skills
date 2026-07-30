---
name: issue-yonsei-certificate
description: Complete the Yonsei internet-certificate free-print flow from certificate selection and browser authentication through the ReportX handoff, one-time document-number reservation, compatibility PDF rendering, result inspection, and optional confirmed physical printing on macOS. Use when a student asks to actually issue a Yonsei certificate end to end.
---

# Issue Yonsei Certificate

Complete the student's own free-print issuance without collecting credentials or
altering certificate content. This creates a local compatibility rendering; it
is not the paid signed electronic-certificate product.

## Workflow

1. Collect certificate type, language, copies, purpose, and whether the desired
   result is a reviewed PDF or a named physical printer. Run:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_certificate_issue.py" --input "<temporary-json>"
   ```

2. Stop unless the result is `ready`.
3. Run the environment check and prepare pinned official runtime assets:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" doctor
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" prepare-assets
   ```

4. Start the local compatibility agent in a continuing terminal session:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" \
     agent --allow-fetch --reserve-document-number
   ```

5. Open the official Yonsei internet-certificate page in the browser. If login
   is required, ask the student to sign in on that page. Never request the
   password in chat or inspect cookies, local storage, or saved passwords.
6. Select the exact certificate, language, copies, and purpose. Before clicking
   **프린터 출력**, confirm the certificate type, copies, free-print path, and
   that one verification number will be reserved.
7. Arm one originless handoff:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" arm
   ```

8. Click **프린터 출력** once within 120 seconds. Do not retry an uncertain
   document-number reservation.
9. Wait for the terminal result:

   ```bash
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" wait-job
   python3 "$SKILL_DIR/../yonsei-certificate-assistant/scripts/icert_print.py" status
   ```

10. Require `server_report_rendered_pdf_unverified` or
    `server_pdf_saved_unverified`, inspect the PDF page count and visible
    certificate identity fields, and provide the local file.
11. For physical printing, recheck the PDF digest, name the printer, ask for
    action-time confirmation, and run the existing `print-job ... --confirm`
    command once.

## Boundaries

- Never create, edit, substitute, or forge certificate fields.
- Never call the compatibility PDF an official electronic original.
- Never automate paid electronic-certificate payment in this skill.
- Never retry a document-number reservation or an uncertain printer submission.
- A rendered PDF is the end-to-end free-print result. Institutional verification
  and submission to a third party remain separate.
