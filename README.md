# SAGE - System for Agentic Governance & Engineering

[English](README.en.md)

[![CI](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml/badge.svg)](https://github.com/SeJonJ/SAGE/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/sage-harness)](https://pypi.org/project/sage-harness/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/sage-harness/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**Claude Code나 Codex 같은 AI 코딩 에이전트가 계획 없이 위험한 코드를 고치거나, 리뷰 없이 "완료"라고
보고하지 않도록 자동으로 확인하고 막는 도구입니다.**

## 왜 필요한가

AI 에이전트에게 "계획부터 세우고, 위험한 파일은 조심히 다루고, 꼭 리뷰를 받아라"라고 매번 말해도 그
지시는 잊히거나 생략됩니다. SAGE는 그 규칙을 자동으로 확인하는 장치(hook)로 만듭니다.

- **계획 없이 위험한 파일을 고치려 하면** → 먼저 계획 문서를 쓰라고 막습니다.
- **리뷰 없이 "완료됐다"고 보고하면** → 승인된 리뷰가 있는지 확인하고 없으면 막습니다.
- **AI가 자동 생성된 설정 파일을 직접 고치면** → 그 원본 정의를 고치도록 안내합니다(직접 고치면 다음
  생성 때 덮어써지므로).
- **한 AI가 자기가 짠 코드를 자기가 검토하면** → 반대 모델(Claude ↔ Codex)에게 독립적으로 검토를
  맡길 수 있습니다.

이 확인들은 AI의 "판단"이 아니라 코드가 "결정론적으로" 검사합니다 — 같은 상황이면 항상 같은 결과가
나오고, 사람이 매번 다시 설명할 필요가 없습니다.

## 빠른 시작

요구사항은 Python 3.10+와 Git입니다.

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

공유 profile이 있는 프로젝트에 합류했다면 `sage-init` 대신 `sage-init-local`만 실행합니다. 자세한
단계는 [퀵스타트](docs/quickstart.md), 오류는 [문제 해결](docs/troubleshooting.md)에 있습니다.

## SAGE 1.0의 주요 기능

| 하고 싶은 일 | 명령 또는 기능 |
|---|---|
| 지금 프로젝트에서 SAGE를 쓸 수 있는지 확인 | `sage status` |
| 특정 경로가 왜 차단되는지 확인 | `sage explain --path PATH` |
| 리뷰·우회·유예 감사 기록 조회 | `sage audit show` |
| 정의와 생성 자산의 무결성 검사 | `sage validate --kind all` |
| 다른 SAGE 버전으로 안전하게 이동 | `sage upgrade --check` → `sage upgrade --apply` |
| 설치한 프로젝트·전역 자산 제거 | `sage uninstall --check` → `sage uninstall --yes` |
| 계획·구현·독립 리뷰·완료 증거 결속 | 표준 PDCA, Fast Cycle, Done Criteria |

`status`, `explain`, `audit show`, `upgrade --check`, `uninstall --check`는 읽기 전용 진단입니다.
자동화용 `--json`, 전체 옵션과 종료 코드는 [CLI 레퍼런스](docs/cli-reference.md)를 참조하세요.

## 지원 환경

SAGE의 일반 CLI와 설치 hook은 Python 3.10+에서 동작하며 Windows에서도 bash가 필요 없습니다. 다만
`scripts/verify-changes.sh`와 사용자 정의 `.sh` 테스트에는 Git Bash가 필요합니다.

`sage uninstall`의 **자동 제거 지원 범위**는 더 좁습니다. 파일을 지우는 기능이므로 검증되지 않은
환경에서는 추측해서 실행하지 않고 첫 변경 전에 멈춥니다.

| 환경 | 일반 CLI·hook | `sage uninstall` |
|---|:---:|---|
| Linux | 지원 | 자동 제거 지원 |
| macOS | 지원 | 자동 제거 지원 |
| Windows 11 데스크톱 workstation, x64, 64-bit Python, 로컬 NTFS | 지원 | 자동 제거 지원 |
| Windows 10 데스크톱 | 지원 | 자동 제거 후순위; 현재는 검증된 계획과 수동 정리 목록 제공 |
| Windows Server·도메인 컨트롤러 | 정식 지원 범위 밖 (직접 검증하지 않음) | 자동 제거 미지원; 계획 기반 수동 목록 제공 |
| 32-bit Python, native ARM64 Python, 비 NTFS·네트워크·UNC 경로 | 환경별 제한 | 자동 제거하지 않음; `--check`로 계획 확인 가능 |

NTFS는 일반적인 Windows 로컬 디스크의 기본 파일 시스템입니다. **동작할 수 있다는 것과 정식으로
지원한다는 것은 다릅니다** — 범위 밖 환경에서 일반 CLI가 도는 경우가 있어도 그 동작을 약속하지 않고,
직접 검증하지도 않습니다. Windows 11 데스크톱의 자동 제거는 그 SKU에서 **실제로 실행해
검증했습니다** — Windows Server 결과로 갈음하지 않았습니다. 두 종류의 거부 화면과 자세한 판정은
[CLI 레퍼런스](docs/cli-reference.md)와 [문제 해결](docs/troubleshooting.md)에 있습니다.

Windows 설치 예시입니다. `sage-hook.exe`가 hook을 실행하므로 Git Bash나 WSL은 필요 없습니다.

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install "sage-harness[schema]"
sage doctor
```

Windows에서 `.sh` 테스트를 실행할 때는 `SAGE_BASH`로 Git Bash 경로를 명시합니다.

## 1.0으로 업그레이드

0.9.x에서 1.0으로 이동할 때는 패키지를 먼저 올린 뒤 프로젝트 자산을 점검·적용합니다.

```bash
pipx upgrade sage-harness
sage upgrade --check
sage upgrade --apply
sage status
```

`--check`는 계획만 보여 줍니다. `--apply`는 transaction이라 실패하면 되돌리고 자동 downgrade는
없습니다.

## 안전하게 제거

먼저 실제 프로젝트별 계획을 확인한 뒤 제거합니다. 패키지 자체는 별도로 지웁니다.

```bash
sage uninstall --check
sage uninstall --yes
pipx uninstall sage-harness
```

자동 제거가 지원되지 않는 환경에서도 두 명령은 실제 경로를 `STRIP`(공유 파일에서 SAGE 부분만
제거)·`DELETE`·`PRESERVE`·`BLOCK`으로 나눠 보여 줍니다. 대상은 host·scope·프로젝트
위치·`CODEX_HOME`에 따라 달라지므로 고정 목록을 여기 싣지 않습니다. 출력된 목록을 따르되
`PRESERVE`와 `BLOCK`은 지우지 마세요 — 손 대는 법은 [문제 해결](docs/troubleshooting.md)에 있습니다.

## 어떻게 동작하는가

SAGE는 두 종류의 파일을 나눠서 관리합니다 — **사람이 고치는 정의 파일**과, 그로부터 자동으로
만들어져 **AI가 실제로 읽는 실행 파일**입니다.

```
정의 파일 (사람이 고침)         sage generate       실행 파일 (AI가 읽음)
hook / agent / skill spec    <------------------>   .claude / .codex
            |                                                 |
            +---- 확인 --- sage validate ---------------------+
            +---- 직접 고치려 하면 ----> 정의 파일을 고치라고 안내
```

정의 파일을 고치고 `sage generate`를 실행하면 실제 AI가 읽는 실행 파일이 자동으로 갱신됩니다. 두
파일이 어긋나면(직접 고쳤거나 갱신을 깜빡했으면) `sage validate`가 잡아냅니다. AI가 실행 파일을 직접
고치려 하면 SAGE가 막고, 대신 정의 파일을 고치도록 안내합니다.

판단이 필요한 코드 작성과 리뷰는 AI가 담당하고, 무결성·단계·승인 경계는 SAGE가 코드로 검사합니다. 더
자세한 신뢰 경계와 실패 정책은 [Architecture](docs/ARCHITECTURE.md)에 있습니다.

## 개발 절차

- **PDCA** — 계획 → 구현 → 독립 리뷰 → 완료보고를 결속합니다.
- **완료 기준(Done Criteria)** — 요구별 증거를 추적하고, 기준이 바뀌면 영향받은 단계를 다시
  검증합니다.
- **profile** — 팀 공유 정책과 개인 환경 설정을 분리합니다.
- **Fast Cycle** — 명시적으로 켠 경우 문서 수를 줄이되 전환 과정을 감사 기록에 남깁니다.
- **조기 완료 승인** — 사용자가 남은 위험을 명시적으로 인수했을 때만 일반 승인과 구분해 기록합니다.

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
