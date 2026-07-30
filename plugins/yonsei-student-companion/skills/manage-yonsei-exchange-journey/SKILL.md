---
name: manage-yonsei-exchange-journey
description: Track a Yonsei exchange student's journey from eligibility and application through nomination, host documents, departure, study abroad, credit recognition, return, and final reporting. Use when a student asks what exchange step or deadline comes next.
---

# Manage Yonsei Exchange Journey

Keep one current exchange checklist across Yonsei, the host institution, and
the student's travel timeline.

## Workflow

1. Follow `$connect-yonsei-session` and read the visible Underwood or official
   exchange application state. Use current official notices for dates and
   requirements.
2. Identify the student's route and current stage: eligibility, Yonsei
   application, nomination or placement, host application, documents, travel
   preparation, study abroad, credit recognition, return, or final report.
3. Record each official deadline, state, required document, responsible
   institution, and source. Mark host-university items separately from Yonsei
   items.
4. Build the next-action view:

   ```bash
   python3 "$SKILL_DIR/scripts/track_exchange_journey.py" --input "<temporary-json>"
   ```

5. Show the current stage, next deadline, missing documents, and later stages.
6. When the student asks to submit a Yonsei form, upload a document, or accept a
   placement, prepare it in the official browser, show the final effect, ask
   for confirmation, act once, and verify the updated state.

## Boundaries

- Never present a host-university deadline as a Yonsei deadline or vice versa.
- Treat visa, immigration, insurance, and travel rules as current-source tasks.
- Never submit, accept, decline, or withdraw without immediate confirmation.
