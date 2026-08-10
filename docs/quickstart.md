# SAGE 퀵스타트

[English](quickstart.en.md) | [README](../README.md)

## 1. 설치

Python 3.10+와 Git이 필요합니다. schema 검증까지 포함한 pipx 설치를 권장합니다.

```bash
pipx install "sage-harness[schema]"
sage --version
```

Windows에서는 `py -m pip install --user pipx`와 `py -m pipx ensurepath`로 pipx를 먼저 설치할 수
있습니다. 설치 hook은 `sage-hook.exe`로 실행되며 bash가 필요하지 않습니다.

## 2. 프로젝트에 설치

```bash
cd your-project

# Codex: CORE skill을 저장소에 함께 설치
sage install --host codex --skill-scope project-local

# 또는 Claude Code
sage install --host claude
```

Codex CORE skill을 사용자 전체 프로젝트에서 공유하려면 `--skill-scope global`을 선택할 수 있습니다.
scope는 반드시 명시해야 하며 `sage doctor`가 중복 사본을 진단합니다.

## 3. Profile 작성

- Claude Code: `/sage-init`
- Codex: `$sage-init`
- 이미 공유 profile이 있는 팀원: `sage-init-local`

최초 init은 공유 정책 `sage/project-profile.yaml`과 Git에서 제외되는 현재 머신 capability
`sage/project-profile.local.yaml`을 분리해 작성합니다.

## 4. Hook 생성과 검증

```bash
# Codex
sage generate --kind hook --write --target codex
# Claude Code는 --target claude, 양쪽은 --target both
sage validate --kind all
sage doctor
```

`validate`가 STALE을 보고하면 출력이 지시한 kind를 다시 generate합니다. FAIL은 파일 누락, schema 오류,
실행 스모크 실패 같은 실제 계약 위반이므로 원인을 해결한 뒤 다시 실행합니다.

## 5. 개발 사이클 시작

- 전체 PDCA: `sage-cycle`
- profile이 허용한 L2/L3 축약 절차: `sage-cycle-fast`
- Fast composite 00 작성: `sage-plan-fast`
- Fast 구현·리뷰·종료: `sage-team-fast`
- 기획 00-02: `sage-plan`
- 구현 03-06: `sage-team`
- 자산 추가·수정: `sage-asset`
- 개발자 피드백 처리: `sage-feedback`

고위험 변경은 Phase 00의 정확한 `Risk Level: L1`, `L2`, `L3` 선언과 필요한 phase 문서를 먼저 요구합니다.
Phase 05 리뷰가 APPROVED되기 전에는 Phase 06 완료 보고가 차단됩니다.
Fast Cycle은 01~04 문서를 생략하는 대신 그 내용을 체크리스트가 있는 composite 00에 포함하며,
Fast level·렌즈 수·사유를 모두 받기 전에는 문서나 감사를 쓰지 않습니다.

## 다음 문서

- [CLI 레퍼런스](cli-reference.md)
- [Profile 레퍼런스](profile-reference.md)
- [문제 해결](troubleshooting.md)
