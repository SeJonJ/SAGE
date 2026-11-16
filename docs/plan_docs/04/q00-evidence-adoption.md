Cycle-Stem: q00-evidence-adoption
Document-Language: ko
Issue: https://github.com/SeJonJ/SAGE/issues/40

# 검증 근거

개발 후보 V5는 아래 테스트와 독립 검토를 완료했다. 코드 후보 wheel SHA-256은 `2b48eaa02c160a5d35fcd1a27be83aeec83c1ab4ba32d8dc9e4eb99f688c8ed8`, patch SHA-256은 `d1a5020e407ca0ccd67fe703f8a4a25d56d214a9e6ab579967215f1a5bc22767`이다. 이 hash는 개발 당시1.3.7 이름의 격리 wheel이며1.3.8 공개 배포물 hash와 동일하다고 주장하지 않는다. 최종 문서·버전 변경의 CI/배포 근거는 PR 및 tag workflow로 별도 확인한다.

|검사|확인한 범위|
|---|---|
|macOS 일반 회귀|116 suites·4,186 test executions, 실패0|
|격리 wheel 설치|Claude, Codex local/global, 실제 구판 non-force/force, 개인 runner2선언 총7대표 셀|
|Windows11 Pro build26200·x64·NTFS|Python3.10.11/3.11.9/3.12.10의42 unittest executions|
|Windows 소유권|Python당8subcases(2host×2path×2spelling), 합계24subcases. 위42에 포함되는 테스트의 세부 사례|
|Windows 설치|3Python×Claude/Codex local/global의9셀, 설치된 runner 실제 실행|
|Windows platform smoke|Python3.12의10검사|
|변이 검증|별도 source 복사본에서 portable alias 보존을 제거하자4subcases가 실제 바이트 assertion에서 실패|
|모델 대표 해석|실제 Claude Opus5.5·Codex gpt-6.1-sol이 출처·오답·NOT TESTED/A2 PASS·재시도 의미를 구분|

모델 시험은 명시된 설치 문서 해석이다. Codex의 known reader 제약 응답을 PASS로 세지 않고 같은 텍스트 inline 입력 보정의 결과를 별도로 보존했다. Native 자동 skill discovery·실제 모델 앱의 전체cycle·통계적 준수율·비용 절감은 증명하지 않았다. 전체 Windows 회귀·Windows10/Server/ARM64도 미실행이다.
