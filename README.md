# SAGE - System for Agentic Governance & Engineering

[English](README.en.md)

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Claude Code나 Codex 같은 AI 코딩 에이전트가 계획 없이 위험한 코드를 고치거나, 리뷰 없이 "완료"라고
보고하지 않도록 자동으로 확인하고 막는 도구입니다.**

## 왜 필요한가

AI 에이전트에게 "먼저 계획을 세우고, 위험한 파일은 조심히 다루고, 꼭 리뷰를 받아라"라고 매번 말해줘도
그 지시는 결국 잊히거나 생략되기 쉽습니다. SAGE는 이런 규칙을 사람이 반복해서 말하는 대신, 자동으로
확인하는 장치(hook)로 만듭니다.

- **계획 없이 위험한 파일을 고치려 하면** → 먼저 계획 문서를 쓰라고 막습니다.
- **리뷰 없이 "완료됐다"고 보고하면** → 승인된 리뷰가 있는지 확인하고 없으면 막습니다.
- **AI가 자동 생성된 설정 파일을 직접 고치면** → 그 원본 정의를 고치도록 안내합니다(직접 고치면 다음
  생성 때 덮어써지므로).
- **한 AI가 자기가 짠 코드를 자기가 검토하면** → 반대 모델(Claude ↔ Codex)에게 독립적으로 검토를
  맡길 수 있습니다.

이 확인들은 AI의 "판단"이 아니라 코드가 "결정론적으로" 검사합니다 — 같은 상황이면 항상 같은 결과가
나오고, 사람이 매번 다시 설명할 필요가 없습니다.

## 빠른 시작

요구사항은 Python 3.10+와 Git입니다. 설치 hook은 Windows에서도 bash 없이 동작합니다.

먼저 SAGE 자체를 설치합니다.

```bash
pipx install "sage-harness[schema]"
cd your-project
```

그다음 **쓰고 있는 AI 도구에 맞는 쪽 하나만** 따라 하세요. 두 쪽 다 실행할 필요는 없습니다.

### Codex를 쓰는 경우

```bash
sage install --host codex --skill-scope project-local
```

설치가 끝나면 **Codex 안에서** `$sage-init`을 실행해 이 프로젝트의 설정(profile)을 대화로 채웁니다.
그다음 터미널로 돌아와 마무리합니다.

```bash
sage generate --kind hook --write --target codex
sage validate --kind all
```

### Claude Code를 쓰는 경우

```bash
sage install --host claude
```

설치가 끝나면 **Claude Code 안에서** `/sage-init`을 실행해 이 프로젝트의 설정(profile)을 대화로
채웁니다. 그다음 터미널로 돌아와 마무리합니다.

```bash
sage generate --kind hook --write --target claude
sage validate --kind all
```

공유 profile이 이미 있는 프로젝트에 합류했다면 `sage-init` 대신 `sage-init-local`만 실행합니다.
더 자세한 단계는 [퀵스타트](docs/quickstart.md), 설치 중 오류는 [문제 해결](docs/troubleshooting.md)을
참조하세요.

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

## 어떻게 동작하는가

SAGE는 두 종류의 파일을 나눠서 관리합니다 — **사람이 고치는 정의 파일**과, 그로부터 자동으로 만들어져
**AI가 실제로 읽는 실행 파일**입니다.

```
정의 파일 (사람이 고침)          sage generate        실행 파일 (AI가 읽음)
hook / agent / skill spec    <------------------>   .claude / .codex
          |                                                |
          +---- 확인 --- sage validate ---------------------+
          +---- 직접 고치려 하면 ----> 정의 파일을 고치라고 안내
```

정의 파일을 고치고 `sage generate`를 실행하면 실제 AI가 읽는 실행 파일이 자동으로 갱신됩니다. 두 파일이
어긋나면(직접 고쳤거나 갱신을 깜빡했으면) `sage validate`가 잡아냅니다. AI가 실행 파일을 직접 고치려
하면 SAGE가 막고, 대신 정의 파일을 고치도록 안내합니다.

판단이 필요한 코드 작성과 리뷰는 AI가 담당하고, 무결성·단계·승인 경계는 SAGE가 코드로 검사합니다.
더 자세한 신뢰 경계와 실패 정책은 [Architecture](docs/ARCHITECTURE.md)에 있습니다.

## 더 알아보기

이 외에도 SAGE는 계획→구현→리뷰→완료보고로 이어지는 PDCA 절차, 팀/개인 설정을 나누는 profile, 급한
작업을 위한 축약 절차(Fast Cycle) 등을 제공합니다. 실제로 써보면서 필요한 부분을 아래 문서에서
찾아보세요 — 처음부터 다 알아야 하는 것은 아닙니다.

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
