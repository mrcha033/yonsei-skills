# Yonsei Skills

연세대학교 생활에서 자주 반복되는 확인·정리 작업을 자연어로 처리하는 비공식 오픈소스 플러그인 모음입니다.

> 연세대학교 공식 서비스가 아닙니다. 학교 계정 권한을 늘리거나 수강신청·출석·예약 제한을 우회하지 않습니다.

## 먼저 써 볼 세 가지

| 플러그인 | 이런 때 사용하세요 | 현재 범위 |
| --- | --- | --- |
| `yonsei-notice-monitor` | 장학금, 등록금, 기숙사, IT 장애 공지를 놓치고 싶지 않을 때 | 공식 공개 공지 실시간 검색·마감일 추출·이전 확인과 비교 |
| `yonsei-course-registration` | 여러 분반으로 충돌 없는 시간표를 만들고 싶을 때 | 붙여 넣은 표·화면 캡처를 바탕으로 시간표 계획, 실제 신청은 하지 않음 |
| `yonsei-attendance-copilot` | 결석·지각 현황을 확인하거나 정정 문의를 준비할 때 | 첨부한 화면·표를 정리하고 문의 초안 작성, 출석 체크는 하지 않음 |

국제캠퍼스를 오간다면 `yonsei-shuttle-booking`, 공간을 빌리려면
`yonsei-space-reservation`, 성적표나 학사 화면을 정리하려면
`yonsei-academic-copilot`을 추가로 설치할 수 있습니다.

## 3분 설치

### Codex

터미널에 아래 두 줄을 차례로 붙여 넣습니다.

```bash
codex plugin marketplace add mrcha033/yonsei-skills
codex plugin add yonsei-notice-monitor@yonsei-skills
```

설치가 끝나면 새 작업을 열고 평소 말하듯 질문하세요.

> 이번 주에 내가 놓치면 안 되는 연세대 공지를 찾아 줘.

시간표 도구도 쓰려면 다음 한 줄만 추가합니다.

```bash
codex plugin add yonsei-course-registration@yonsei-skills
```

### Claude Code

```bash
claude plugin marketplace add mrcha033/yonsei-skills
claude plugin install yonsei-notice-monitor@yonsei-skills
```

Claude Code 안에서는 `/plugin` 화면의 **Marketplaces** 탭에
`mrcha033/yonsei-skills`를 추가한 뒤 원하는 플러그인을 고르는 방법도
사용할 수 있습니다. 설치 후 `/reload-plugins`를 실행하거나 Claude Code를
다시 시작하세요.

### ChatGPT 사용자

이 저장소는 Codex와 Claude Code 마켓플레이스 형식으로 배포됩니다.
ChatGPT 웹·데스크톱에서 조직용 플러그인을 가져오는 기능은 요금제와
워크스페이스 설정에 따라 다르므로, 플러그인 디렉터리에 이 마켓플레이스를
직접 가져올 수 없는 계정에서는 Codex에서 사용하는 것이 가장 간단합니다.

## 코딩이나 JSON을 알아야 하나요?

아니요. 사용자는 JSON 파일을 만들 필요가 없습니다.

- 공지는 원하는 주제와 기간만 말하면 됩니다.
- 시간표·학사·출결·셔틀·공간 정보는 화면 캡처를 첨부하거나 표를 그대로
  붙여 넣으면 됩니다.
- 플러그인이 읽을 수 있는 항목만 임시로 구조화하며, 결과에는 자료를
  확인한 시각과 빠진 항목을 함께 표시합니다.
- 최신 상태가 중요한 좌석·출결·공간 정보는 첨부한 화면 시각 이후에도
  바뀔 수 있으므로 공식 화면에서 마지막으로 확인해야 합니다.

예시:

> 이 수강편람 캡처로 금요일 공강, 18학점, 신촌캠퍼스 위주 시간표를 만들어 줘.

> 첨부한 전자출결 화면에서 결석과 지각을 과목별로 정리해 줘.

> 이 셔틀 화면에서 내일 오전 9시 전에 신촌에서 국제캠퍼스로 가는 편을 찾아 줘.

## 학생용 플러그인

| 플러그인 | 설치 명령 | 할 수 있는 일 |
| --- | --- | --- |
| 공지·마감일 | `codex plugin add yonsei-notice-monitor@yonsei-skills` | 대학·IT 공식 공지 검색, 본문 날짜 추출, 이전 확인과 비교 |
| 수강계획 | `codex plugin add yonsei-course-registration@yonsei-skills` | 과목 표 정리, 충돌·이동시간 확인, 시간표 후보 생성 |
| 전자출결 | `codex plugin add yonsei-attendance-copilot@yonsei-skills` | 출결 요약, 확인할 기록 찾기, 정정 문의 초안 |
| 셔틀 | `codex plugin add yonsei-shuttle-booking@yonsei-skills` | 셔틀 화면 필터, 잔여석 판정, 접속 진단 |
| 공간대관 | `codex plugin add yonsei-space-reservation@yonsei-skills` | 공간 후보 필터, 공개 규칙 확인, 신청 초안 |
| 학사정보 | `codex plugin add yonsei-academic-copilot@yonsei-skills` | 강의·성적·학적 화면 정리 |
| Mac 증명서 | `codex plugin add yonsei-certificate-assistant@yonsei-skills` | 인터넷증명서 ReportX 진단과 호환 PDF 렌더링 |

`learnus-course-copilot`은 학교의 지속형 학생 API 토큰이 제공되지 않고
현재 로그인 만료 복구를 공개 사용자 환경에서 다시 확인해야 하므로 아직
설치 가능 목록에서 제외했습니다.

## 연구·행정용 플러그인

`yonsei-yri`, `yonsei-rms`, `yonsei-erp`, `yonsei-groupware`는 일반 학부
생활보다 연구자·대학원생·교직원의 내보내기 자료 점검에 가깝습니다.
실시간 서버를 조회하거나 승인·지급·발송을 수행하지 않습니다.

## 개인정보와 로그인

- 비밀번호, OTP, 세션 쿠키를 채팅에 붙여 넣지 마세요.
- 공개 공지 도구는 로그인과 VPN이 필요 없습니다.
- 화면 캡처를 첨부하기 전 학번, 전화번호, 주소처럼 질문에 필요 없는
  정보는 가리는 것을 권장합니다.
- 학사·출결·연구·행정 도구는 인식한 최소 필드만 결과에 남깁니다.
- 플러그인은 출석 체크, 수강신청, 예약, 승인, 결제, 메시지 발송을 대신
  수행하지 않습니다.

## 꼭 알아둘 제한

- 공지를 제외한 대부분의 학생 도구는 첨부한 화면·표·내보내기 파일을
  분석합니다. 현재 학교 서버의 실시간 상태라고 주장하지 않습니다.
- 셔틀 잔여석과 공간 가능 시간은 공식 화면에서 다시 확인해야 합니다.
- 증명서 도구가 만드는 파일은 정상 발급 응답의 macOS 호환 렌더링
  PDF이며, 전자서명된 공식 전자증명서라는 뜻이 아닙니다.
- ERP 로그인 과정에서는 HTTPS에서 HTTP로 내려가는 레거시 경로가
  관측되어 라이브 로그인 기능을 제공하지 않습니다.

서비스별 확인 근거와 남은 범위는
[`docs/service-evidence-matrix.md`](docs/service-evidence-matrix.md)에 있습니다.

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

MIT License. Copyright © mrcha033.
