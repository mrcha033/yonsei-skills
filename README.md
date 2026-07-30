# Yonsei Skills

연세대학교 생활에서 자주 반복되는 확인·정리 작업을 자연어로 처리하는 비공식 오픈소스 플러그인 모음입니다.

> 연세대학교 공식 서비스가 아닙니다. 학교 계정 권한을 늘리거나 수강신청·출석·예약 제한을 우회하지 않습니다.

## 터미널 없이 설치

명령어를 입력하지 않아도 됩니다.

| 사용하는 앱 | 받을 파일 | 설치 방법 |
| --- | --- | --- |
| Codex 데스크톱 | [Codex용 ZIP](https://github.com/mrcha033/yonsei-skills/releases/latest/download/yonsei-codex-ui-pack.zip) | 압축을 풀고 `yonsei-skills` 폴더를 Codex에서 연 뒤 **Plugins**에서 `+` 선택 |
| Claude 웹·데스크톱 | [Claude용 ZIP](https://github.com/mrcha033/yonsei-skills/releases/latest/download/yonsei-student-life.zip) | **Customize → Skills → + → Create skill → Upload a skill**에서 ZIP 업로드 |
| `.skill` 업로드 지원 앱 | [학생생활 통합 .skill](https://github.com/mrcha033/yonsei-skills/releases/latest/download/yonsei-student-life.skill) | Skills의 업로드 화면에서 파일 선택 |

화면을 보면서 따라 하는 자세한 설명은
[`docs/download-and-install.md`](docs/download-and-install.md)에 있습니다.

셔틀·공간은 Windows, macOS, Linux에서 같은 공식 브라우저 흐름을
사용합니다. 증명서는 Windows의 공식 ReportX 출력과 macOS/Linux의
호환 PDF 경로를 자동으로 구분합니다.

`yonsei-student-companion`은 한 번 로그인한 전용 브라우저 프로필과
학생용 단일 요청 창구를 사용합니다. 오늘의 연세, 학사신청·장학, 수강
마일리지, 졸업·교직, 셔틀, 공간·생활관, 증명서, LearnUs·출결 중
어느 기능을 쓸지 에이전트가 알아서 고릅니다. 학생은 명령어나 포털
메뉴 위치를 외울 필요가 없습니다.

> Claude 웹에서는 공지·수강·졸업·LearnUs 정리를 사용할 수 있습니다.
> 사용자의 학교 브라우저를 직접 눌러야 하는 셔틀 예약·공간 신청·증명서
> 발급은 Codex 데스크톱에서 진행하세요.

## 먼저 써 볼 네 가지

| 플러그인 | 이런 때 사용하세요 | 현재 범위 |
| --- | --- | --- |
| `yonsei-student-companion` | 포털 로그인을 반복하고 싶지 않거나 오늘 할 일을 한 번에 보고 싶을 때 | 공식 화면에서 한 번 로그인한 브라우저 세션 재사용·자연어 바로가기·오늘의 학생 브리핑 |
| `yonsei-notice-monitor` | 장학금, 등록금, 기숙사, IT 장애 공지를 놓치고 싶지 않을 때 | 공식 공개 공지 실시간 검색·마감일 추출·이전 확인과 비교 |
| `yonsei-course-registration` | 시간표와 마일리지 배분을 함께 짜고 싶을 때 | 충돌 없는 시간표와 정원·신청자·지난 컷을 고려한 마일리지 전략 |
| `yonsei-attendance-copilot` | 결석·지각 현황을 확인하거나 정정 문의를 준비할 때 | 첨부한 화면·표를 정리하고 문의 초안 작성, 출석 체크는 하지 않음 |

국제캠퍼스를 오간다면 `yonsei-shuttle-booking`, 공간을 빌리려면
`yonsei-space-reservation`, 성적표나 학사 화면을 정리하려면
`yonsei-academic-copilot`을 추가로 설치할 수 있습니다.

## 41개 학생용 스킬 상세 기능

스킬 이름을 알거나 직접 선택할 필요는 없습니다. 평소 말로 요청하면
에이전트가 아래 기능 중 알맞은 것을 골라 사용합니다. **조회**는 학교
정보를 바꾸지 않고, **초안**은 제출 직전까지 준비하며, **실행**은 학생이
최종 내용을 확인한 뒤 한 번만 진행합니다.

### 포털·오늘의 연세 — 매일 열어 볼 통합 도우미

한 번 로그인한 연세 전용 브라우저를 포털·Underwood·LearnUs·출결·셔틀
등에서 함께 사용합니다. 여러 메뉴를 찾아다니는 시간을 줄이고, 학교생활
전체의 다음 행동을 한곳에서 확인하고 싶은 학생에게 적합합니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [포털 한 번 연결](plugins/yonsei-student-companion/skills/connect-yonsei-session/SKILL.md) `connect-yonsei-session` | 공식 로그인 화면을 열고 학생이 직접 인증하면 같은 브라우저 프로필을 계속 재사용합니다. 세션이 만료된 경우에만 다시 로그인하도록 안내하며 비밀번호·OTP·쿠키를 받지 않습니다. | “연세 포털 로그인 한 번만 하고 계속 이어서 써 줘.” |
| [오늘의 연세](plugins/yonsei-student-companion/skills/summarize-yonsei-today/SKILL.md) `summarize-yonsei-today` | 오늘 수업, 7일 이내 LearnUs 마감, 출결 확인 항목, 예약, 공지, 장학·학사신청·생활관 일정을 읽기 전용으로 모아 우선순위와 다음 행동을 보여 줍니다. | “오늘 수업이랑 마감, 예약을 한 번에 정리해 줘.” |
| [학교 서비스 바로 열기](plugins/yonsei-student-companion/skills/open-yonsei-service/SKILL.md) `open-yonsei-service` | “증명서”, “상담”, “도서관”, “채플”처럼 목적만 말하면 현재 공식 주소와 포털 메뉴를 찾아 같은 로그인 세션에서 바로 엽니다. 오래된 즐겨찾기나 메뉴 위치를 기억할 필요가 없습니다. | “포털에서 학생증 재발급하는 곳 바로 열어 줘.” |
| [생활관 생활 관리](plugins/yonsei-student-companion/skills/manage-yonsei-dorm-life/SKILL.md) `manage-yonsei-dorm-life` | 신촌·국제·미래캠퍼스 생활관의 입사 신청, 납부·호실 상태, 룸메이트, 외박, 수리 신고, 시설 예약, 입·퇴사 업무를 조회하거나 최종 확인 후 신청합니다. | “이번 주 금요일 국제캠 외박 신청 준비해 줘.” |
| [맞춤 장학금 관리](plugins/yonsei-student-companion/skills/manage-yonsei-scholarships/SKILL.md) `manage-yonsei-scholarships` | 공식 공지와 본인의 Underwood 상태를 함께 보고 지원 가능성이 있는 장학금을 마감·누락 서류·확인 필요 조건 순으로 정리합니다. 선택한 장학금은 제출 전 검토까지 돕습니다. | “지금 지원할 만한 장학금과 필요한 서류를 찾아 줘.” |
| [교환학생 여정 관리](plugins/yonsei-student-companion/skills/manage-yonsei-exchange-journey/SKILL.md) `manage-yonsei-exchange-journey` | 지원 자격, 교내 지원, 파견교 지명, 출국 서류, 현지 수학, 학점 인정, 귀국 보고까지 현재 단계를 찾아 다음 마감과 준비물을 이어서 관리합니다. | “교환학생 지원에서 지금 다음으로 뭘 해야 해?” |

### 공지·마감일 — 놓치기 쉬운 학교 소식만 골라 보기

로그인 없이 연세대학교와 신촌 IT 공식 공지를 확인합니다. 장학·등록금·수강
같은 중요한 공지를 검색하고, 긴 본문에서 실제 신청일과 납부일만 뽑아
보고 싶은 학생에게 유용합니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [공식 공지 통합 검색](plugins/yonsei-notice-monitor/skills/search-yonsei-notices/SKILL.md) `search-yonsei-notices` | 여러 공식 공지 출처를 한 번에 검색하고 게시일·주제·기간으로 거른 뒤 최신순으로 합칩니다. 각 결과에 게시 기관, 핵심 문장, 원문 링크와 확인 시각을 제공합니다. | “최근 2주 장학금이랑 등록금 공지를 찾아 줘.” |
| [공지 마감일 추출](plugins/yonsei-notice-monitor/skills/list-yonsei-notice-deadlines/SKILL.md) `list-yonsei-notice-deadlines` | 공지 본문에서 신청·제출·납부·수강·행사 날짜를 문맥과 함께 추출하고 이미 지난 날짜와 다가오는 날짜를 구분합니다. 단순 게시일을 마감일로 오해하지 않습니다. | “이 공지들에서 이번 달 안에 끝나는 신청만 정리해 줘.” |
| [새 공지·변경 공지 확인](plugins/yonsei-notice-monitor/skills/watch-yonsei-notices/SKILL.md) `watch-yonsei-notices` | 사용자가 선택한 이전 확인 상태와 현재 공식 목록을 비교해 새로 올라온 공지, 내용이 바뀐 공지, 목록에서 사라진 공지를 구분합니다. 반복 확인에 적합합니다. | “지난번 이후 새로 생긴 수강 공지만 보여 줘.” |

### 수강계획·마일리지 — 시간표부터 배분 전략까지

과목표를 정리하는 단계부터 충돌 검사, 시간표 후보 생성, 개인 마일리지
이력을 반영한 전략까지 연결합니다. 수강신청 성공을 보장하지는 않지만
불확실성과 대체 과목을 함께 보여 줍니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [공식 수강편람 조회·과목표 정리](plugins/yonsei-course-registration/skills/normalize-yonsei-courses/SKILL.md) `normalize-yonsei-courses` | 로그인된 Underwood의 `수업 → 수강편람`을 직접 조회해 과목번호·분반·학점·교수·시간·캠퍼스로 정리합니다. 수강신청 기간이 아니어도 편람 조회를 먼저 시도하며, 캡처·PDF·엑셀은 공식 조회 실패 시 보조 입력으로만 씁니다. | “2026년 2학기 공과대학 자료구조 과목을 찾아 시간표용으로 정리해 줘.” |
| [시간표 충돌 검사](plugins/yonsei-course-registration/skills/check-yonsei-schedule/SKILL.md) `check-yonsei-schedule` | 수업 시간 중복, 같은 과목의 중복 분반, 개인 차단 시간, 신촌↔국제캠퍼스 이동시간 부족을 찾아냅니다. 시간이 불명확한 과목은 안전하다고 단정하지 않습니다. | “이 시간표에 겹치는 수업이나 캠퍼스 이동 문제가 있어?” |
| [수강계획 조건 점검](plugins/yonsei-course-registration/skills/audit-yonsei-course-plan/SKILL.md) `audit-yonsei-course-plan` | 선택한 시간표가 목표 학점, 필수 과목, 금요일 공강, 수업 시작·종료 시간, 하루 최대 수업량 등 학생이 말한 조건을 모두 만족하는지 항목별로 검사합니다. | “18학점, 전공필수 포함, 금요일 공강 조건을 만족하는지 봐 줘.” |
| [시간표 후보 자동 생성](plugins/yonsei-course-registration/skills/build-yonsei-timetable/SKILL.md) `build-yonsei-timetable` | 원하는 과목마다 가능한 분반을 조합해 충돌 없는 시간표를 만들고 공강, 등교일 수, 이동 부담, 선호 시간에 따라 후보를 순위화합니다. 실제 수강신청은 수행하지 않습니다. | “월요일 오전은 비우고 등교일이 적은 시간표 세 개 만들어 줘.” |
| [개인 맞춤 마일리지 전략](plugins/yonsei-course-registration/skills/plan-yonsei-mileage-strategy/SKILL.md) `plan-yonsei-mileage-strategy` | Underwood 개인 신청 이력, 과거 성공·실패, 현재 정원과 신청자, 마일리지 상한, 졸업 중요도, 동점 기준과 대체 과목을 반영해 배분안과 위험도를 계산합니다. | “내 이력과 현재 정원을 보고 마일리지 72점을 나눠 줘.” |
| [수강 사이트 접속 진단](plugins/yonsei-course-registration/skills/diagnose-yonsei-course-access/SKILL.md) `diagnose-yonsei-course-access` | 상시 조회 가능한 로그인된 Underwood 수강편람과 기간 중에만 열릴 수 있는 학부·대학원 수강신청 화면을 분리해 진단합니다. 편람의 실제 과목 행, 등록 기간, 로그인, 오래된 링크를 각각 확인하며 근거 없이 VPN이 필요하다고 단정하지 않습니다. | “수강신청은 닫혔어도 수강편람에서 과목은 직접 찾아 줘.” |

### 전자출결 — 기록 확인과 정정 준비

출석을 대신 체크하거나 위치를 위조하지 않습니다. 본인의 공식 출결 화면
또는 첨부 자료를 정리하고, 실제 기록과 기억이 다른 항목을 찾아 증빙과
정정 문의를 준비하는 데 집중합니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [과목별 출결 요약](plugins/yonsei-attendance-copilot/skills/summarize-yonsei-attendance/SKILL.md) `summarize-yonsei-attendance` | 출석·지각·결석·조퇴·공결·처리 대기를 전체와 과목별로 집계합니다. 조회 시각과 중복·알 수 없는 상태를 표시하며 출석 체크는 수행하지 않습니다. | “내 전자출결에서 결석이랑 지각을 과목별로 정리해 줘.” |
| [출결 불일치 찾기](plugins/yonsei-attendance-copilot/skills/find-yonsei-attendance-discrepancies/SKILL.md) `find-yonsei-attendance-discrepancies` | 공식 표시 상태와 학생이 기억하는 상태를 비교하되, 학생이 명시적으로 이의를 제기한 수업만 정정 후보로 분류합니다. 날짜·교시·사유·증빙이 부족하면 무엇이 필요한지 알려 줍니다. | “이날은 출석했는데 결석으로 나온 항목을 확인해 줘.” |
| [출결 정정 문의 초안](plugins/yonsei-attendance-copilot/skills/draft-yonsei-attendance-correction/SKILL.md) `draft-yonsei-attendance-correction` | 확인된 불일치를 바탕으로 교수님께 보낼 정중한 한국어 문의와 증빙 체크리스트를 작성합니다. 메시지는 자동 전송하지 않아 학생이 검토·수정할 수 있습니다. | “이 결석 기록에 대한 정정 문의를 정중하게 써 줘.” |

### 캠퍼스 셔틀 — 말로 찾고 확인 후 예약

신촌과 국제캠퍼스의 이동 방향·날짜·시간만 말하면 후보를 찾습니다.
조회 결과에는 시각이 표시되며, 예약·대기·취소는 정확한 편을 학생이
확인한 뒤 한 번만 실행합니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [셔틀 후보 정리](plugins/yonsei-shuttle-booking/skills/list-yonsei-shuttle-options/SKILL.md) `list-yonsei-shuttle-options` | 공식 화면 캡처나 표에서 날짜, 출발 캠퍼스, 시간 범위, 최소 잔여석 조건에 맞는 편을 걸러 시간순으로 정리합니다. 첨부 시점 이후의 좌석은 실시간이라고 주장하지 않습니다. | “이 화면에서 오전 9시 전 신촌 출발 셔틀만 보여 줘.” |
| [잔여석·대기 상태 판별](plugins/yonsei-shuttle-booking/skills/check-yonsei-shuttle-seats/SKILL.md) `check-yonsei-shuttle-seats` | 선택한 한 편을 예약 가능, 대기만 가능, 매진, 확인 불가로 구분하고 공식 화면에서 읽은 잔여석과 대기 인원을 함께 보여 줍니다. | “이 9시 셔틀은 바로 예약할 수 있어, 대기해야 해?” |
| [셔틀 접속 문제 진단](plugins/yonsei-shuttle-booking/skills/diagnose-yonsei-shuttle-access/SKILL.md) `diagnose-yonsei-shuttle-access` | 포털의 셔틀 진입 주소, 로그인 경계, 공개 화면 구성요소를 점검해 링크 만료·인증 필요·서비스 장애를 구분합니다. 예약이나 개인정보 변경은 하지 않습니다. | “포털 셔틀 메뉴가 안 열리는데 어디서 막힌 건지 봐 줘.” |
| [셔틀 조회·예약·취소](plugins/yonsei-shuttle-booking/skills/book-yonsei-shuttle/SKILL.md) `book-yonsei-shuttle` | Windows·macOS·Linux에서 방향·날짜·선호 시간을 받아 공식 후보를 조회합니다. 선택한 편과 사유를 보여 준 뒤 확인받아 예약·대기·취소하고 공식 내역에서 결과를 다시 확인합니다. | “내일 9시쯤 신촌에서 국제캠퍼스 가는 셔틀 예약해 줘.” |

### 공간대관 — 조건 검색부터 접수 확인까지

인원과 장비에 맞지 않는 공간을 일일이 열어 보지 않아도 됩니다. 이용
규칙과 요금을 먼저 확인하고, 실제 신청은 학생이 공간·시간·연락처를
검토한 뒤 진행합니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [조건에 맞는 공간 찾기](plugins/yonsei-space-reservation/skills/search-yonsei-spaces/SKILL.md) `search-yonsei-spaces` | 공식 공간 목록 화면이나 표에서 날짜·시간 전체 포함 여부, 최소 수용인원, 건물, 프로젝터 등 필수 장비로 후보를 거르고 조건 적합도순으로 정리합니다. | “다음 주 수요일 15명, 프로젝터 있는 스터디 공간 찾아 줘.” |
| [대관 규칙 사전 점검](plugins/yonsei-space-reservation/skills/check-yonsei-space-rules/SKILL.md) `check-yonsei-space-rules` | 신청 가능 시점, 최대 이용시간, 예약 건수, 10분 단위, 신청자 자격, 제한 기간 등 공개 규칙과 요청을 비교합니다. 필요한 정보가 없으면 가능하다고 추측하지 않습니다. | “이 일정으로 공간을 빌려도 규칙에 맞는지 확인해 줘.” |
| [공간 신청 초안](plugins/yonsei-space-reservation/skills/prepare-yonsei-space-request/SKILL.md) `prepare-yonsei-space-request` | 신청자, 공간, 날짜·시간, 인원, 목적, 장비, 연락처를 완성된 검토용 초안과 준비물 목록으로 만듭니다. 제출하거나 승인된 것처럼 표현하지 않습니다. | “이 내용으로 공간 신청서를 작성하되 아직 제출하지 마.” |
| [공간 검색·신청](plugins/yonsei-space-reservation/skills/submit-yonsei-space-request/SKILL.md) `submit-yonsei-space-request` | Windows·macOS·Linux 공식 공간 시스템에서 조건을 검색하고 선택 공간의 수용인원·시간·표시 요금을 재확인합니다. 최종 내용 확인 후 한 번 제출하고 신청 내역의 접수 상태를 확인합니다. | “15명 스터디 공간을 찾아 신청까지 진행해 줘.” |

### 학사·성적·졸업·교직 — 남은 학교생활을 계산

단순 학점 합계를 넘어 학번·전공·입학연도에 맞는 공식 기준과 본인의
Underwood 진행표를 비교합니다. 계산은 계획을 돕는 결과이며 최종 졸업
판정은 학교의 공식 예비사정·졸업심사를 따라야 합니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [이번 학기 강의 정리](plugins/yonsei-academic-copilot/skills/list-yonsei-classes/SKILL.md) `list-yonsei-classes` | 학사정보 화면이나 첨부 자료에서 과목번호·분반·교수·학점·수업시간을 추려 현재 학기 강의 목록으로 정리합니다. 공식 수강 내역을 변경하지 않습니다. | “내 학사정보 화면에서 이번 학기 수업을 표로 정리해 줘.” |
| [성적·평량평균 요약](plugins/yonsei-academic-copilot/skills/summarize-yonsei-grades/SKILL.md) `summarize-yonsei-grades` | 신청학점·취득학점·평량평균 반영학점과 4.3 기준 보수적 GPA를 계산하고, 화면에 표시된 GPA와 계산값이 다르면 원인을 확인할 항목으로 남깁니다. | “이 성적표에서 취득학점과 GPA를 학기별로 요약해 줘.” |
| [재학·휴학 상태 확인](plugins/yonsei-academic-copilot/skills/check-yonsei-enrollment/SKILL.md) `check-yonsei-enrollment` | 재학·휴학·수료·졸업·제적 상태와 해당 학기 등록 증거를 분리해 읽고 서로 모순되는 표시나 빠진 학기 정보를 알려 줍니다. 장학·증명서 자격을 임의로 추론하지 않습니다. | “이 화면에서 내 학적 상태와 확인할 항목을 알려 줘.” |
| [학사신청 마감 레이더](plugins/yonsei-academic-copilot/skills/track-yonsei-academic-applications/SKILL.md) `track-yonsei-academic-applications` | 휴·복학, 전공 변경, 복수전공·부전공, 학점 인정, 졸업 관련 신청 등 Underwood 항목을 지금 신청 가능, 곧 마감, 진행 중, 확인 필요로 나눕니다. | “지금 열려 있는 학사신청과 내가 이미 낸 신청을 정리해 줘.” |
| [졸업요건 계산](plugins/yonsei-academic-copilot/skills/calculate-yonsei-graduation-progress/SKILL.md) `calculate-yonsei-graduation-progress` | 입학연도·캠퍼스·대학·전공별 공식 기준과 취득·수강 중·인정·대체 학점을 비교해 완료, 진행 중, 부족 학점·필수 과목·인증을 근거와 함께 계산합니다. | “2024학번 컴퓨터과학과 기준으로 졸업까지 뭐가 부족해?” |
| [졸업까지 학기별 계획](plugins/yonsei-academic-copilot/skills/plan-yonsei-graduation-path/SKILL.md) `plan-yonsei-graduation-path` | 졸업요건 계산 결과와 향후 개설 예정 과목을 이용해 선수과목, 연 1회 개설, 학기 최대학점을 고려한 학기별 이수 계획과 예상 남은 학기를 만듭니다. | “졸업까지 남은 과목을 다음 학기부터 어떻게 배치할까?” |
| [교직이수 진행 관리](plugins/yonsei-academic-copilot/skills/manage-yonsei-teaching-credential/SKILL.md) `manage-yonsei-teaching-credential` | 교직 과목, 적성·인성검사, 응급처치, 교육실습, 폭력예방교육, 성적과 신청·발급 절차를 완료·진행·예정·누락으로 나눠 다음 날짜가 있는 행동을 보여 줍니다. | “내 교직이수에서 교육실습 전에 남은 요건을 계산해 줘.” |

### 증명서·학생활동 문서 — 운영체제에 맞춰 끝까지

Windows에서는 학교의 공식 ReportX 경로를 사용하고, macOS·Linux에서는
번들된 연세 제목체·본문체를 각각 포함하는 호환 PDF 경로를 사용합니다.
유료 전자증명서와 호환 PDF의 차이를 숨기지 않습니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [증명서 환경 진단](plugins/yonsei-certificate-assistant/skills/yonsei-certificate-assistant/SKILL.md) `yonsei-certificate-assistant` | 운영체제, 공식 ReportX 연결, localhost 65432, 발급 티켓, 필요한 공식 런타임과 글꼴을 점검해 Windows 공식 출력 또는 macOS/Linux 호환 PDF 경로를 선택합니다. | “이 컴퓨터에서 연세 증명서를 발급할 수 있는지 확인해 줘.” |
| [증명서 E2E 발급](plugins/yonsei-certificate-assistant/skills/issue-yonsei-certificate/SKILL.md) `issue-yonsei-certificate` | 재학·성적·졸업 등 문서 종류, 국·영문, 매수, 용도, PDF·프린터를 확인한 뒤 공식 iCert 인증부터 결과 확인까지 진행합니다. 문서번호가 필요한 요청은 한 번만 예약합니다. | “국문 재학증명서를 PDF로 발급해 줘.” |
| [ReportX FP3 호환 PDF](plugins/yonsei-certificate-assistant/skills/render-reportx-fp3-pdf/SKILL.md) `render-reportx-fp3-pdf` | 정상 발급 과정에서 이미 복호화된 FP3 준비 보고서와 이미지 구성요소를 Windows 없이 로컬 PDF로 렌더링하고 글꼴·페이지 결과를 검사합니다. 증명서 내용을 만들거나 바꾸는 기능이 아닙니다. | “이 정상 발급 FP3 결과를 macOS에서 검토 가능한 PDF로 렌더링해 줘.” |
| [학생활동·실습 확인서](plugins/yonsei-certificate-assistant/skills/issue-yonsei-student-activity-documents/SKILL.md) `issue-yonsei-student-activity-documents` | 학생홍보대사, RA, 교육실습, 등록금 납부, 생활관 등 성적·재학증명서가 아닌 교내 활동 문서를 공식 메뉴에서 찾고 발급 결과 파일과 글꼴을 확인합니다. | “교육실습 참가확인서를 찾아 PDF로 발급해 줘.” |

### LearnUs — 강의·과제·자료를 한 번에 정리

공식 포털 로그인을 이어 쓰며 강의실에서 학생이 볼 수 있는 항목만
읽습니다. 과제 제출, 퀴즈 응시, 성적 변경은 수행하지 않습니다.

| 스킬 | 상세 기능 | 이렇게 요청해 보세요 |
| --- | --- | --- |
| [LearnUs 로그인 유지](plugins/learnus-course-copilot/skills/manage-learnus-session/SKILL.md) `manage-learnus-session` | 공식 LearnUs 로그인과 포털 SSO를 같은 브라우저 프로필에서 재사용하고 만료됐을 때만 다시 연결합니다. GUI 없는 세션은 학생이 명시적으로 요청한 경우에만 사용합니다. | “LearnUs 로그인 연결하고 이 작업 끝날 때까지 이어서 써 줘.” |
| [내 강의 목록](plugins/learnus-course-copilot/skills/list-learnus-courses/SKILL.md) `list-learnus-courses` | My Courses 대시보드에서 실제로 보이는 강의를 중복 없이 정리하고 강의명, 안정적인 강의 ID, 민감한 쿼리를 제거한 링크를 제공합니다. | “내 LearnUs 강의 목록을 링크와 함께 보여 줘.” |
| [과제 마감일](plugins/learnus-course-copilot/skills/list-learnus-deadlines/SKILL.md) `list-learnus-deadlines` | 강의 화면에서 과제 활동과 명확히 연결된 마감만 추출해 과목·과제·날짜별로 정리합니다. 공지 작성일이나 달력의 무관한 날짜를 과제 마감으로 섞지 않습니다. | “이번 주 LearnUs에서 제출해야 할 과제를 정리해 줘.” |
| [강의자료·영상 목록](plugins/learnus-course-copilot/skills/list-learnus-materials/SKILL.md) `list-learnus-materials` | 강의별 파일, 폴더, 외부 자료, 읽기자료, 화면에 표시된 영상 항목을 종류와 링크로 정리합니다. 접근 권한이 없는 자료를 우회하거나 다운로드 권한을 늘리지 않습니다. | “이 강의의 슬라이드와 녹화영상 링크를 모아 줘.” |

## 터미널 설치가 편한 경우

### Codex

터미널에 아래 두 줄을 차례로 붙여 넣습니다.

```bash
codex plugin marketplace add mrcha033/yonsei-skills
codex plugin add yonsei-student-companion@yonsei-skills
```

설치가 끝나면 새 작업을 열고 평소 말하듯 질문하세요.

> 연세 포털에 한 번 로그인하고 오늘 할 일을 정리해 줘.

공지나 시간표 도구도 쓰려면 다음 플러그인을 추가합니다.

```bash
codex plugin add yonsei-notice-monitor@yonsei-skills
codex plugin add yonsei-course-registration@yonsei-skills
```

### Claude Code

```bash
claude plugin marketplace add mrcha033/yonsei-skills
claude plugin install yonsei-student-companion@yonsei-skills
```

Claude Code 안에서는 `/plugin` 화면의 **Marketplaces** 탭에
`mrcha033/yonsei-skills`를 추가한 뒤 원하는 플러그인을 고르는 방법도
사용할 수 있습니다. 설치 후 `/reload-plugins`를 실행하거나 Claude Code를
다시 시작하세요.

### ChatGPT 사용자

ChatGPT Work와 Codex의 공개 Plugins 화면에 바로 나오려면 OpenAI의
공개 플러그인 심사를 통과해야 합니다. 심사용 통합 ZIP과 제출 자료는
자동으로 만들지만, 공개 전까지는 위의 Codex용 ZIP 또는 Claude용 ZIP을
사용하세요. 현재 상태는
[`docs/openai-directory-submission.md`](docs/openai-directory-submission.md)에
정리했습니다.

## 코딩이나 JSON을 알아야 하나요?

아니요. 사용자는 JSON 파일을 만들 필요가 없습니다.

- 공지는 원하는 주제와 기간만 말하면 됩니다.
- 시간표는 원하는 학기·단과대·학과·과목명을 말하면 로그인된
  Underwood 수강편람을 직접 조회합니다. 캡처나 표는 공식 조회가
  실패했을 때만 보조 입력으로 사용합니다.
- 학사·출결 정보도 가능한 항목은 로그인된 공식 화면을 먼저 읽고,
  직접 조회할 수 없는 자료만 화면이나 표를 받습니다.
- 포털·LearnUs·셔틀·공간·증명서는 같은 브라우저 프로필을 우선
  재사용합니다. 학생은 공식 화면에서 한 번 로그인하고, 학교 세션이
  만료될 때만 다시 연결합니다.
- 플러그인이 읽을 수 있는 항목만 임시로 구조화하며, 결과에는 자료를
  확인한 시각과 빠진 항목을 함께 표시합니다.
- 최신 상태가 중요한 좌석·출결·공간 정보는 첨부한 화면 시각 이후에도
  바뀔 수 있으므로 공식 화면에서 마지막으로 확인해야 합니다.

예시:

> 2026년 2학기 신촌 공과대학 수강편람을 직접 찾아서 금요일 공강, 18학점 시간표를 만들어 줘.

> 첨부한 전자출결 화면에서 결석과 지각을 과목별로 정리해 줘.

> 이 셔틀 화면에서 내일 오전 9시 전에 신촌에서 국제캠퍼스로 가는 편을 찾아 줘.

> 내 성적표와 2024학번 전공 졸업요건을 비교해서 부족한 과목을 계산해 줘.

> 지난 마일리지 컷과 현재 정원을 고려해서 72점을 전략적으로 나눠 줘.

## 학생용 플러그인

| 플러그인 | 설치 명령 | 할 수 있는 일 |
| --- | --- | --- |
| 포털·오늘의 연세 | `codex plugin add yonsei-student-companion@yonsei-skills` | 기존 브라우저 로그인 재사용, 오늘 요약, 생활관·장학금·교환학생 관리 |
| 공지·마감일 | `codex plugin add yonsei-notice-monitor@yonsei-skills` | 대학·IT 공식 공지 검색, 본문 날짜 추출, 이전 확인과 비교 |
| 수강계획 | `codex plugin add yonsei-course-registration@yonsei-skills` | 시간표 후보, 충돌·이동시간, Underwood 개인 이력·정원 기반 마일리지 전략 |
| 전자출결 | `codex plugin add yonsei-attendance-copilot@yonsei-skills` | 출결 요약, 확인할 기록 찾기, 정정 문의 초안 |
| 셔틀 | `codex plugin add yonsei-shuttle-booking@yonsei-skills` | 방향·시간별 후보, 잔여석, 확인 후 예약·대기·취소 |
| 공간대관 | `codex plugin add yonsei-space-reservation@yonsei-skills` | 공간 검색, 규칙·요금 확인, 확인 후 신청 및 접수 확인 |
| 학사·졸업 | `codex plugin add yonsei-academic-copilot@yonsei-skills` | 학사신청·교직이수, 공식 진행표 기반 졸업요건과 남은 학기 계산 |
| 증명서 | `codex plugin add yonsei-certificate-assistant@yonsei-skills` | 증명서·학생활동·교육실습 문서를 Windows 공식 ReportX 또는 macOS/Linux 호환 PDF로 발급 |
| LearnUs | `codex plugin add learnus-course-copilot@yonsei-skills` | 강의·마감일·자료 정리, 실행 중 로그인 만료 자동 복구 |

학생용 플러그인 9개에 41개 스킬이 들어 있습니다. 마켓플레이스에는
스킬이 아니라 플러그인 단위로 표시되며, 플러그인을 설치하면 포함된
스킬이 함께 활성화됩니다. 이전에 언급된 37개와 현재 전체 53개의 구분은
[`docs/skill-catalog.md`](docs/skill-catalog.md)에 정리했습니다.

LearnUs도 기본적으로 같은 브라우저 프로필을 이어 씁니다. 포털 로그인,
외부 로그인, MFA가 필요하면 공식 화면을 그대로 열어 두고 학생이 한 번
완료한 뒤 원래 작업을 계속합니다. 터미널 기반 메모리 전용 세션은
학생이 백그라운드 실행을 명시적으로 요청한 경우에만 선택합니다.

## 연구·행정용 플러그인

`yonsei-yri`, `yonsei-rms`, `yonsei-erp`, `yonsei-groupware`는 일반 학부
생활보다 연구자·대학원생·교직원의 내보내기 자료 점검에 가깝습니다.
실시간 서버를 조회하거나 승인·지급·발송을 수행하지 않습니다.

## 개인정보와 로그인

- 비밀번호, OTP, 세션 쿠키를 채팅에 붙여 넣지 마세요.
- 공개 공지 도구는 로그인과 VPN이 필요 없습니다.
- 로그인은 포털·LearnUs 등 학교 공식 브라우저 화면에서 직접 합니다.
  도구는 비밀번호나 쿠키를 복사하지 않고 같은 브라우저 프로필만
  이어 씁니다.
- 화면 캡처를 첨부하기 전 학번, 전화번호, 주소처럼 질문에 필요 없는
  정보는 가리는 것을 권장합니다.
- 학사·출결·연구·행정 도구는 인식한 최소 필드만 결과에 남깁니다.
- 플러그인은 출석 체크, 수강신청, 승인, 결제, 메시지 발송을 수행하지
  않습니다. 셔틀 예약·공간 신청·무료 프린트 증명서 발급은 정확한
  대상과 전송 내용을 보여 준 뒤 학생이 확인한 경우에만 한 번 실행합니다.

## 꼭 알아둘 제한

- 성적·출결·졸업 계산과 마일리지 이력은 첨부한 화면·표·공식 문서를
  분석합니다. 학교의 공식 졸업사정이나 수강 성공을 보장하지 않습니다.
- 셔틀과 공간은 제출 직전에 공식 화면에서 조건을 다시 확인합니다.
- 공간 신청은 접수일 뿐 승인이나 결제가 아닙니다.
- Windows 무료 출력은 학교의 공식 ReportX를 사용합니다. macOS/Linux에서
  도구가 만드는 파일은 정상 발급 응답의 호환 렌더링 PDF이며,
  전자서명된 공식 전자증명서라는 뜻이 아닙니다.
- macOS/Linux 증명서는 재배포 허가를 받은 연세 제목체와 본문체가
  플러그인에 포함되어 별도 설치 없이 각각 PDF에 들어갑니다. 두 파일의
  무결성이 맞지 않으면 다른 한글 글꼴로 바꾸지 않고 발급 전에 중단합니다.
- ERP 로그인 과정에서는 HTTPS에서 HTTP로 내려가는 레거시 경로가
  관측되어 라이브 로그인 기능을 제공하지 않습니다.

서비스별 확인 근거와 남은 범위는
[`docs/service-evidence-matrix.md`](docs/service-evidence-matrix.md)에 있습니다.
포털에서 확인한 기능과 다음 우선순위는
[`docs/portal-convenience-review.md`](docs/portal-convenience-review.md)에
정리했습니다.

## 업데이트와 삭제

마켓플레이스와 설치된 플러그인을 최신 상태로 갱신합니다.

```bash
codex plugin marketplace upgrade yonsei-skills
claude plugin marketplace update yonsei-skills
```

플러그인을 제거합니다.

```bash
codex plugin remove yonsei-notice-monitor@yonsei-skills
claude plugin uninstall yonsei-notice-monitor@yonsei-skills
```

## 설치가 안 될 때

1. `codex plugin marketplace list` 또는 `claude plugin marketplace list`에서
   `yonsei-skills`가 보이는지 확인합니다.
2. 기존 작업에는 새 스킬이 바로 나타나지 않을 수 있으므로 새 작업을
   열거나 Claude Code에서 `/reload-plugins`를 실행합니다.
3. `plugin not found`가 나오면 마켓플레이스를 업데이트한 뒤 다시 설치합니다.
4. 학교 로그인 화면이 나오면 브라우저에서 직접 로그인하고 비밀번호를
   채팅에 입력하지 않습니다.

문제가 계속되면 GitHub Issues에 사용한 제품(Codex 또는 Claude Code),
운영체제, 오류 문구를 올려 주세요. 비밀번호·쿠키·학번은 포함하지 마세요.

## 개발

```bash
python3 -B scripts/render_manifests.py
python3 -B scripts/sync_runtime.py
python3 -B scripts/validate_repo.py
python3 -B -m unittest discover -s tests -v
```

공식 포털 주소 점검은 `python3 -B scripts/check_portal_catalog.py`로 실행합니다.

## 라이선스

코드는 MIT License입니다. 번들된 `연세제목.TTF`와 `연세본문.TTF`는
MIT 적용 대상이 아니며 원 저작권과 재배포 허가 조건을 따릅니다.
