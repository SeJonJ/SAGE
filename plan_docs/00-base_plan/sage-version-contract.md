# [Base Plan] 프로젝트 SAGE 버전 계약과 실행 불일치 알림

Cycle-Stem: `sage-version-contract`
Risk Level: L3
Status: PLANNED

## 1. Context

프로젝트 자산을 만든 SAGE 버전과 팀원이 실행하는 `sage`·`sage-hook` 버전이 다르면 같은 프로필과 훅이
서로 다른 의미로 해석될 수 있다. 현재 일부 manifest와 CORE render에는 버전이 기록되지만 프로젝트가
요구하는 버전과 런타임을 한 화면에서 비교하지 않는다.

## 2. Goal

- shared profile에 프로젝트 요구 SAGE 버전을 정확히 기록한다.
- 요구 버전, 설치/생성 영수증 버전, 현재 CLI/hook 버전을 구분한다.
- doctor, validate, SessionStart에서 불일치를 명확한 WARN/notification으로 노출한다.
- local profile은 요구 버전을 변경할 수 없게 한다.

## 3. Scope

- exact version 계약과 형식 검증
- manifest 설치 영수증 및 runtime `__version__` 비교
- 정정 명령이 포함된 진단 문구
- 설치 템플릿과 기존 프로젝트 호환

Out of scope: 자동 패키지 설치·다운그레이드, 원격 패키지 최신 버전 조회, semver 범위 solver.

## 4. Done Criteria

1. 신규 프로젝트는 설치한 SAGE 버전을 shared 요구 버전 기본값으로 가진다.
2. 세 버전 축이 doctor/validate 출력에서 구분된다.
3. SessionStart는 불일치를 한 번 알리되 세션을 차단하지 않는다.
4. local 요구 버전 선언은 스키마/ownership FAIL이다.
5. 버전 일치 시 불필요한 경고가 없다.
6. 세 번의 독립 headless 리뷰를 완료한다.
