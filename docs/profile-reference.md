# SAGE Profile 레퍼런스

[English](profile-reference.en.md) | [문서 인덱스](README.md)

## 공유 정책과 로컬 capability

- `sage/project-profile.yaml`: 저장소에 커밋하는 팀 정책
- `sage/project-profile.local.yaml`: Git에서 제외되는 현재 머신 capability
- `sage/project-profile.json`: generate가 만든 병합·정규화 결과

로컬 profile은 host/model/vault 경로처럼 머신마다 다른 capability만 소유합니다. risk, PDCA, review처럼
게이트를 완화할 수 있는 공유 정책은 로컬에서 덮어쓸 수 없습니다.

generate는 compiled profile을 `0600`으로 수렴시킵니다. 이전 버전이 만든 `0644` 파일도 다음 generate에서
소유자 전용으로 강화됩니다. hook 프로세스가 다른 UID로 실행되는 CI/컨테이너에서는 같은 UID로 실행하거나
명시적인 파일 전달 방식을 구성해야 하며, 권한을 넓혀 공유하는 방식은 지원 계약이 아닙니다.

로컬 profile은 표시 언어도 소유합니다.

```yaml
interface:
  language: en      # 없으면 ko. ko | en 두 값만 허용
```

이 값은 공유 profile·compiled `project-profile.json`·manifest·profile hash 어디에도 들어가지
않습니다. 언어는 머신 capability와 같은 성격이라 로컬에만 남습니다. 한 번만 다르게 실행하려면
하위 명령 앞에 전역 `--lang`을 붙입니다(`sage --lang en validate`). 우선순위는 `--lang` →
local profile → `ko`이며, hook은 `--lang`을 받지 않아 local profile과 기본값만 따릅니다.
잘못된 값은 `ko`로 되돌리고 `sage validate`가 설정 실패로 보고하지만, 게이트 판정과 종료코드는
바뀌지 않습니다.

## 최소 흐름

최초 작성은 `sage-init`, 이미 설정된 프로젝트에 합류할 때는 `sage-init-local`을 사용합니다.

```bash
# runtime.installed_hosts에 맞춰 claude, codex, both 중 선택
sage generate --kind hook --write --target codex
sage validate --kind all
sage doctor --profile sage/project-profile.yaml
```

## 주요 섹션

### 프로젝트와 버전

```yaml
sage:
  required_version: "0.9.72"

project:
  name: "weatherapp"
  prefix: "weatherapp"
```

`required_version`은 프로젝트 자산을 해석해야 하는 exact SAGE 버전입니다. installed/generated/runtime
버전과 다르면 doctor, validate, SessionStart가 진단합니다.

### Runtime과 cross-model

```yaml
runtime:
  active_host: auto
  installed_hosts: [claude, codex]

options:
  cross_model: true

cross_model:
  reviewer: { host: codex, model: gpt-5.6-terra }
  effort: xhigh
```

`active_host: auto`는 현재 실행 환경에서 host를 감지합니다. Phase 05 cross-model review는 실제 active
host를 제외한 runtime을 선택합니다. peer CLI에 도달하지 못하면 required 정책은 BLOCKED입니다.

`cross_model.policy`는 `required | recommended | off`입니다. `required`는 로컬 profile에서
`cross_model.enabled: false`로 완화할 수 없습니다(local이 공유 정책을 완화 불가). `on_unavailable`은
peer CLI에 도달하지 못했을 때의 처리이며 `block`(기본, required 정책에서 사실상 강제)이거나
`clean_context_same_runtime`(같은 runtime의 새 세션으로 대체)입니다.

### Risk

```yaml
risk:
  l0_pass_globs: ["docs/**"]
  l1_path_globs: ["frontend/**"]
  l2_path_globs: ["backend/**"]
  l3_filename_globs: ["*payment*", "*auth*"]
  l2_content_keywords: ["transaction"]
  l3_content_keywords: ["PrivateKey", "chargeCard"]
  plan_glob: "plan_docs/**/*.md"
  l3_review_strategy: "claude_grep_first"
```

