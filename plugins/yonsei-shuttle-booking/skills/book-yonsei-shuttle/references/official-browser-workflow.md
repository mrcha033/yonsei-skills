# Official shuttle browser workflow

Checked against the public client module on 2026-07-30.

- Entry: `https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=shuttle`
- Menu: `M105077`
- Program: `P004023`
- Search operation: `findShtlbusResveList.do`
- Reservation operation: `saveShtlbusResveList.do`
- Reservation history: `findShtlbusDtlsCanclList.do`
- Waitlist history: `findShtlbusDtlsWaitList.do`

Use the official UI rather than constructing requests. The client applies
NetFunnel and its own request token.

Transcribe these row fields:

- `areaDivCd`, `busCd`, `busNm`, `stdrDt`
- `beginTm`, `endTm`, `thrstNm`
- `remndSeat`, `resveWaitPcnt`, `resveYn`, `resveWaitYn`
- `seatNo` when verifying a completed reservation

The stable selector uses departure area, bus code, date, and start time. Re-read
those fields immediately before a reservation or cancellation.
