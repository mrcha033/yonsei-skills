# Field lineage

The official Yonsei shuttle client module
`https://underwood1.yonsei.ac.kr/ui/contents/sch/shtl/shtlrm/shtlrm0020.clx.js`
declares `remndSeat`, `resveWaitPcnt`, `resveYn`, and `resveWaitYn`.

The runtime uses those observations conservatively. It does not call the
reservation, waitlist, cancellation, or print endpoints.
