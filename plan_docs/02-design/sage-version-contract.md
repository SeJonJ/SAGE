# [Design] 프로젝트 SAGE 버전 계약과 실행 불일치 알림

Cycle-Stem: `sage-version-contract`

## 1. Version Axes

- required: shared `sage.required_version`
- installed/generated: manifest의 `sage_version`과 `generator_version`
- runtime: import된 package의 `sage.__version__`

exact 문자열 비교를 사용한다. 범위 해석 라이브러리를 추가하지 않으며 버전 형식은 숫자 점 구분과 선택적
pre-release/build suffix만 허용한다.

## 2. Shared Checker

순수 `version_contract_issues(profile, manifest, runtime_version)`가 구조화된 결과를 반환하고 doctor,
validate, hook entry가 같은 판정을 사용한다. 각 caller는 출력 채널만 다르게 렌더링한다.

## 3. SessionStart

hook entry는 session-start hook dispatch 전에 shared compiled profile과 manifest를 읽어 버전 상태를 확인한다.
불일치 시 stderr 또는 host notification 채널에 한 번 출력하고 원래 hook 실행은 계속한다. parse 오류는 기존
gate 정책을 따르며 버전 checker가 오류를 숨기지 않는다.

## 4. Tests

- required/install/runtime 완전 일치
- 각 축 단독·복합 불일치
- manifest 없음/legacy key 없음
- invalid version 형식
- doctor/validate/Claude/Codex SessionStart 메시지 parity
