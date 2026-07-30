# 터미널 없이 Yonsei Skills 설치하기

코드나 명령어를 몰라도 됩니다. 사용하는 앱에 맞는 파일 하나만 받으세요.

## Codex 데스크톱 앱

1. [Codex용 ZIP 받기](https://github.com/mrcha033/yonsei-skills/releases/latest/download/yonsei-codex-ui-pack.zip)를 누릅니다.
2. 다운로드한 ZIP을 더블클릭해 압축을 풉니다.
3. Codex 데스크톱 앱에서 압축을 푼 `yonsei-skills` 폴더를 엽니다.
4. 앱을 한 번 다시 시작하고 **Plugins**를 엽니다.
5. **Yonsei Skills - 학생생활**에서 원하는 도구의 `+`를 누릅니다.
6. 새 작업을 열고 “내 졸업요건 계산해 줘”처럼 평소 말하듯 요청합니다.

플러그인이 안 보이면 다른 폴더가 아니라 `.agents` 폴더가 들어 있는
`yonsei-skills` 폴더 자체를 열었는지 확인하세요.

## Claude 웹·데스크톱

1. [Claude용 ZIP 받기](https://github.com/mrcha033/yonsei-skills/releases/latest/download/yonsei-student-life.zip)를 누릅니다.
2. Claude에서 **Customize → Skills → + → Create skill → Upload a skill**로 이동합니다.
3. ZIP을 풀지 말고 그대로 업로드합니다.
4. **연세 학생생활 도우미**를 켜고 새 대화를 시작합니다.

`.skill` 파일을 받는 화면이라면
[yonsei-student-life.skill](https://github.com/mrcha033/yonsei-skills/releases/latest/download/yonsei-student-life.skill)을
대신 선택해도 됩니다.

Claude 웹에서는 공지, 시간표, 마일리지, 졸업계획과 자료 정리는 사용할
수 있습니다. 사용자의 학교 브라우저를 직접 눌러야 하는 셔틀 예약, 공간
신청, 증명서 발급은 초안과 최종 확인 내용까지 준비하고 실제 클릭은
브라우저 제어가 있는 Codex 데스크톱에서 진행하는 것이 안전합니다.

## 설치 후 첫 질문

- “연세 포털에 한 번 로그인하고 오늘 할 일을 정리해 줘.”
- “이번 주에 놓치면 안 되는 연세대 공지를 찾아 줘.”
- “내 성적표와 2024학번 전공요건을 비교해 줘.”
- “정원과 지난 컷을 고려해서 마일리지를 나눠 줘.”
- “내일 오전 9시쯤 신촌에서 국제캠퍼스로 가는 셔틀을 찾아 줘.”
- “이번 주 LearnUs 과제와 마감일을 정리해 줘.”

비밀번호, OTP, 세션 쿠키는 채팅에 입력하지 마세요. 학교 로그인이
필요하면 도구가 공식 로그인 화면을 열어 둡니다. 그 화면에서 한 번
로그인하면 같은 브라우저 프로필을 포털·LearnUs·출결·셔틀·공간·도서관
작업에 이어 사용합니다. 학교 세션이 만료되면 그때만 다시 로그인합니다.
