# Phase 04 — 역할 packet과 headless reviewer 전달 관측

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Risk Level: L3
Status: OBSERVED_WITH_OPEN_ACCEPTANCE — reviewer 작은 native 진단 PASS, A4 전체 미판정
Evidence-Date: 2026-11-05

## 실행 경계와 고정 subject

독립 QA는 격리 consumer의 제품 시험으로 `sage review --packet-file`을 실행했다. 이는 엔진의 Phase 05 승인·review-loop·gate·waiver가 아니며, 실제 검토 대상을 승인한 실행도 아니다. packet은 파일 탐색·수정·tool 호출 없이 받은 역할 marker만 보고하라는 읽기 전용 진단이다. 제품 source/test 파일은 수정하지 않았고, 외부 메시지·commit/push·전역 설정 변경도 하지 않았다.

scratch는 `/Users/sejon/project/sage_project_worktree/overlay-context-phase04-role-1105a`이다. 현재 제품 source의 package/runtime/CORE/templates/schema 등 **378개 파일**을 `subject/`에 복사하고, 정렬된 파일 hash inventory의 digest를 고정했다.

- subject inventory digest: `ab4001f3cfa442b771dfbf492a0f6b036baa62d0c71865a2d2009a41de234bdf`.
- `subject-hashes.json`, `subject-id.txt`, `assessment.json`에 근거가 있다. 최종 분석 시 고정 사본 drift 0, 현재 작업 소스와의 차이 0이었다. git commit/release candidate digest와는 구분한다.
- Python: `/Users/sejon/project/sage_project_worktree/overlay-local-consumer-env/bin/python`.
- 제품 정상 `install --host codex --skill-scope project-local --force`와 `install --host claude --force`, 양 host `generate --kind hook --write`를 격리 consumer에 실행했다. 모두 exit0이며 `install-<host>.*`, `generate-<host>.*`에 결과가 있다.
- root 스킬 7종 × shared/personal **14 source**를 collector가 정상 반환하는 consumer다. reviewer와 implementer-a에도 shared/personal 고유 marker를 새로 만들었다. 사용자 실제 개인 파일은 복사하지 않았다.
- consumer profile은 기존 native 시험의 합성 fixture를 복사하여 이름과 host 설정을 진단용으로 지정했다. same-runtime 제품 경로를 시험하기 위해 이 fixture의 `cross_model.policy=off`, `options.cross_model=false`를 명시했다. 엔진 프로젝트 profile/gate 정책을 바꾼 것이 아니다.

## Reviewer CLI의 본문·refs·명시 역할 경계

`reviewer_packet`/실제 CLI는 packet에 reviewer shared/personal 본문을 **각 한 번** 추가했다. CLI stdout에 `SAGE_LOCAL_OVERLAY_REF`를 **한 번** 출력하며 실제 개인 source의 path/hash와 일치했다. 해당 reference는 CLI의 호출자에게 주는 영수증이며 모델 prompt에 같은 reference JSON을 추가한다는 뜻은 아니다.

| 구분 | 값 |
|---|---|
| 공유 marker | `ROLE_REVIEWER_SHARED_1105A` |
| 개인 marker | `ROLE_REVIEWER_PERSONAL_1105A` |
| 개인 source | `sage/asset_overrides.local/agents/reviewer.md` |
| 개인 SHA-256 | `9c1eaef13596fce73d12c0e3ae6a95e1461b4ac68147307385ab66c7ca748bb4` |
| worker marker / root source marker가 reviewer prompt에 새로 포함 | 각각 0개 |
| 완전 root catalog 본문 | 0개 |

진단 질문 자체에 `SAGE_OVERLAY_CATALOG_V2`라는 이름이 한 번 있다. 이를 실제 catalog 한 사본으로 세지 않았다. catalog wrapper/body와 root source marker 14종의 부재, 모델의 수신 보고를 별도로 확인했다.

실제 `sage review`가 생성한 새 process의 argv/stdin/cwd/선택된 비밀 아닌 role/host env만 `peer_recorder.py`가 기록하고, 본래 제품 command와 stdin을 그대로 실제 CLI에 넘겼다. 인증 내용이나 전체 env를 기록하지 않았다. command를 새로 작성하여 제품 controls를 대체하지 않았다. `peer-launch.json`에 두 host 모두 **`SAGE_OVERLAY_ROLE=reviewer`**, `SAGE_HOST=<실제 host>`가 있었다. generic agent_type 추론으로 reviewer를 선택한 것이 아니다.

