# SAGE - System for Agentic Governance & Engineering

[English](README.en.md)

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Claude Code와 Codex를 위한 결정론적 거버넌스 하네스입니다.** hook/MCP spec과 agent/skill host
render를 정본 입력으로 관리하고, drift를 검증하며, hook이 정책 위반을 실행 전에 차단합니다.

## 왜 SAGE인가

AI 코딩 에이전트는 빠르지만 plan 없이 고위험 파일을 수정하거나, PDCA 단계를 건너뛰거나, 생성물을
직접 고칠 수 있습니다. SAGE는 사람이 같은 지시를 반복하는 대신 다음 폐루프를 제공합니다.

```
spec 작성 -> 런타임 자산 생성 -> manifest 검증 -> hook 차단 -> 리뷰와 회고
```

- **spec SSOT**: hook, agent, skill, MCP 정의를 추적 가능한 문서로 관리합니다.
- **실행 게이트**: 위험도, PDCA phase, 리뷰 승인, 생성물 직접수정을 결정론적으로 검사합니다.
- **듀얼 호스트**: 같은 정책 core를 Claude Code와 Codex의 I/O 규약에 맞춰 실행합니다.
- **교차 모델 리뷰**: 현재 실행 중인 host가 아닌 peer runtime에 독립 리뷰를 맡길 수 있습니다.
- **감사 가능성**: manifest, phase 문서, review-loop, retro 기록을 저장합니다.

## 빠른 시작

요구사항은 Python 3.10+와 Git입니다. 설치 hook은 Windows에서도 bash 없이 동작합니다.

```bash
pipx install "sage-harness[schema]"

cd your-project
sage install --host codex --skill-scope project-local
# Codex에서 최초 설정: $sage-init
sage generate --kind hook --write --target codex
sage validate --kind all

# Claude Code를 쓰는 경우:
# sage install --host claude
# /sage-init
# sage generate --kind hook --write --target claude
```

공유 profile이 이미 있는 프로젝트에 합류했다면 `sage-init-local`만 실행합니다. 단계별 설명은
[한국어 퀵스타트](docs/quickstart.md), 설치 문제는 [문제 해결](docs/troubleshooting.md)을 참조하세요.

## Windows

`sage-hook.exe`가 7개 설치 hook을 Python으로 실행하므로 hook 실행에는 Git Bash나 WSL이 필요하지
않습니다.

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install "sage-harness[schema]"
sage doctor
```

표준 L2/L3 전달 흐름의 `scripts/verify-changes.sh`와 사용자 정의 `.sh` 회귀 테스트에는 Git Bash가
필요합니다. Windows에서 후자를 실행할 때는 `SAGE_BASH`로 인터프리터를 명시합니다.

## 동작 원리

```
hook / MCP specs                  sage generate       host assets
agent / skill host renders    <------------------>   .claude / .codex
          |                                               |
          +---- manifest hash <--- sage validate ---------+
          +---- blocked edit ----> sage absorb proposal
