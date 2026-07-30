---
name: issue-yonsei-student-activity-documents
description: Locate and issue Yonsei student-activity, ambassador, resident-assistant, education-practicum, tuition-payment, dorm, and other campus participation records through the official browser, preserving document fonts and verifying the final file. Use when a student needs a non-transcript campus document or confirmation.
---

# Issue Yonsei Student Activity Documents

Find the correct issuing office and complete the official document flow on
Windows, macOS, or Linux.

## Workflow

1. Follow `$connect-yonsei-session` and reuse the persistent browser profile.
2. Identify the exact document, language, purpose, recipient, output type, and
   number of copies. Search the visible official Portal or Underwood menu before
   asking the student to locate it.
3. Prepare the route:

   ```bash
   python3 "$SKILL_DIR/scripts/prepare_student_document.py" --input "<temporary-json>"
   ```

4. If the document is issued by a department or activity office rather than a
   central system, show that office and required evidence. Do not substitute a
   generic enrollment certificate.
5. On the official issuance screen, show document name, language, purpose,
   recipient exposure, fee, and output format. Ask for confirmation immediately
   before issuance or payment.
6. Issue once and verify the official document name, issue date, document
   number when present, page count, and readable PDF.
7. Preserve the document's embedded fonts. For the supported ReportX
   compatibility path, reuse the bundled authorized Yonsei title and body fonts
   and verify both before handing off the PDF.

## Boundaries

- Never alter the document body, seal, number, date, or identity fields.
- Never issue or pay for the wrong purpose merely to bypass a restriction.
- If the result is ambiguous, do not consume another issuance number.
