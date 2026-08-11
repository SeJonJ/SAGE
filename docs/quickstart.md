# SAGE 퀵스타트

[English](quickstart.en.md) | [README](../README.md)

## 1. 설치

Python 3.10+와 Git이 필요합니다. schema 검증까지 포함한 pipx 설치를 권장합니다.

```bash
pipx install "sage-harness[schema]"
sage --version
```

Windows에서는 `py -m pip install --user pipx`와 `py -m pipx ensurepath`로 pipx를 먼저 설치할 수
있습니다. 설치 hook은 `sage-hook.exe`로 실행되며 bash가 필요하지 않습니다.

## 2. 프로젝트에 설치 — 쓰는 AI 도구에 맞는 쪽 하나만

SAGE는 Claude Code와 Codex 양쪽을 지원하지만, 한 프로젝트에는 실제로 쓰는 쪽 하나만 설치하면
됩니다. 둘 다 쓰고 싶다면 각각 따로 실행하면 됩니다.

**Codex를 쓴다면:**

```bash
cd your-project
sage install --host codex --skill-scope project-local
```

`--skill-scope`는 반드시 명시해야 합니다 — `project-local`은 이 저장소에만, `global`은 이 머신의
모든 프로젝트에 Codex CORE skill을 공유합니다. `sage doctor`가 중복 설치를 진단해줍니다.

**Claude Code를 쓴다면:**

```bash
cd your-project
sage install --host claude
```

## 3. Profile 작성 — 이 프로젝트의 설정을 대화로 채우기

설치만으로는 SAGE가 아무것도 검사하지 않습니다. 위험도, 검증 명령 같은 프로젝트별 설정(profile)을
채워야 실제로 동작합니다. **방금 설치한 쪽 host 안에서** 아래 명령을 실행하세요.

- Claude Code: `/sage-init`
- Codex: `$sage-init`
- 이미 공유 profile이 있는 프로젝트에 합류하는 팀원: `sage-init-local`

최초 init은 공유 정책 `sage/project-profile.yaml`과 Git에서 제외되는 현재 머신 capability
`sage/project-profile.local.yaml`을 분리해 작성합니다.

## 4. Hook 생성과 검증 — profile 대로 실제 실행 파일 만들기

profile을 채운 것만으로는 아직 실제 hook이 생성되지 않습니다. `generate`가 profile 내용을 읽어
AI가 실제로 읽는 실행 파일을 만들고, `validate`가 그게 제대로 됐는지 확인합니다.

```bash
# Codex
sage generate --kind hook --write --target codex
# Claude Code는 --target claude, 양쪽 다 쓴다면 --target both
sage validate --kind all
sage doctor
```

`validate`가 `STALE`을 보고하면(정의 파일은 바뀌었는데 실행 파일이 아직 안 갱신됐다는 뜻) 출력이
지시한 kind를 다시 generate합니다. `FAIL`은 파일 누락, schema 오류, 실행 스모크 실패 같은 실제
계약 위반이므로 원인을 먼저 해결한 뒤 다시 실행합니다.

## 5. 개발 사이클 시작 — 실제로 코드를 짤 때

여기까지 마치면 SAGE가 게이트로 동작합니다. 실제 개발은 아래 명령으로 시작합니다.

- 전체 PDCA(계획→구현→리뷰→완료보고): `sage-cycle`
- profile이 허용한 L2/L3 축약 절차(급한 작업용): `sage-cycle-fast`
- Fast composite 00 작성: `sage-plan-fast`
- Fast 구현·리뷰·종료: `sage-team-fast`
- 기획만(00-02): `sage-plan`
- 구현부터(03-06): `sage-team`
- hook/agent/skill/MCP 자산 추가·수정: `sage-asset`
- 개발자 피드백 마커 처리: `sage-feedback`

고위험 변경은 Phase 00의 정확한 `Risk Level: L1`, `L2`, `L3` 선언과 필요한 phase 문서를 먼저
요구합니다 — 계획 없이 바로 위험한 코드를 고칠 수 없다는 뜻입니다. Phase 05 리뷰가 `APPROVED`되기
전에는 Phase 06 완료 보고가 차단됩니다 — 리뷰 없이 "완료"라고 보고할 수 없다는 뜻입니다.
Fast Cycle은 01~04 문서를 생략하는 대신 그 내용을 체크리스트가 있는 composite 00에 포함하며,
Fast level·렌즈 수·사유를 모두 받기 전에는 문서나 감사를 쓰지 않습니다.

새 Phase 00에는 `Done-Criteria-Revision: 1`과 정확한 `## 5. Done Criteria`를 두고 결과를
`- [ ] ...`로 작성합니다. 증거가 생길 때만 `[x]`, 실제 범위 밖이면 `[~] ... (N/A: 사유)`를
사용합니다. 기준 문구나 범위가 바뀌면 revision과 사유·영향 phase를 기록하고 해당 phase 및
Phase 05 리뷰를 다시 수행합니다.

## 다음 문서

- [CLI 레퍼런스](cli-reference.md)
- [Profile 레퍼런스](profile-reference.md)
- [문제 해결](troubleshooting.md)
