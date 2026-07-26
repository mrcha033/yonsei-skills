---
name: yonsei-notice-monitor
description: Find, filter, and summarize current public Yonsei University and Sinchon IT service notices from official sources with publication dates and direct links. Use for Yonsei announcements, academic schedules, service outages, account changes, security notices, RSS monitoring, or checking what changed recently.
---

# Yonsei Notice Monitor

Use official public notice sources and preserve the distinction between publication date and event date.

## Workflow

1. Validate the packaged sources:

   ```bash
   python3 "$SKILL_DIR/scripts/yonsei_service.py" doctor
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe university-notices --json
   python3 "$SKILL_DIR/scripts/yonsei_service.py" probe it-notices --json
   ```

2. Query the narrowest relevant source:
   - University notices: `https://www.yonsei.ac.kr/sc/254/subview.do`
   - University RSS: `https://www.yonsei.ac.kr/bbs/sc/58/rssList.do?row=50`
   - Sinchon IT notices: `https://yis.yonsei.ac.kr/ics/help/notice.do`
   For a bounded metadata fetch, run:

   ```bash
   python3 "$SKILL_DIR/scripts/fetch_notices.py" \
     --source all --limit 20 --json
   ```

3. Filter by the user's topic and requested date window. Open each candidate notice rather than relying on its title.
4. Return title, publisher or board, publication date, relevant event or deadline date, one-sentence relevance, and the direct official link.
5. State when no matching official notice was found. Do not substitute reposts or search-result snippets for the official page.

This skill is public and read-only. It never needs credentials or a VPN merely to access the packaged notice sources.
