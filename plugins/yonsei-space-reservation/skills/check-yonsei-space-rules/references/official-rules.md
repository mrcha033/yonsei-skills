# Official public space rules

Sources checked 2026-07-27:

- Affiliated-user guide: `https://space.yonsei.ac.kr/ys_popform.php?mid=K00_01`
- General-public guide: `https://space.yonsei.ac.kr/ys_popform.php?mid=K00_06`
- Service entry: `https://space.yonsei.ac.kr/`

The affiliated-user guide describes this sequence: sign in, choose a date,
headcount, room, and time, wait for staff approval, pay when required, receive
approval notice, and print the permit.

Implemented deterministic checks:

- students, graduate students, staff, alumni, registered organizations, and
  general-public organizations are recognized applicant classes;
- requests must be at least one day and no more than 14 days ahead;
- time selection uses ten-minute units;
- one booking is at most four hours;
- at most two bookings are allowed in one seven-day window;
- opening weeks, exam periods, and special-event periods are unavailable;
- weekday approvals are not processed after 16:00.

The runtime requires the caller to label restricted periods instead of inventing
the academic calendar. A pass does not constitute availability or approval.
