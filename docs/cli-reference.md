# SAGE CLI 레퍼런스

[문서 인덱스](README.md) | 실행 환경의 정확한 옵션은 `sage <command> --help`

## 설치와 생성

| 명령 | 역할 |
|---|---|
| `sage install --host claude` | Claude Code framework, CORE hook, agent, skill 설치 |
| `sage install --host codex --skill-scope project-local` | Codex 자산과 저장소 로컬 CORE skill 설치 |
| `sage install --host codex --skill-scope global` | Codex 자산과 사용자 전역 CORE skill 설치 |
| `sage generate --kind hook --write --target HOST` | hook spec에서 host 등록, adapter, manifest stamp 생성 |
| `sage generate --kind mcp --write --target HOST` | MCP spec에서 host 설정 생성 |
| `sage generate --kind {agent,skill} --write` | 두 host render에서 spec과 claims를 역추출하고 정합화 |
| `sage generate --kind roster` | `profile.components`에서 implementer spec 생성 |
| `sage generate --kind roster --from-existing ID` | 기존 implementer 합성 렌더를 새 component identity로 승격 |

`generate`는 `--write`가 없으면 미리보기입니다. hook/MCP는
`--target claude|codex|both`로 host를 지정합니다. agent/skill은 항상 두 host render를 요구하는
render-first 흐름이므로 `--target`으로 범위를 줄이지 않습니다.

## 검증과 진단

| 명령 | 역할 |
|---|---|
| `sage validate` | 기본 `hook` 범위의 hash, staleness, regression, profile 의미 검사 |
| `sage validate --kind all` | hook, agent, skill, MCP 전체 자산 검사 |
| `sage validate --check` | 회귀 명령을 실행하지 않는 빠른 정합성 검사 |
| `sage validate --schema` | manifest와 profile JSON Schema 검사 |
| `sage validate --strict` | bootstrap/schema/overlay/profile drift 등 지정된 advisory check를 실패로 승격 |
| `sage doctor` | Python, hook entry, host, reviewer, profile, optional capability 진단 |
| `sage models --host HOST` | 로컬에서 확인 가능한 model 후보와 검증 수준 표시 |
| `sage asset-check --gate` | 자산 변경의 auto-approve 가능 여부를 CI exit code로 반환 |

## 자산 유지보수

| 명령 | 역할 |
|---|---|
| `sage absorb --kind K --id ID` | 직접 수정 diff를 spec patch 후보로 변환 |
| `sage sync-overlays` | CORE overlay와 governance routing 관리 블록 재수렴 |
| `sage change "설명"` | 변경 의도에 맞는 generate/absorb 경로 안내 |
| `sage feedback` | `sage-feedback ::` 마커 조회 |
| `sage feedback --release-gate` | 미해결 blocking feedback으로 릴리즈 차단 |
| `sage override --reason R --ttl T` | 허용된 gate의 기간 제한 우회와 감사 기록 |
| `sage acceptance-waiver {grant,list,revoke}` | exact L3 acceptance 운영 유예 관리 |

## 리뷰와 루프

| 명령 | 역할 |
|---|---|
| `sage review` | 새 same-runtime headless reviewer 실행 |
| `sage cross-check --packet-file FILE` | 반대 runtime의 cross-model reviewer 실행 |
| `sage review-loop open` | review loop와 감사 run 시작 |
| `sage review-loop round` | finding, 반박, 수정 결과 라운드 기록 |
| `sage review-loop next` | 결정론적 계속/종료 권고 |
| `sage review-loop close` | `--result APPROVED|BLOCKED`로 loop 종료 |
| `sage retro --feature STEM` | 완료 사이클 회고 노트와 distillation 입력 생성 |
| `sage retro --check NOTE` | 회고 노트가 빈 템플릿이 아닌지 검사 |

## 지식과 컨텍스트

| 명령 | 역할 |
|---|---|
| `sage knowledge scan` | 개발 전 Obsidian vault 검색 결과를 `.sage/knowledge_scan.md`에 기록 |
| `sage knowledge write-back --append-log` | 완료 지식을 vault 노트와 `wiki/log.md`에 반영 |
| `sage context snapshot --cycle-stem STEM --phase ID` | 완료 phase의 profile, manifest, 문서 hash packet 저장 |
| `sage context restore --snapshot PATH` | snapshot과 현재 source를 검증하고 재개 briefing 생성 |

## CI 권위

| 명령 | 역할 |
|---|---|
| `sage authority inspect` | base/head 변경과 최고 위험도 검사 |
| `sage authority attest` | exact PDCA evidence attestation 생성 |
| `sage authority gate` | 보호된 CI에서 attestation과 현재 변경을 결속해 판정 |

## 공통 종료코드

명령별 세부 계약은 `--help`와 출력이 우선합니다. 일반적으로 `0`은 PASS, `1`은 검증 FAIL,
`2`는 도구·게이트 오류 또는 BLOCK, `3`은 STALE을 의미합니다. Hook에서는 `0`이 통과,
`2`가 차단입니다.