경로, 파일명, 내용, 사용자 선언 중 가장 높은 tier가 effective risk입니다. Governed cycle은 같은 stem의
Phase 00에 정확히 하나의 `Risk Level: L1`, `L2`, `L3` 선언이 필요하며 현재 변경보다 낮으면 먼저
Phase 00을 상향해야 합니다.

`l3_review_strategy`는 **L3가 리뷰 가능해지기 위한 필수 값**입니다(`claude_grep_first` |
`codex_feature_signal` | 프로젝트 커스텀 모듈명). 비어 있으면 L3 독립 리뷰가 안전하게 BLOCK되므로,
"L3인데 리뷰가 통과 안 된다"는 문제는 대개 이 값 누락이 원인입니다.

### Phase 00 Done Criteria

```yaml
pdca:
  base_plan:
    done_criteria_gate: advisory  # off | advisory | enforce
```

키 부재나 `off`는 기존 동작을 유지합니다. `advisory`는 Phase 00의 완료 기준 구조, 3상태 항목,
재계획 revision, 영향 phase 재실행, 최신 Phase 05 승인 결속 문제를 경고하되 진행을 허용합니다.
`enforce`는 같은 문제를 phase 전환·APPROVED·Phase 06 경계에서 차단합니다. 정상적인 01~04의
미완료 `[ ]`는 차단하지 않습니다. 신규 Phase 00은 `Done-Criteria-Revision: 1`에서 시작하며,
기준 문구나 범위가 바뀌면 revision과 사유·영향 phase를 기록합니다. 이 shared 정책은
`sage-init`과 `sage-profile-modify`가 수집하고 `sage-init-local`은 수정하지 않습니다.

### Review loop (Phase 05)

```yaml
pdca:
  review_loop:
    enabled: false
    lenses: { L2: [correctness, security], L3: [correctness, security, concurrency] }
    refuters: 2
    refute_threshold: majority
    max_iterations: { L2: 1, L3: 3 }
    dry_rounds: 1
    budget_tokens: { L2: 150000, L3: 400000 }
    severity_block: ["P0", "P1"]
    termination_enforce: advisory
    report_gate_enforce: advisory
    early_completion:
      enabled: false
      minimum_completed_rounds: 1
```

Phase 05의 find→refute→triage→rework 적대적 반복 루프입니다. 기본은 꺼져 있습니다. `lenses`가 각
라운드에서 찾을 관점, `refuters`가 finding당 반박자 수, `max_iterations`가 라운드 상한,
`dry_rounds`가 "신규 발견 0"이 몇 라운드 연속이면 수렴으로 볼지입니다. `termination_enforce`/
`report_gate_enforce`는 `off | advisory | enforce`이며, `enforce`는 06 작성을 실제로 차단합니다.
표준 사이클의 정식 절차이고, 명시적으로 허용된 L2/L3에서만 쓰는 축약판은 아래 Fast Cycle입니다.

`early_completion`은 사용자의 명시적 승인으로 수렴 전에 루프를 닫을 수 있게 하는 옵트인이며 기본은
꺼짐입니다. 블록 자체가 없으면 꺼진 것으로 읽습니다. `minimum_completed_rounds`는 엔진 하한이 1이고
프로젝트가 올릴 수만 있습니다 — 0을 허용하면 "리뷰 0라운드 승인"이 설정 한 줄로 열립니다. 이 옵트인은
게이트를 **느슨하게** 하는 방향이라, 판정 토큰은 `APPROVED`를 유지하되 Phase 05가
`Review-Assurance: REDUCED_BY_USER_AUTHORIZATION`을 함께 적어 나중에 읽는 사람과 CI 권위가 수렴
승인과 구분할 수 있게 합니다. **설정을 켠 것은 개별 실행의 승인이 아닙니다** — 사유·승인자·확인 토큰은
close 시점에 사용자가 직접 줍니다.

### Fast Cycle

```yaml
pdca:
  fast_cycle:
    enabled: false
    reason_required: true
    minimum_rounds: { L2: 1, L3: 1 }
    minimum_lenses: { L2: 2, L3: 2 }
    lenses:
      L2: [correctness, error_handling, convention]
      L3: [correctness, security, data_integrity, concurrency]
    standard_transition:
      enabled: false
```

