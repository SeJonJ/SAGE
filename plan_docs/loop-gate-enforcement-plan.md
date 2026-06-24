# 7.8단계 — 루프 종료 결정론 집행 + absorb --from-retro 설계 스펙

> 로드맵 8단계(4차 weatherapp) **직전** 추가 작업. 목적: 루프 엔지니어링을 "게이트 ON 잔여" 2종까지
> 채운 상태로 4차에서 평가. 연관: `plan_docs/loop-engineering-plan.md`(v0.7.0),
> `conversational-profile-authoring-plan.md`(v0.8.0). 미구현 — 착수 전 합의용.

## 0. 범위

| 포함 | 제외(후속) |
|---|---|
| A. 루프 종료 결정론 집행 (host close 를 audit+cfg 로 검산) | Loop B(04 커버리지) |
| B. `sage absorb --from-retro` (승인 retro 노트 → patch 제안) | Loop D(self-heal) |

## 1. 시퀀싱 평가 (advisory-first 와의 긴장 + 해소)

- 설계 §5.7 롤아웃은 *advisory 먼저 → 측정 → enforce*. 4차 전에 enforce 를 하드로 켜면 **튜닝 안 된
  budget/iter 값**으로 정상 루프를 BLOCK 할 위험.
- **해소**: 검산 *로직*은 결정론(값 튜닝 무관). 지금 만들되 **기본 모드 `advisory`(불일치 경고만),
  profile 로 `enforce` 전환**. 4차가 advisory 로 측정 → `/sage-profile-modify`(v0.8.0)로 budget 튜닝
  → enforce 플립. report←approve backstop 은 어느 모드든 작동(06←05).
- 결과: "지금 건설 + 안전" 양립. 4차 평가가 집행 발동 정확성까지 관찰.

## 2. A — 루프 종료 결정론 집행

**플래그** (`profile.pdca.review_loop`, 기존 닫힌 서브스키마에 키 추가 → schema + validate 갱신):
```yaml
pdca:
  review_loop:
    termination_enforce: advisory   # advisory | enforce (기본 advisory — §1 해소)
```

**집행 지점**: `sage review-loop close` 가 닫기 전에 audit 라운드 + cfg 로 **종료 일관성 검산**.
이미 있는 result↔reason 짝 검증 위에, *audit 사실과의 일관성*을 추가:

| 닫힌 reason | audit/cfg 와 일관 조건 |
|---|---|
| `CONVERGED` | 마지막 라운드 `survived == 0` |
| `DRY` | 마지막 `dry_rounds` 라운드가 각각 `found == 0`(신규 없음 근사) |
| `BUDGET_TOK` | 누적 `tokens ≥ budget_tokens[risk]` |
| `BUDGET_ITER` | `iterations ≥ max_iterations[risk]` 이고 미수렴(마지막 survived>0) |
| `BLOCKED_ARCH` | 어떤 라운드 `arch > 0` |
| `APPROVED`(결과) | 누적 tokens < budget **AND** 마지막 survived==0 (수렴 정황) — 아니면 불일치 |

**모드별 동작**:
- `advisory`(기본): 불일치 시 stderr WARN + 감사에 `loop_close` 옆에 불일치 사유 기록(또는 close 레코드에 `enforced:false, discrepancy:...`). close 는 그대로 진행(exit 0). → 측정용.
- `enforce`: 불일치 시 close **거부(exit 2)** — host 가 일관된 result/reason 으로 다시 닫게 강제. (또는 옵션: 강제로 BLOCKED 기록. v1 은 거부가 단순·안전.)

**전제**: cfg(`review_loop`) 로드. risk 별 budget/max_iterations 참조. cfg 없거나 미설정 → 검산 skip + WARN(결정론 데이터 부족). audit 무결성 경고(orphan/손상) 있으면 검산 신뢰 불가 → WARN, advisory 취급.

**도메인값 0 유지**: 임계값은 전부 profile 에서. close 는 audit 사실 vs cfg 산술 비교만(LLM 0).

## 3. B — `sage absorb --from-retro`

**retro 노트 구조화**(retro.py 의 human-gate 노트에 제안 블록 추가):
- 현재 노트 = 증거 + distiller 프롬프트(자유 텍스트). 여기에 **`## 제안 (proposals)` 코드블록 placeholder**
  추가 — host 가 distiller 출력(JSON 배열: `{pattern, evidence, target, proposed_change, confidence}`)을
  거기 채우고, 사람이 검토·수정 후 frontmatter `approved: true`.

**명령**: `sage absorb --from-retro <note-path>` (absorb.py 확장):
- frontmatter `approved: true` 아니면 **거부**(human gate — 미승인 노트 반영 금지).
- `## 제안` 블록의 JSON 파싱(실패/없음 → 안내). target 별 patch *제안*(자동반영 없음, absorb 철학):
  - `profile`/`hook`(기계적) → profile 키 / hook spec patch 후보 출력
  - `agent`/`skill`(의미적) → spec intent/advisory_scope 보강 후보 출력
- 출력 후: 사람 적용 → `sage generate`(hook/agent/skill) 또는 profile 직접수정(`/sage-profile-modify`) → `sage validate`.

**absorb 기존 계약 유지**: 제안 전용, 자동반영 절대 없음. `--from-retro` 는 입력원을 "승인된 회고 노트"로 받는 모드.

## 4. 빌드 순서 + 검증

```
A. termination_enforce 스키마/검증 + review-loop close 검산(advisory/enforce) + 테스트 → codex 리뷰 A
B. retro 노트 제안 블록 + absorb --from-retro(승인 게이트·파싱·target 분기) + 테스트 → codex 리뷰 B
```

- A 테스트: close 검산 일관/불일치 케이스 × advisory(WARN+진행)/enforce(거부). cfg 부재 skip. audit 무결성 경고 시 advisory.
- B 테스트: 미승인 노트 거부 / 제안 블록 파싱 / target 분기 / 자동반영 0(파일 미수정).
- 전체 회귀 + 양 host + 도메인값 0.

## 5. 4차 weatherapp 평가 연계

7.8 후 4차는: `/sage-init` 루프 켜기(termination_enforce: advisory) → 루프 실행 → `review-loop close` 검산 발동 관찰(수렴률·토큰 측정) → `/sage-profile-modify` 로 budget 튜닝 → (선택) enforce 플립 재실행 → `sage retro` → 제안 블록 채움 → `absorb --from-retro` → 적용. **루프 엔지니어링 전 구간 e2e 평가.**

## 6. 진행 로그

- 2026-06-23 설계 스펙 작성(미구현). 의존순서 A→B. 4차 weatherapp 선행. 종료집행 기본 advisory(§1).
- 2026-06-23 A 완료 — termination_enforce 플래그 + close 종료 검산(advisory/enforce). codex 2라운드: R1 P1×3(라운드0·BUDGET_ITER·integrity degrade)+P2×2(cfg skip WARN·미지 mode WARN) 반영, R2 CLEAN. review_loop_cli 29 + profile_validate 53 + 회귀 PASS.
- 2026-06-24 B 완료 — absorb --from-retro(승인 게이트·제안 파싱·target 분류·자동반영 0) + retro 노트 ## 제안 블록. absorb 20 테스트 + 회귀 PASS. **codex 리뷰 B 3라운드(R3 P1 비-dict 크래시·P2 첫블록만 파싱 / R4 unhashable target / R5 최종확인) — codex-host 직접 실행 검증(approved→0·unapproved→2) 포함.** 누적 codex 리뷰 5회(A 2 + B 3).
