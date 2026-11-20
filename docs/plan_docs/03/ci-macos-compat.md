# CI 구현 소유권과 검증 계획

Cycle-Stem: ci-macos-compat
Document-Language: ko
Done-Criteria-Revision: 1

브랜치 chore/ci-macos-compat는 완료 EGM commit0081e58을 기반으로 한다. 소유 파일은 ci.yml, 새 macos-compat.yml, 기존 test_release_readiness.py의 검증 보완, 관련 한영 release-readiness 문서/검증 인덱스와 이 cycle 기록이다. runtime·설치 templates·기존 publish.yml·Windows job은 변경하지 않는다.

검증 순서: 기존 readiness baseline → 요구 기반 실패 테스트 → YAML 구현 → 표적/전체 회귀·공식 actionlint·검증 Bash 실제 실행 → macOS Python3.10/3.11의 기존 smoke/race/core 실제 실행 → 새 맥락 읽기 전용 검토 → 완료 기록·커밋/푸시. 기존 테스트를 삭제하지 않고 유효 matrix와 수동 복원 합집합을 검증한다. 원격 GitHub 실행은 아직 수행하지 않았으며 main 미반영/미실행을 PASS로 바꾸지 않는다.