Fast Cycle은 L2/L3의 별도 축약 절차이며 일반 override가 아닙니다. `enabled`는 공유 정책이고 기본값은
false입니다. `reason_required`는 true로 고정되며 완화할 수 없습니다. 최소 라운드는 1 이상, 최소 렌즈는
2 이상이어야 하고 각 후보 목록은 최소 수 이상이어야 합니다. 실행자는 `sage-cycle-fast`에서 Fast
level·렌즈 수·한 줄 사유를 모두 입력합니다. 실제 Risk Level은 composite 00에 별도로 남고 Fast level이
이를 낮추지 않습니다. `sage-init`과 `sage-profile-modify`가 이 공유 설정을 대화로 수집합니다.

`standard_transition`은 이미 진행 중인 Standard Cycle을 `sage fast-cycle convert`로 Fast 계약에
넘길 수 있게 하는 별도 옵트인이며 기본은 꺼짐입니다. 블록이 없으면 꺼진 것으로 읽습니다. 켜면
composite 계획 없이도 Fast 리뷰 최소치에 도달할 수 있으므로, 문서가 아니라 감사 레코드가 그 run이
어떻게 Fast로 들어왔는지에 대한 유일한 증거가 됩니다. 전환은 문서를 쓰지 않고, 전환된 run은 감사에
남은 phase 목록이 담고 있는 pre-implementation phase만 면제받습니다. **설정을 켠 것은 개별 전환의
확인이 아닙니다** — `--confirm FAST-CONVERTED`·사유·승인자는 전환 시점에 사용자가 직접 줍니다.

### Components

```yaml
components:
  - id: backend
    paths: ["backend/**"]
    runtime_models: { claude: opus, codex: gpt-5.6-terra }
  - id: frontend
    paths: ["frontend/**"]
```

Components는 implementer roster와 ownership routing에 사용됩니다. `sage generate --kind roster`가
`implementer-<component>` spec을 생성합니다.

### Phase 04 체크리스트 스캔

```yaml
checklist_scan_targets:
  - label: "03 implementation"
    glob: "plan_docs/03-implementation/**/*.md"
    is_impl: true
  - label: "backend plan"
    glob: "backend/plan_docs/*.md"
```

각 항목은 `label`과 project-relative `glob`이 필수이며 `is_impl`은 선택 boolean입니다. 절대경로,
UNC/rooted 경로, Windows drive-relative 경로(`C:private/*.md`), `..` 세그먼트와 제어문자는
거부됩니다. 실제 매치도 realpath로 다시 검사하므로 symlink를 통해 저장소 밖 문서를 읽을 수 없습니다.
이전 버전에서 잘못된 항목이 조용히 무시됐다면 새 버전의 `sage generate`는 기존 산출물을 보존하고
FAIL합니다. profile을 수정한 뒤 다시 생성하세요.

### Team runtime

```yaml
team:
  core:
    leader:
      enabled: true
      runtime: { model: opus, effort: xhigh }
    reviewer:
      enabled: true
      runtime: { model: opus }
```

변경 후 `sage install --force`를 실행하면 Claude CORE agent frontmatter에 model과 effort가
재배포됩니다. Codex agent 파일은 같은 필드를 실행 설정으로 해석하지 않으므로 validate가 무동작
설정을 경고합니다.

### Governance 문서

```yaml
governance_docs:
  - { doc: "docs/architecture.md", label: "시스템 아키텍처" }
  - { doc: ".github/SECURITY.md", label: "보안 정책" }
```

각 항목은 프로젝트 상대경로와 80자 이하 한 줄 label입니다. 경로 포인터만 `AGENT_GUIDE.md`의 관리 블록에
렌더되며 risk trigger는 포함하지 않습니다. 변경 후 `sage sync-overlays`를 실행합니다.

### 지식 캡처

