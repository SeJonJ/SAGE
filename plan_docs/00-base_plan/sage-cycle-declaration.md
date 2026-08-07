# [Base Plan] SAGE 사이클 선언 통로 — `.sage/cycle.json`

Cycle-Stem: `sage-cycle-declaration`
Risk Level: L3
Status: DESIGN

## 1. Context

게이트는 편집마다 "이 편집이 어느 사이클인가"를 판정한다. 재료는 둘뿐이다.

| 편집 대상 | stem 출처 | 정확한가 |
|---|---|---|
| phase 문서 | 파일명 + `Cycle-Stem:` 줄 | 정확. 위조 불가 |
| 소스 코드 | git 브랜치 이름 마지막 조각 | 브랜치를 사이클마다 딸 때만 |

ChatForYou 는 `chatforyou_v2_sage` 하나로 여러 달·여러 사이클을 돈다. 모든 소스 편집이 존재하지
않는 사이클에 결속돼 00~03 을 다 써도 "PDCA 문서 없음" 으로 막힌다.

탈출구인 `SAGE_CYCLE_STEM` env 는 결함이 셋이다(실측).

```
SAGE_CYCLE_STEM=leftover-stem  bash run-all.sh   → rc=1, 실패 17건
env -u SAGE_CYCLE_STEM         bash run-all.sh   → rc=0, 실패 0건
```

1. 자식 프로세스를 전부 따라간다(위 17건)
2. 셸이 사이클보다 오래 산다 → 끝난 사이클에 결속
3. 조회 통로가 없다 → 남아 있다는 사실이 안 보인다

## 2. Goal

`sage cycle use | show | clear` — 파일 하나를 쓰고, 읽고, 지운다. env 는 폐기하지 않고 위에 둔다.

## 3. 범위 원칙

위키 `SAGE - 앞으로 개발할 내용` §환경 가변성 인정 원칙을 적용한다. 판정 질문은 하나다 —
**"이게 없었을 때도 있었나?"**

| 분류 | 처분 |
|---|---|
| 이 기능이 만든 결함 | 잡는다. 안 잡으면 출하가 순손실이다 |
| 기존 사각 · 구성 의존 · 개선 사항 | 인정하고 §6 에 사실만 기록 |