```

판단이 필요한 코드 작성과 리뷰는 AI가 담당하고, 무결성·단계·승인 경계는 SAGE가 코드로 검사합니다.
신뢰 경계와 fail-open/fail-closed 정책은 [Architecture](docs/ARCHITECTURE.md)에 있습니다.

## 핵심 흐름

### 자산 관리

| 종류 | 작성 흐름 | 대표 산출물 |
|---|---|---|
| hook | spec-first: `docs/sage_harness/hooks/{id}.md` | host hook 등록 + Python runtime |
| agent | render-first: 두 host render를 작성한 뒤 spec/claims 추출 | `.claude/agents`, `.codex/agents` |
| skill | render-first: 두 host render를 작성한 뒤 spec/claims 추출 | `.claude/skills`, `.codex/skills` |
| MCP | spec-first: `docs/sage_harness/mcps/{id}.md` | `.mcp.json`, `.codex/config.toml` |

생성된 파일을 직접 수정하면 write guard가 차단합니다. hook/MCP는 spec을 수정한 뒤 generate합니다.
agent/skill은 두 host render를 작성한 뒤 generate로 spec과 claims를 역추출합니다. 이미 생긴 차단
diff는 `sage absorb`로 spec patch 후보로 변환할 수 있습니다.

### PDCA와 리뷰

`sage-cycle`은 Phase 00-06을 구동합니다. `sage-plan`은 기획 00-02, `sage-team`은 구현 03-06,
`sage-review`는 Phase 05 리뷰와 적대적 반복을 담당합니다. `sage review-loop`는 라운드를 기록하고,
`sage retro`는 완료 후 놓친 패턴을 분석합니다.

긴급하거나 축약된 전달이 필요한 L2/L3 작업은 공유 profile에서 명시적으로 허용한 경우에만
`sage-cycle-fast`를 사용합니다. Fast Cycle도 실제 위험도, acceptance, 구현·검증, 독립 리뷰, 05/06,
write-back·retro·snapshot을 유지합니다. 대신 물리 문서는 00 composite Fast Plan + 05 + 06으로 줄이고,
01~04의 내용은 00에 포함합니다. 시작 전에 Fast level, 렌즈 수, 사유를 모두 받아야 하며 실행 이력은
커밋 대상인 `.sage/fast_cycle.jsonl`에 남습니다. 일반 `sage-cycle`은 Fast 상태를 직접 만들지 않습니다.

장수 브랜치에서는 `sage cycle set <stem>`으로 현재 사이클을 선언합니다. Phase 00이 없다면
`sage cycle set <stem> --create --risk L1|L2|L3`로 뼈대를 만든 뒤 내용을 채웁니다.
`sage-cycle` 우산은 이 명령을 중복 실행하지 않습니다. `sage-plan`이 stem 검증 뒤 선언하고,
`sage-team`이 재개 시 `sage cycle show`로 대조한 뒤 실제 완료 때 `sage cycle clear`로 해제합니다.
리뷰가 `BLOCKED`/`FAIL`이면 재개를 위해 선언을 유지합니다. env 선언은 파일 해제 뒤에도 남으므로
`unset SAGE_CYCLE_STEM`이 필요합니다.
`set B`는 `.sage/cycle.json` 포인터만 바꾸며 A의 문서·증거·감사를 수정하지 않습니다. 다시
`set A`하면 A의 판정이 복원됩니다.

### Profile

`sage/project-profile.yaml`은 팀이 공유하는 정책이고, Git에서 제외되는
`sage/project-profile.local.yaml`은 현재 머신의 host/model/vault capability입니다. 로컬 profile은
공유 risk나 review 정책을 완화할 수 없습니다.
`sage-init`과 `sage-profile-modify`는 Fast Cycle 활성화, L2/L3 최소 라운드·렌즈 후보, vault dashboard를
대화로 수집합니다. 기본값은 `enabled: false`입니다.

## 문서

| 목적 | 문서 |
|---|---|
| 처음 설치하고 실행 | [퀵스타트](docs/quickstart.md) |
| 명령과 옵션 확인 | [CLI 레퍼런스](docs/cli-reference.md) |
| profile 설정 | [Profile 레퍼런스](docs/profile-reference.md) |
| 오류 해결 | [문제 해결](docs/troubleshooting.md) |
| 설계와 신뢰 경계 | [Architecture](docs/ARCHITECTURE.md) |
| 생성 위치와 소유권 | [Artifacts](docs/ARTIFACTS.md) |
| 전체 문서 지도 | [문서 인덱스](docs/README.md) |

## 적합한 사용자

SAGE는 Claude Code 또는 Codex로 실무 저장소를 변경하면서, prompt 권고가 아니라 검증 가능한 정책과
독립 리뷰가 필요한 팀을 위한 도구입니다. 단순 prompt 모음이나 코드 생성 스니펫이 필요한 경우에는
과한 선택일 수 있습니다.

## 라이선스

Apache License 2.0입니다. 상업적 이용, 수정, 재배포가 가능하며 배포물에는 [LICENSE](LICENSE)와
[NOTICE](NOTICE)를 포함해야 합니다. `v0.9.71` 이전 배포분은 CC BY-NC-SA 4.0이 적용됩니다.
