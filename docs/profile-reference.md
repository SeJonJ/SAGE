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
```

경로, 파일명, 내용, 사용자 선언 중 가장 높은 tier가 effective risk입니다. Governed cycle은 같은 stem의
Phase 00에 정확히 하나의 `Risk Level: L1`, `L2`, `L3` 선언이 필요하며 현재 변경보다 낮으면 먼저
Phase 00을 상향해야 합니다.

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
  note_convention:
    folder: "wiki"
    required_structure: {}
```

`vault_path`가 비면 vault 기능은 비활성입니다. write-back 깊이는 Phase 00 risk tier를 따르며 L2/L3는
배경, 설계결정, 변경, 검증, 재발방지를 포함하는 심층 노트를 요구합니다.

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
```

검증 명령은 프로젝트가 소유합니다. SAGE는 profile과 phase 문서에 선언된 명령·증거를 연결하지만,
프로젝트별 build system을 추측하지 않습니다.