```yaml
knowledge_capture:
  vault_path: "/path/to/obsidian/vault"
  provider: obsidian
  scan_before_dev: true
  update_after_dev: true
  fast_cycle_dashboard: false
  note_convention:
    folder: "wiki"
    required_structure: {}
```

`vault_path`가 비면 vault 기능은 비활성입니다. write-back 깊이는 Phase 00 risk tier를 따르며 L2/L3는
배경, 설계결정, 변경, 검증, 재발방지를 포함하는 심층 노트를 요구합니다.
`fast_cycle_dashboard: true`이면 Fast run 종료·중단 뒤 vault에 프로젝트별 파생 dashboard를 갱신합니다.
감사 정본은 항상 `.sage/fast_cycle.jsonl`이며 dashboard 실패는 이미 기록된 종료를 되돌리지 않습니다.

### Feedback

```yaml
feedback:
  enabled: false
  block_release: false
  record: false
  record_target: auto
```

활성화하면 소스의 `sage-feedback ::` 마커를 추적합니다. `block_release`는 CI가
`sage feedback --release-gate`를 호출할 때 미해결 blocking marker로 릴리즈를 차단합니다.

### Verification

```yaml
verification:
  commands:
    build: "npm run build"
    test: "npm test"
    lint: "npm run lint"
  acceptance:
    enabled: true
    require_for_risk: [L2, L3]
    statuses: [PASS, FAIL, "NOT TESTED", N/A]
    unresolved_statuses: [FAIL, "NOT TESTED"]
    report_gate_by_risk: { L2: advisory, L3: enforce }
    waiver: { enabled: true }
```

검증 명령은 프로젝트가 소유합니다. SAGE는 profile과 phase 문서에 선언된 명령·증거를 연결하지만,
프로젝트별 build system을 추측하지 않습니다.

`acceptance`는 요구사항별 수용 증거 매트릭스입니다. 빌드·테스트가 통과해도 "사용자가 요청한 기능이
실제로 동작한다"는 별개로 증명해야 한다는 전제 위에 있습니다. 기본 `enabled: true`이고 `require_for_risk`에
포함된 위험도는 Phase 04에서 각 요구사항에 `PASS/FAIL/NOT TESTED/N/A`를 기록해야 합니다.
`report_gate_by_risk`는 `unresolved_statuses`(기본 FAIL·NOT TESTED)가 남아있을 때 06 작성을 막을지
결정하며, **L3는 profile만으로 advisory로 낮출 수 없습니다.** 예외가 필요하면 `waiver`로 사이클·요구사항
ID가 정확히 일치하는 명시적 CLI grant만 사용합니다 — 조용한 통과는 없습니다.

### 기타 게이트 토글

| 키 | 기본값 | 의미 |
|---|---|---|
| `pdca.cycle_binding_visibility` | `gated` | 게이트 **통과** 줄에 결속 cycle stem을 어디까지 표기할지. `gated`는 판정 줄이 생기는 경우(L2/L3 통과·WARN)에만. `all`은 L1·L0 통과에도 한 줄을 내보낸다 — 장수 브랜치에서 오결속을 눈으로 잡을 때 켜되, 편집마다 한 줄이 쌓인다. 결속 증거 자체는 이 설정과 무관하게 `.sage/override.jsonl`에 남는다 |
| `pdca.retro.report_gate_enforce` | `off` | `sage retro --check` 실행 여부를 Stop 훅이 사후 확인. `enforce`는 세션당 최대 1회 BLOCK |
| `pdca.writeback.depth_review_gate` | `off` | L2/L3 write-back 노트가 host self-review를 거쳤다는 자기선언(`Depth-Self-Review: performed`)을 Stop 훅이 확인 |
| `conventions` | `[]` | 스택별 컨벤션 문서 포인터. `[{ scope, stack, doc, file_globs }]` |
| `context_management.compaction` | `enabled: true` | 세션 압축 시 보존할 항목(`architectural_decisions`, `open_bugs` 등)과 최대 스냅샷 크기 |
| `hooks.register` | `[claude]` | 어느 host에 hook을 등록할지. cross-model 프로젝트는 `[claude, codex]` |