## 실제 계정 native headless 결과

실행 형태는 `$PY -m sage review --packet-file <scratch>/packet.md --host <host> --root <scratch>/consumer --timeout 120`이다. 실행은 두 host 각각 실제 계정 모델 **진단 1회**로 제한했다. wrapper는 같은 host의 실제 launcher 기록이 있으면 재호출을 거부하도록 했다.

| host / CLI | 관측 model / session | 실제 결과 |
|---|---|---|
| Claude Code `2.1.318` | `claude-opus-5-5` / `f8639df2-0edb-4ac1-80c9-eef66c5754a3` | rc0; reviewer marker 2개 보고; `root_catalog_present=false`, `role_packet_only=true`; tool_calls=0 |
| Codex `0.166.0` | `gpt-6.1-sol` / `01a1abf9-62ef-7323-857c-3b5b64543e43` | rc0; 같은 marker 2개 보고; `root_catalog_present=false`, `role_packet_only=true`; tool_calls=0 |

Claude model/session은 native stream의 system init/result에서, Codex session은 native `thread.started`, model은 격리 session의 `turn_context.model`에서 확인했다. backend alias의 내부 provenance를 검증했다고 주장하지 않는다. 두 모델 모두 마지막에 `DIAGNOSTIC_ONLY`를 출력했다. CLI의 `REVIEWER_STATUS: COMPLETE`는 이 진단 프로세스의 정상 완료이며 엔진 변경의 검토 승인이나 Phase 05 종료를 의미하지 않는다.

제품 controlled launcher는 의도적으로 빈 `sage-peer-*` cwd에서 실행한다. Claude는 `--restricted --disallowedTools Agent Task --setting-sources= --strict-mcp-config --disable-slash-commands --no-session-persistence`, Codex는 read-only sandbox, strict config, `mcp_servers={}`, web search/memories/hooks/multi-agent disable을 사용했다. `REVIEWER_CONTROLS: full`, `REVIEWER_AUDIT: ok`를 확인했다. 따라서 이 실제 headless 경로의 catalog 0 관측은 **역할 env만으로 hook이 억제됐다는 native 단독 실험이 아니다**. 제품 launcher가 hooks/프로젝트 지침 자동 공급을 막는 격리 조건과 함께 성립한다. role env의 collector 억제는 아래 함수 경계 관측으로 구분한다.

첫 Codex CLI 시도는 상위 프로세스 host 표지가 없는 상태에서 `active_host=auto`의 기존 default가 claude로 해석되어 preflight rc2로 막혔다. 이때 Codex child/모델 호출은 없었다. `preflight-review.*`에 보존했다. fixture 호출 상위 env에 명시 `SAGE_HOST=codex`를 준 후 제품 CLI를 실행한 **실제 Codex 진단 1회**만 위 표에 포함했다. 이 fallback 관측을 새 catalog 전달 결함으로 분류하지 않았다.

## Worker loader/packet — 결정적 경계와 native 미실행

같은 consumer에서 실제 `sage overlay-local --kind agent --id implementer-a --root <consumer>`를 실행했다. exit0의 검증된 JSON `content`와 그때의 kind/id/path/hash를 사용하고, 기존 worker의 공유 본문을 함께 담은 역할 packet을 scratch에 작성했다. raw 개인 파일을 오류 후 대체로 읽거나 root 7종 catalog를 packet에 붙이지 않았다.

| 항목 | 관측 |
|---|---|
| 공유 worker marker | `ROLE_IMPLEMENTER_A_SHARED_1105A`, packet에 1회 |
| 개인 worker marker | `ROLE_IMPLEMENTER_A_PERSONAL_1105A`, packet에 1회 |
| 개인 source/ref | `sage/asset_overrides.local/agents/implementer-a.md`, `d6c79a916aa4ac4b46f84627a7f27b8ef217e69a40f2f4c0204c88c89918f5b6` |
| 다른 reviewer marker / root catalog | packet에서 각각 0개 |
| 명시 `SAGE_OVERLAY_ROLE=reviewer` 또는 `implementer-a`로 `overlay_context.current` 실행 | 두 host runtime 모두 `context=''`, issue 없음. root 14 source 입력 검증은 유지 |
| installed `.claude`, `.codex`, `docs/sage_harness`에 개인 role marker가 영구 삽입 | 0개 |

