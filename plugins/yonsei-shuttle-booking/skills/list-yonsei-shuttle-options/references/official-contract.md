# Official shuttle row contract

Source checked 2026-07-27:

- Entry: `https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=shuttle`
- Client module: `https://underwood1.yonsei.ac.kr/ui/contents/sch/shtl/shtlrm/shtlrm0020.clx.js`

The official module identifies menu `M105077`, program `P004023`, and exposes
fields including `busCd`, `busNm`, `stdrDt`, `beginTm`, `endTm`, `thrstNm`,
`remndSeat`, `resveWaitPcnt`, `resveYn`, and `resveWaitYn`.

This reference establishes field lineage only. A user-supplied row is not live
availability, and no read result authorizes a reservation or cancellation.
