# Changelog

새 릴리즈 노트는 반드시 한글로 작성합니다.

## Unreleased

- EGM 기반 구현 전 계획 맥락 검토를 추가했습니다. 명시한 계획·원천을 같은 호스트의 새 프로세스에서 검토하고 입력 해시·실제 사용량·원시 JSON을 기록합니다.
- 기본값은 비활성화이며, 검토 결과의 반영·보류·반박은 사람이 결정합니다. 기존 Phase04/05/06 승인 경계는 유지합니다.
- Claude·Codex의 표준/Fast 계획 흐름에 연결하고 한영 사용 문서를 정리했습니다. 검증 범위와 남은 한계는 [완료 기록](docs/plan_docs/06/egm-plan-review.md)에 구분했습니다.

## 1.3.8 — 2026-11-17

- Keep requirement sources visible through planning and QA; use approved contracts to derive expected results.
- Distinguish executed and skipped checks. Zero executions now report `NO_EVIDENCE` while existing exit codes remain unchanged.
- Preserve missing required evidence as `NOT TESTED` and keep Standard, Fast and rework interpretations aligned.
- Preserve project-owned verification runners during force installation on Windows when profiles use portable `/` spelling for the supported current/legacy paths.
- Update Korean/English manuals and installed framework guidance. See the [verification and upgrade notes](docs/plan_docs/06/q00-evidence-adoption.md) for scope and remaining limits.

Earlier release notes are preserved on [GitHub Releases](https://github.com/SeJonJ/SAGE/releases).