이 결과는 **loader/host가 작성한 worker packet과 함수 경계**까지만 입증한다. 실제 Claude Agent implementer-a child가 packet을 받아 적용하거나 자체 압축 뒤 복구한 native 실행은 **NOT_TESTED**다. host별 실제 모델 호출 한 번을 reviewer CLI 진단에 사용했고, 해당 제품 reviewer controls는 Agent/Task 실행을 금지한다. 같은 headless 호출에서 worker를 생성하여 이 제약을 바꾸지 않았다. 실제 Agent child, fork inherited context와 신규 packet의 구분, child 자체 압축 복구를 이 작은 진단의 PASS로 세지 않는다.

## 비용·원자료·종료 점검

| host | 제품 telemetry |
|---|---|
| Claude | new_input=2792, cached_input=7263, output=130, turns=1, tool_calls=0, wall_s=3, cost_usd=0.0263806 |
| Codex | new_input=5805, cached_input=9856, output=93, tool_calls=0, wall_s=12 |

이는 CLI가 관측한 이 작은 진단의 usage이며 전체 세션/서비스 총비용 보장은 아니다. Codex 인증은 격리 CODEX_HOME의 로컬 symlink로만 연결했고 종료 시 제거했다. `assessment.json`에서 남은 auth symlink 0, subject/current source drift 0, reference hash 일치, 개인 marker 설치본 유출 0을 확인했다. 전역 user 설정을 변경하지 않았다.

원자료는 scratch의 `setup_role.py`, `run_roles.py`, `run_codex_explicit.py`, `peer_recorder.py`, `assess_roles.py`, `subject-hashes.json`, `assessment.json`, `deterministic-receipts.json`, `worker-loader.*`, `worker-packet.json`, `<host>/peer-launch.json`, `<host>/peer.stdout`, `<host>/peer.stderr`, `<host>/review.*`다. 모델 입력/출력 파일에는 새 진단 marker만 사용했다. `packet.md`의 SHA-256은 `4b8d2cf97fc320456e6d3408e986c50a31cd6a810530a8b57d5de28c521d56a8`이며 실제 두 launcher prompt에 같은 packet 문자열이 포함됨을 확인했다.

## 수용 조건 추적

| 부분 항목 | 상태 | 범위 |
|---|---|---|
| headless reviewer 공유/개인 1회 본문·refs, 명시 role env | PASS | 실제 CLI launch + 두 실제 모델 작은 진단 |
| reviewer에 root catalog 신규 본문 0 | PASS | controlled headless 제품 경로 및 함수별 role 억제; native role hook 단독 인과 시험과 구분 |
| worker loader 자기 본문·refs/다른 역할과 분리 | PASS | 실제 loader + host packet 작성/함수 경계 |
| native Claude Agent worker의 packet 수신·적용/자체 압축 | NOT_TESTED | 이번 작은 진단 호출 예산/통제 범위 밖 |
| A4 전체 | NOT_TESTED | 이 문서만으로 중첩/반환·native worker/fork·전체 역할 수용을 대신 판정하지 않음 |

이 기록은 parent의 별도 중첩/압축 증거와 합쳐 검토할 부분 근거다. 최종 acceptance·Phase 05 승인·cycle 완료 판정은 수행하지 않았다.

## 최종04 집계 시점의 subject 차이

위 drift0은 해당 역할 시험 종료 시점 관측이다. 이후 Claude 예산/L1 호환 보완 뒤 최종 집계에서 보존 subject378개와 현재 소스를 비교하면7개 파일 차이가 있다: `sage/overlay_delivery.py`, `sage/commands/doctor.py`, `scripts/sage_harness/hooks/runtime/{overlay_context,hook_runtime}.py`, `scripts/sage_harness/hooks/tests/test_{doctor,overlay_runtime_delivery,overlay_delivery}.py`. 역할 packet/launcher 소스는 동일하지만 실제 계정 진단을 최종 후보에서 다시 실행하지 않았다. 최종 일반 회귀는 현재 runtime의 역할 억제 경계를 포함하며, 이것을 최종 후보 native Agent/실제 reviewer 재시험으로 승격하지 않는다. 최종 집계는 `overlay-context-evidence/phase04-final-assessment.json`이다.
