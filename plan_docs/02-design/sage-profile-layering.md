# [Design] SAGE 공유 정책과 로컬 capability 프로필 분리

Cycle-Stem: `sage-profile-layering`

## 1. Central Resolver

새 프로필 계층 모듈이 다음 순서를 단일 소스로 소유한다.

```text
load shared YAML
  -> validate shared bootstrap/schema/semantics
  -> optionally load local YAML
  -> validate local schema and allowlist
  -> reject policy weakening
  -> build in-memory effective profile
```

`sage generate`는 shared YAML만 `project-profile.json`으로 컴파일한다. hook gate의 정본은 계속 shared
JSON이며 local 개인 정보는 들어가지 않는다. host-side CLI인 doctor, review, models, knowledge 경로는 중앙
resolver의 effective profile을 사용한다.

## 2. Local Contract

로컬 스키마는 닫힌 구조로 두며 다음 capability만 허용한다.

- `runtime.installed_hosts`
- `capabilities.claude|codex`
- `cross_model.enabled`
- `knowledge_capture.enabled|vault_path`
- host별 사용 가능 모델 메타데이터

병합은 일반 deep-merge가 아니라 필드별 projector로 구현한다. 따라서 향후 shared에 새 gate 키가 추가돼도
local이 자동으로 덮어쓸 수 없다. 실제 active host는 local 영구값 대신 review 명령의 `--host` 또는 host
runtime의 확정 가능한 환경 신호로 주입한다.

## 3. Init Skills

`sage-init`은 현재 bootstrap predicate를 먼저 검사한다. 설치가 배치한 빈 템플릿은 허용하지만 project.name과
risk/components가 설정된 shared는 차단한다. 허용된 경우 shared 인터뷰 뒤 local capability 인터뷰를 이어서
수행한다.

`sage-init-local`은 shared를 읽어 local에서 선택 가능한 항목만 질문한다. shared 정책이 required이면
cross-model false 선택지를 제시하지 않는다. local이 이미 있으면 현재값을 보여주고 재인터뷰 후 원자적으로
교체한다. 두 skill 모두 수동 YAML 작성이 아니라 agent-authored profile 원칙을 유지한다.

## 4. Git Safety and Validation

install은 local 경로를 프로젝트 `.gitignore`의 SAGE managed block에 등록한다. 기존 사용자 규칙은 보존한다.
doctor/validate는 `git check-ignore`와 `git ls-files`로 local 파일의 ignore/추적 상태를 구분한다. Git 저장소가
아닌 프로젝트에서는 ignore 검사를 N/A로 보고한다.

## 5. Tests

- init 상태표 전체, 빈 설치 템플릿과 부트스트랩 shared 구분
- local allowlist와 unknown/policy key 거부
- local 비밀값이 compiled JSON/manifest에 없는지 검사
- required 완화 차단과 recommended opt-out 허용
- `.gitignore` managed block 보존·멱등·추적 경고
- local 없는 레거시 프로젝트 회귀