이 사이클의 앞선 시도가 독립 리뷰 7라운드 연속 FAIL 했고, 3R~7R 다섯 라운드가 전부 한 항목이었다 —
CLI 와 게이트의 root 해석 차이. 원래 설계가 저장 위치를 **유추**로 정한 것이 뿌리다("override grant 를
저장소 밖으로 옮긴 것과 같은 구조"). 그 유추가 머신 공용 위치를 들여왔고, 공용 위치는 "어느 저장소
것인가"를 키로 표시해야 하며, 그 키는 CLI 와 게이트가 root 에 합의해야 성립한다. **그 합의는 원리적으로
불가능하다** — 게이트 root 는 hook 실행 시점 호스트 env 로 정해지고 CLI 는 그걸 볼 수 없다.
이번 설계는 합의를 포기하고 §6-K1 로 인정한 뒤, 어긋났을 때 **보이게** 한다.

## 4. 결정

### D1 — root 는 SAGE 자신의 표식, `realpath` 정규화

`sage install` 이 만드는 `<dest>/docs/sage_harness/.manifest.json` 이 "여기가 SAGE 프로젝트다"의
정의다. 가장 가까운 조상을 찾되 시작 경로를 `realpath` 로 정규화한다. 표식이 없으면 **거부**한다.

측정: 현행 `abspath` 는 symlink 8갈래 중 **4갈래에서 틀린다**. 최악은 "저장소 밖에서 하위로 symlink"
로 `None` 을 돌려줘 **정상 프로젝트를 거부**한다. `realpath` 는 8/8.

이 방식을 고르는 이유는 게이트와의 합의가 아니라(불가능) **root 와 `.gitignore` 앵커가 일치한다는
것**이다 — `install` 이 `.gitignore` 를 쓰는 `dest` 와 manifest 의 `dest` 가 같다.

**주장하지 않는 것**: "게이트 root 는 항상 이 표식을 갖는다". 게이트의 실제 전제조건은
`sage/project-profile.{yaml,json}` 쌍이고 manifest 없이도 게이트는 돈다. 그래서 D5 가 필요하다.

### D2 — 선언은 `<root>/.sage/cycle.json`

`install` 의 `/.sage/*` 관리 블록이 덮는다. env 가 아니므로 자식으로 안 새고, 파일이므로 조회할 수
있다. **탐색하지 않는다** — 상위 탐색이 앞선 시도 7R 실패의 직접 원인이었다(쓰기 자리가 gitignore
앵커 밖으로 나가 커밋 대상이 됐다).

측정: 정상 설치는 덮인다(`check-ignore` rc=0). 규칙·블록이 사라진 상태는 덮이지 않지만
`sage install --force` 로 실제 복구된다. 마커 자체 손상만 복구 불가인데 그때는 규칙이 남아 덮여 있다.
→ **"안 덮임 + 복구 불가" 조합은 없다.**

### D3 — 우선순위: `SAGE_CYCLE_STEM` > 파일 선언 > 브랜치 leaf 추론

env 는 프로세스 1회용이라 범위가 더 좁고 CI 에서 정당하다. `use`·`show` 는 env 가 이기는 사실을
화면에 적는다.

### D4 — 완결 사이클 차단이 선언에도 적용된다 (조건 교체)

env 선언은 셸과 함께 죽어 무해했다. 파일은 세션을 넘겨 살아남으므로 3주 전 선언이 그 차단을
꺼버린다(실측: exit 0, 출력 0바이트).

```python
# 이전
if (_DECLARED_SOURCE not in source and _INFERRED_SOURCE in source
        and _cycle_closed(binding["stem"], cfg, snapshot)):
# 이후
if not _phase_only_change(event, cfg) and _cycle_closed(binding["stem"], cfg, snapshot):
```

`_phase_only_change` = 변경이 **1건 이상이고 전부** phase 문서. 신설한다.

- **`_is_phase_write` 를 쓰지 않는다.** 그건 `any()` 이고, 면제 조건에 넣으면 소스 편집에 문서 한 줄만
  섞어 차단 전체를 끌 수 있다. 유일 호출부인 PDCA 진입 조건에서는 `any` 가 **넓게 잡는** 안전한
  방향이라 그대로 옳다 — 같은 술어를 면제에 쓰면 방향이 뒤집힌다.
- "선언 면제만 철회" 는 **무동작**이다 — phase 변경이 있으면 `resolve` 가 `branch-leaf` 를 source 에
  넣지 않아 `_INFERRED_SOURCE in source` 가 이미 False 다. 조건 전체를 갈아야 한다.
- 변경 0건은 면제가 아니다 — 어댑터 추출 실패가 면제를 사면 안 된다.

**차단 사유가 결속 출처를 갈라 말한다**(`선언된` / `브랜치에서 추론한`). 고정 문구는 조건이 추론
출처였을 때만 참이었고, 지금은 낡은 선언 때문에 막힌 사용자를 브랜치로 보내 D9 를 정면으로 무효화한다.

### D5 — `use` 는 확인한 것만 말한다

1. 선언한 stem, env 가 이기면 그 사실
2. **절대경로** root·파일 위치 — §6-K1 이 어긋났을 때 사람이 볼 수 있는 유일한 단서
3. `git check-ignore -q` 결과. 안 덮이면 경고하고 `sage install --force` 를 안내한다(복구되는 상태다)
4. `sage/project-profile.{yaml,json}` 부재 시 경고 — 표식과 게이트 전제조건이 다르다는 사실의
   유일한 노출 지점

### D6 — 표시·감사는 읽은 자리만 말하되, 통로는 갈라 말한다

"`sage cycle use` 로 선언했다" 는 확인 불가능한 단언이다(파일은 프로젝트 안에 있어 무엇이든 쓸 수
있다). `SAGE_CYCLE_STEM 선언` / `.sage/cycle.json 선언` 으로 **읽은 자리만** 적는다.
어댑터가 `cycle_stem_origin`(`env`/`cli`)을 이벤트에 싣고 core 가 판정에 스탬프한다 — 순수 판정
모듈(`cycle_binding`)은 건드리지 않는다.

**감사 dedupe 키에 기원을 포함한다.** 빼면 한 세션에서 두 통로를 쓸 때 먼저 걸린 쪽만 남아, 세션을
넘겨 살아남는 파일 선언이 일회성 env 선언으로 기록된다 — 구분하려고 넣은 필드가 뒤집힌다.

### D7 — 선언 파일은 write-guard 대상이다

재현된 fail-open: 편집 도구로 `.sage/cycle.json` 을 쓰면 어떤 risk 글롭에도 안 걸려 PDCA 블록 진입
전에 통과하고(exit 0, 0바이트), 그 다음 L2 소스 편집이 그 선언으로 통과한다.

**env 통로에서는 불가능했다** — hook 프로세스는 호스트가 띄우고 에이전트의 자식 셸은 부모 환경을
못 바꾼다. 파일로 옮기면서 생긴 구멍이므로 여기서 닫는다. 안 막으면 에이전트가 자기 게이트를 끌 수
있고, 그건 출하가 순손실이라는 뜻이다.

**`.mcp.json` 처럼 basename 으로 매칭하지 않는다** — 프로젝트의 아무 `cycle.json` 이 차단된다.
`.sage/cycle.json` **경로 꼬리**로 판정한다. CLI 는 편집 도구 밖이라 그대로 동작한다.

커버리지를 과대평가하지 않는다: matcher 는 편집 도구뿐이고 Bash 는 어느 hook spec 에도 없다(§6-K8).

### D8 — 쓰기는 원자적, 읽기 실패는 degrade 하면서 표면화

- 쓰기: `tempfile.mkstemp` + `os.replace`
- 읽기 실패: **선언 부재로 degrade** — 파일 하나 깨진 것으로 모든 편집을 멈추지 않는다
- **단 "파일이 존재하나 읽지 못했다" 를 표면화한다.** 부재·손상·스키마 위반이 전부 `""` 로 뭉개지면
  1바이트만 잘라도 D4 차단이 사라진다. 이 프로젝트가 반복해 반증한 "부재는 안전 방향"의 자리다.
- 채널은 `hookSpecificOutput.additionalContext` — 저장소가 이미 기록했다: Claude Code 는 exit 0 hook 의
  평문 stdout 을 디버그 로그에만 쓰고, PreToolUse 는 이 봉투로 실어야 닿는다. stderr 는 BLOCK 경로다.

D4 가 선언을 **차단 근거로 승격**시켰으므로 손상이 곧 차단 해제 레버가 될 수 있는데, **그 레버를 막는
주력은 D7 이다**. D8 의 원자성은 쓰기 중단 손상을, 표면화는 남은 경로를 보완한다.

### D9 — 두 차단 메시지 양쪽에 해제 통로를 넣는다

재현: 완결 차단이 "새 사이클의 Phase 00 을 작성하라" 고 하고, 그대로 하면 binding 후보 2개로 다시
막히며 그 안내는 "파일명과 Cycle-Stem 을 일치시켜라"(이미 일치한다). **두 안내가 서로를 가리키고
`sage cycle clear` 를 어느 쪽도 언급하지 않는다.** env 시절엔 드물었지만 파일은 세션을 넘겨 살아남아
**사이클 경계마다** 발생한다. `block_cycle_closed` 와 `block_cycle_binding` 양쪽을 고친다.

**단정하지 않는다** — `resolve` 는 문서 오류를 후보 개수보다 먼저 반환하므로 `source` 로 실패 원인을
역추론할 수 없다. "선언도 후보에 포함된다" 는 사실 진술이고 원인 단정이 아니다.

## 5. 범위 밖

- **`SAGE_CYCLE_STEM` 폐기** — 프로세스 범위 지정은 CI 에서 정당하다
- **선언 stem 유효성 검증** — 게이트가 이미 문서 부재로 판정한다(형식 검사는 `use` 에서 한다)
- **자동 만료(TTL)** — 작업 맥락을 시간으로 끊으면 작업 중간에 조용히 바뀐다
- **L1 통과에 결속 노출** → 백로그 EH-15. 감시 개선이지 이 기능이 만든 결함이 아니다
- **L0 / pdca 비활성 통과 노출** → 백로그 EH-16. 기존 사각. `_stamp_cycle_identity` 가 위험도와
  무관하게 스탬프하므로 "재료가 없다"는 근거는 **거짓**이다 — 다음 사이클이 물려받지 않게 적어둔다

## 6. 알려진 한계 — 인정하고 넘어간다

**K1 — CLI root ≠ 게이트 root (구성 의존, 보장 불가능)**
게이트 root 는 hook 실행 시점 호스트 env(`SAGE_PROJECT_ROOT` → `CLAUDE_PROJECT_DIR`/
`CODEX_PROJECT_ROOT` → git toplevel → cwd)로 정해지고 CLI 는 그걸 볼 수 없다. 발화 구성: 이중 설치 ·
셸에 `SAGE_PROJECT_ROOT` 잔존 · 모노레포 하위 설치에서 상위에 서 있는 경우. 저장소 루트 단일
설치에서는 발생하지 않는다. **보장 대신 가시성(D5)으로 대체한다.** 게이트 root 해석은 건드리지
않는다 — 호출부는 하나지만 root 가 profile·snapshot·감사 경로·정체성 키로 흐르고 셸 어댑터 2곳이
같은 규칙을 문자열로 복제한다. 어긋난 구성에서도 잃는 능력은 없다 — `SAGE_CYCLE_STEM` 이 남아 있고
D3 이 그걸 최우선에 둔다.

**K2 — 표식 검사가 존재 검사다**(기존 코드) 디렉터리·0바이트 파일도 root 로 인정된다. self-DoS 성격.

**K3 — L1/L0 통과가 화면 출력 0바이트**(기존 사각) §5 참조. 인정 근거는 **감사**다 — 선언 결속이면
위험도와 무관하게 기록되고 통과 시 기록 실패는 fail-closed BLOCK 이다. 화면에는 안 보여도 **증거는
소실되지 않는다.** (D7 을 근거로 들면 안 된다 — D7 은 몰래 심는 쓰기만 막고, 정식 `use` 로 심은
낡은 선언 + L1 편집은 그대로 0바이트다.)

**K4 — `sage override` 의 root 해석이 다르다**(선행 사이클 소관) 게이트는 게이트 root 에 감사를 쓰고
`--list` 는 cwd 에서 읽는다. 같은 병이지만 이 사이클 범위 밖.

**K5 — CLI 쪽 root 규칙이 다섯 갈래다** `generate`·`validate`·`sync_overlays` 는 manifest, `review` 는
profile.yaml + cwd 폴백, `override` 는 탐색 없음. 통일은 별도 사이클.

**K6 — `--root` 는 verbatim 이다** 표식 검사를 거치지 않는다. 명시 지정은 사용자 책임. 게이트는 게이트
root 만 읽으므로 잘못 쓰면 무효이지 우회가 아니다.

**K7 — 완결 판정을 되돌릴 수 있다**(기존 사각, 측정) 05 의 `Final Status: APPROVED` 를 지우거나 06 을
삭제하는 편집은 "문서 전부 변경" 이라 D4 면제에 걸리고, 그 뒤 `_cycle_closed` 가 False 가 된다. 현재
코드에서 추론 경로로도 동일하며 `_cycle_closed` 가 이 성질을 명시적으로 선택했다. D4 가 새로 여는
것이 아니다.

**K8 — Bash 는 어느 hook spec 의 matcher 에도 없다**(기존 사각, 시스템 전체 균일) Bash 를 가진 주체는
소스 자체를 게이트 없이 쓸 수 있다. D7 을 이보다 강한 방어로 과대평가하지 않는다.

## 7. 회귀 이빨

`scripts/sage_harness/hooks/tests/test_cycle_state.py` 신설(42건) + `test_cycle_stem_declaration.py`
확장. 각 줄은 "깨지면 이 사이클이 무의미해지는" 성질이고 **양방향**으로 고정한다.

| # | 성질 |
|---|---|
| T1 | 하위 디렉터리·`realpath` 경유에서도 같은 root 로 해석되고 게이트가 읽는다 |
| T2 | SAGE 표식 없는 곳에서는 거부한다 |
| T3 | 선언 후 `git status` 가 깨끗하다. 무시 규칙은 `install` 상수에서 가져와 검사 |
| T4 | 선언이 자식 프로세스 env 로 새지 않는다 |
| T5 | env > 파일 > 추론 4갈래 |
| T6 | root A 선언이 root B 판정에 새지 않는다 |
| T7 | 잘못된 stem 형식은 `use` 시점에 거부 |
| T8 | 손상 시 degrade 하고(BLOCK 아님) **동시에** 표면화한다 |
| T8b | 원자적 쓰기 — 고정 tmp 이름·직접 `open(w)` 변이가 죽는다 |
| T9 | 편집 도구로 `.sage/cycle.json` 쓰기가 가드에 걸리고, 다른 `cycle.json` 은 과차단되지 않는다 |
| T10 | D4 네 갈래 — 완결+선언 / 완결+문서 전부 / 완결+혼합 / 완결+변경 0건 |
| T11 | 완결 차단과 binding 차단 양쪽 안내가 해제 통로를 가리킨다 |
| T12 | binding 실패 안내가 원인을 단정하지 않는다 |
| T13 | 표시·감사가 통로만 말하고 실행 주체를 단언하지 않는다 |
| T13b | env 선언과 파일 선언이 표시·감사·**dedupe 키**에서 갈린다 |
| T13c | 완결 차단 사유가 결속 출처를 갈라 말한다 |
| T14 | `use` 가 절대 root·파일 경로를 찍고 gitignore 미적용·profile 부재를 경고한다 |
| T15 | 배선 폐루프 — 실제 `run_pre_implementation_gate` 와 실제 `python -m sage` 로 태운다 |
| T16 | `asset_paths` 등록 + drift(STALE)·missing(FAIL) 짝 |
| T17 | 신규 스위트가 `run-all.sh` 에 등록된다(주석 처리·종료코드 버림도 orphan) |
