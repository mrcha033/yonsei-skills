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

`yonsei-student-companion`은 한 번 로그인한 전용 브라우저 프로필을
재사용해 오늘의 연세, 학사신청·장학, 수강 마일리지, 졸업·교직, 셔틀,
공간·생활관, 증명서, LearnUs·출결을 빠른 내부 명령으로 연결합니다.
학생은 명령어나 포털 메뉴 위치를 외울 필요가 없습니다.

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
- 시간표·학사·출결 정보는 화면 캡처를 첨부하거나 표를 그대로
  붙여 넣으면 됩니다.
- 포털·LearnUs·셔틀·공간·증명서는 같은 브라우저 프로필을 우선
  재사용합니다. 학생은 공식 화면에서 한 번 로그인하고, 학교 세션이
  만료될 때만 다시 연결합니다.
- 플러그인이 읽을 수 있는 항목만 임시로 구조화하며, 결과에는 자료를
  확인한 시각과 빠진 항목을 함께 표시합니다.
- 최신 상태가 중요한 좌석·출결·공간 정보는 첨부한 화면 시각 이후에도
  바뀔 수 있으므로 공식 화면에서 마지막으로 확인해야 합니다.

예시:

> 이 수강편람 캡처로 금요일 공강, 18학점, 신촌캠퍼스 위주 시간표를 만들어 줘.

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
