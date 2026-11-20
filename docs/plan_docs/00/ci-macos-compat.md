# CI macOS 호환성 검사 실행 시점 분리

Cycle-Stem: ci-macos-compat
Document-Language: ko
Done-Criteria-Revision: 1
Risk Level: L3
Base-Commit: 0081e58d431c9e06772056c3e4e0b77d791bfc26

## 배경과 사용자 결정

2026-11-20 사용자는 EGM cycle/문서의 커밋·푸시 후 CI 변경을 별도 커밋·푸시하도록 승인했다. 일반 PR/main CI에서 macOS Python3.10·3.11 제거 검증 조합을 제외하고 배포 직전 수동 검사로 보존한다. Ubuntu3.10/3.11/3.12와 macOS3.12, 나머지 검사를 유지한다. 기존 runner 미배정은 코드 실패와 구분하며 실행 빈도 조정이 runner 용량을 보장하지 않는다.

## 범위와 권위

일반 matrix의 두 조합 제외, 새 workflow_dispatch 호환성 검사2조합, full candidate SHA 결속, 한영 운영 안내와 검증을 포함한다. 테스트 코드·검사 내용·Windows 승인 조건·기존 PyPI publish 흐름은 유지한다. 엔진 자체 gate/review-loop/waiver를 승인 권위로 쓰지 않는다. 새 문맥 독립 검토와 일반 테스트를 근거로 판단한다. 원격 GitHub 실행/main 병합·릴리스는 이번 구현 검증과 구분한다.

## 5. Done Criteria

- [x] C01: 기존 테스트와 나머지 CI 작업·Windows 제한을 유지한다.
- [x] C02: 일반 제거 검증은 Ubuntu3개+macOS3.12의4조합이다.
- [x] C03: 수동 검사는 macOS3.10/3.11만 실행하며 기존 제거 검사를 보존한다.
- [x] C04: 후보40자리 SHA를 먼저 검증하고 checkout된 동일 commit만 검사한다.
- [x] C05: 검사 구성·거부 경로·두 Python 실제 제거 검사와 전체 회귀를 검증한다.
- [x] C06: 한영 안내가 수동 실행/배포의 경계를 정확히 설명한다.

## 6. Done Criteria Revision Log

- 1: 사용자 승인한 실행 시점 분리와 기존 검증 보존 범위를 최초 작성했다.
