# Yonsei service evidence matrix

Checked 2026-07-30 with anonymous, read-only GET requests. No login form,
reservation, cancellation, approval, message, payment, or other mutation was
submitted.

## Portal routing

The copied portal anchors are not service URLs. The portal renders anchors with
keys such as `LK039_A` and resolves them at click time through:

- portal: `https://portal.yonsei.ac.kr/ui/index.html`
- public address map:
  `https://portal.yonsei.ac.kr/ui/thirdparty/portal/lib/js/linkAddress.js`

The authenticated portal may override the public map with role-specific link
metadata. Therefore a copied `main.jsp#` or `href="#"` is a SPA placeholder,
not evidence that services share one backend or require VPN.

The current public link lookup returned 59 entries across common, Sinchon, and
Mirae services. The student companion resolves through the live portal rather
than treating copied placeholder anchors as destinations.

| Service | Portal key | Publicly resolved entry |
| --- | --- | --- |
| Academic information | `LK001_A` | `https://underwood1.yonsei.ac.kr/passni/spLogin.jsp?locale=ko` |
| Electronic attendance | `LK010_A` | `https://ysrollbook.yonsei.ac.kr/` |
| International shuttle | `LK014_S` | `https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=shuttle` |
| Space reservation | `LK016_A` | `https://space.yonsei.ac.kr/` |
| YRI | `LK039_A` | `https://yri.yonsei.ac.kr/` |
| RMS | `LK053_A` | `https://rms2.yonsei.ac.kr/` |
| ERP | `LK008_A` | `https://infra.yonsei.ac.kr/sso/sapep_gw_prd.jsp` |
| Groupware | `LK007_A` | `https://ysgw.yonsei.ac.kr/` |

All eight public front doors responded without an active VPN during this
review. This establishes only direct front-door connectivity. Post-login
role-specific backend or IP policy remains unverified per service.

The ERP entry currently follows an HTTPS-to-HTTP legacy redirect before showing
an auto-submit page whose form action returns to HTTPS `PmSSOService`. No
credential was submitted. The offline ERP skills are installable, but a live
credential adapter remains blocked until every authentication hop is HTTPS or
the university documents a safe supported path.

## Release decisions

| Plugin | Verified evidence | Installable result scope | Still pending live acceptance | Disabled writes |
| --- | --- | --- | --- | --- |
| Student companion | Official portal page, 59-entry live link catalogue, browser-visible login boundaries, public student-service front doors | persistent browser-profile login reuse, current portal routing, read-only daily briefing | current student account across each selected downstream service | all reservations, applications, attendance, issuance, payment, and messages |
| LearnUs | Browser-visible Portal Login boundary plus headless SSO parser, memory-only optional session lifecycle, expiry and reauthentication tests | browser-first course, deadline, and material reads; optional hidden-prompt background session | current SSO flow with a student's account after install | course writes, submissions, messages, grading |
| Academic | Official portal entry, 2026 university catalog, and department-specific requirement pages | supplied class, grade and enrollment audits plus sourced graduation progress and semester planning | official portal graduation-audit comparison for each program | profile, leave/return, registration, withdrawal, grade changes |
| Attendance | SSO application `yscattend`; official student/chapel guidance | supplied attendance summary, discrepancy review, unsent correction draft | student record fields and correction-status workflow | check-in, presence attestation, record changes, correction submission |
| Certificate | Official internet-certificate flow, locally pinned ReportX runtime assets, and member-supplied YonseiB/YonseiL embedding checks | Windows native ReportX routing; macOS/Linux original title/body font mapping, one-time document-number reservation, compatibility PDF review, and optional confirmed CUPS print | authenticated issuance on each OS with a student's chosen certificate and printer | certificate-field alteration, generic-font substitution, uncertain retry, paid electronic-certificate payment |
| Shuttle | Public program `P004023`; official search, reservation, waitlist, history, cancellation operations and row fields | Windows/macOS/Linux live-browser search, stable trip selection, confirmed reservation/waitlist/cancel, official-history verification | authenticated end-to-end run on each OS with an eligible student and real trip | quota bypass, repeated uncertain write, aggressive polling |
| Space | Public user guides, login roles, application and approval stages | Windows/macOS/Linux live-browser room search, rule checks, reviewed request, confirmed submission, official-history verification | authenticated end-to-end request on each OS against a real available room | payment, approval, permit issuance, repeated uncertain write |
| YRI | Official manual, Excel export, KRI and approval workflow | authorized export listing, missing/duplicate review, unsaved field diff | current user achievements and modification-request status | register, change, delete, verify, request modification |
| RMS | Current Research Office workflow guidance | supplied project summary, budget arithmetic, participant-period checks | current project, budget, document, participant, and approval state | upload, expense, contract, travel, approve, sign |
| ERP | Official service categories, task-path examples, and observed legacy SSO downgrade | supplied request, approval, and payment-status review | safe HTTPS-only authentication path, role-specific SAP menus, personal payroll and live workflow state | submit, approve, pay, change personal or administrative data |
| Groupware | Official service catalogue and records guidance | supplied approval triage, authorized-export search, unsent message draft | current inbox, document metadata, approval lines and archives | draft submission, approve, reject, send, share, move records |

`AVAILABLE` means the packaged calculation or browser workflow is implemented
and its local decision logic is tested. It does not imply that a real
student-account write was performed during this anonymous review. Reservation,
application, and document-number writes require the student's authenticated
official screen, action-time confirmation, a single attempt, and result
verification.

Cross-platform CI runs the platform selectors and compiles the shuttle, space,
and certificate implementations on Windows, macOS, and Ubuntu. This confirms
packaging and local runtime compatibility; the live authenticated rows above
remain the user-visible acceptance step.

## Service-specific primary sources

### Academic and attendance

- Academic functions:
  `https://www.yonsei.ac.kr/sc/199/subview.do`
- Current public course catalogue:
  `https://underwood1.yonsei.ac.kr/com/lgin/SsoCtr/initExtPageWork.do?link=handbList&locale=ko`
- Catalogue client:
  `https://underwood1.yonsei.ac.kr/ui/contents/sch/sles/slessy/slessy0180.clx.js`
- Electronic attendance:
  `https://ysrollbook.yonsei.ac.kr/`

### Shuttle and space

- Shuttle client:
  `https://underwood1.yonsei.ac.kr/ui/contents/sch/shtl/shtlrm/shtlrm0020.clx.js`
- Space guide:
  `https://space.yonsei.ac.kr/ys_popform.php?mid=K00_01`
- General-public space guide:
  `https://space.yonsei.ac.kr/ys_popform.php?mid=K00_06`

### Research and administration

- YRI manual notice:
  `https://ysrnd.yonsei.ac.kr/main/noticeDetail.do?key=262&type=YRI`
- Current RMS2 employment workflow:
  `https://research.yonsei.ac.kr/research/data_manual.do?articleNo=114666&mode=view`
- Research and administration system responsibilities:
  `https://yis.yonsei.ac.kr/ics/about/organization.do`
- Groupware records guidance:
  `https://archives.yonsei.ac.kr/News_Notice/view/158`
