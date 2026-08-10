#!/usr/bin/env bash
# 순수 wheel 단독배포 게이트 (P2-10 wheel 패키징 독립 게이팅 마일스톤).
#
# clean venv 에 wheel 만 설치(SAGE_RESOURCE_ROOT 없음, repo 체크아웃 접근 없음)하고
# sage install→generate(전 hook)→validate 전체 사이클이 sage/_bundle 리소스만으로 PASS 하는지 검증.
# 리소스 번들 회귀(setup.py BundleResources / _resources 번들 감지)를 빌드 단계에서 잡는다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== [1/8] wheel 빌드 (격리 build venv — 시스템 python PEP668 회피) =="
python3 -m venv "$WORK/buildenv"
"$WORK/buildenv/bin/pip" install --quiet build >/dev/null
( cd "$HERE" && rm -rf dist build && "$WORK/buildenv/bin/python" -m build --wheel >/dev/null )
WHL="$(ls "$HERE"/dist/*.whl | head -1)"
echo "   wheel: $(basename "$WHL")"

# 중립 CWD 로 이동 — repo 루트(./sage 존재)에서 실행하면 stdin/console 스크립트가 cwd 의 repo sage 를
# site-packages wheel 보다 먼저 import 해 번들 검증이 무력화된다. $WORK 엔 sage/ 가 없어 wheel 이 import 됨.
cd "$WORK"

echo "== [2/8] clean venv 설치 (wheel + jsonschema 만) =="
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet "$WHL" jsonschema >/dev/null
SAGE="$WORK/venv/bin/sage"
PY="$WORK/venv/bin/python"

echo "== [3/8] sage_root 가 번들(sage/_bundle)로 해석되는지 (repo fallback 아님) =="
unset SAGE_RESOURCE_ROOT
"$PY" - <<'PYEOF'
import os, sys
from sage import _resources
root = _resources.sage_root()
assert root.endswith(os.path.join("sage", "_bundle")), f"sage_root 가 번들이 아님: {root}"
assert os.path.isdir(os.path.join(root, "templates")), "번들에 templates 없음"
assert os.path.isfile(os.path.join(root, "scripts", "sage_harness", "hooks", "pre_implementation_gate_core.py")), "번들에 hook core 없음"
assert os.path.isfile(os.path.join(root, "scripts", "sage_harness", "hooks", "runtime", "checklist_contract.py")), "번들에 checklist 계약 없음"
assert os.path.isfile(os.path.join(root, "scripts", "sage_harness", "hooks", "runtime", "fast_cycle_audit.py")), "번들에 Fast 감사 runtime 없음"
print(f"   sage_root = {root} (번들 OK)")
PYEOF

PROJ="$WORK/proj"; mkdir -p "$PROJ"
echo "== [4/8] sage install (번들 → 신규 프로젝트 복사) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" install --host claude --dest "$PROJ" >/dev/null
test -f "$PROJ/docs/sage_harness/.manifest.json" || { echo "❌ manifest 미생성"; exit 1; }
test -f "$PROJ/scripts/sage_harness/hooks/pre_implementation_gate_core.py" || { echo "❌ hook 정본 미복사"; exit 1; }
test -f "$PROJ/sage/project-profile.yaml" || { echo "❌ profile 미복사"; exit 1; }
test -f "$PROJ/.claude/skills/sage-init/SKILL.md" || { echo "❌ /sage-init 부트스트랩 스킬 미복사"; exit 1; }
for SKILL in sage-cycle-fast sage-plan-fast sage-team-fast; do
  test -f "$PROJ/.claude/skills/$SKILL/SKILL.md" || { echo "❌ $SKILL 스킬 미복사"; exit 1; }
done
test -f "$PROJ/scripts/sage_harness/hooks/runtime/fast_cycle_audit.py" || { echo "❌ Fast 감사 runtime 미복사"; exit 1; }
echo "   install OK (manifest + hook/Fast 정본 + profile + CORE Fast 스킬 복사)"

# 강제 게이트 검증: 부트스트랩 전(project.name 빈값)엔 generate 가 BLOCK(exit 2) 돼야 한다.
echo "== [4b/8] 부트스트랩 게이트 (빈 profile → generate BLOCK 기대) =="
if env -u SAGE_RESOURCE_ROOT "$SAGE" generate --kind hook --write --dest "$PROJ" >/dev/null 2>&1; then
  echo "❌ 미부트스트랩 profile 인데 generate 가 통과함 (게이트 미작동)"; exit 1
fi
echo "   gate OK (미부트스트랩 generate 차단)"

# 부트스트랩 시뮬레이션: /sage-init 인터뷰가 채울 값(project.name + risk glob)을 설정.
# 설치 인스턴스는 강한 신호(name + risk/components) 필요 — name 만으론 게이트 미통과.
python3 - "$PROJ/sage/project-profile.yaml" <<'PY'
import sys
p = sys.argv[1]
t = open(p, encoding="utf-8").read()
t = t.replace('name: ""', 'name: "smoke"')
t = t.replace('l2_path_globs: []', 'l2_path_globs: ["src/**"]')
open(p, "w", encoding="utf-8").write(t)
PY

echo "== [5/8] sage generate --kind hook --write (등록 산출물 + manifest 스탬프) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" generate --kind hook --write --dest "$PROJ" >/dev/null
test -f "$PROJ/.claude/settings.json" || { echo "❌ generate 가 .claude/settings.json 미생성"; exit 1; }
echo "   generate OK (.claude/settings.json 등록 산출물)"

echo "== [6/8] 설치 template 기반 project hook 등록 + 양 host 실제 dispatch =="
"$PY" - "$PROJ" <<'PY'
import os, sys
from pathlib import Path
from sage import _resources

root = Path(sys.argv[1])
hook_id = "wheel-project-gate"
template = Path(_resources.templates_dir(), "hook.spec.md").read_text(encoding="utf-8")
(root / "docs" / "sage_harness" / "hooks" / f"{hook_id}.md").write_text(
    template.replace('id: ""', f"id: {hook_id}", 1), encoding="utf-8")
(root / "scripts" / "sage_harness" / "hooks" / "wheel_project_gate_core.py").write_text(
    'CONTRACT_VERSION = "1"\n\n'
    'def decide(event, profile, snapshot):\n'
    '    return {"status": "block", "exit_code": 2, "message": "wheel project block"}\n',
    encoding="utf-8")
PY
env -u SAGE_RESOURCE_ROOT "$SAGE" generate --kind hook --id wheel-project-gate \
  --write --target both --root "$PROJ" --dest "$PROJ" >/dev/null
for HOST in claude codex; do
  if [ "$HOST" = claude ]; then
    INPUT='{"tool_name":"Write","tool_input":{"file_path":"src/a.py"}}'
  else
    INPUT='{"tool_name":"apply_patch","tool_input":{"command":"*** Update File: src/a.py\\n+x"}}'
  fi
  set +e
  printf '%s' "$INPUT" | SAGE_PROJECT_ROOT="$PROJ" \
    "$PROJ/scripts/sage_harness/hooks/adapters/$HOST/wheel-project-gate.sh" \
    >"$WORK/$HOST.out" 2>"$WORK/$HOST.err"
  RC=$?
  set -e
  test "$RC" -eq 2 || { echo "❌ $HOST project hook rc=$RC (expected 2)"; cat "$WORK/$HOST.err"; exit 1; }
  grep -q "wheel project block" "$WORK/$HOST.err" || {
    echo "❌ $HOST decision 미실행"; cat "$WORK/$HOST.err"; exit 1;
  }
  ! grep -q "Traceback" "$WORK/$HOST.err" || { echo "❌ $HOST traceback 노출"; exit 1; }
done
echo "   project hook lifecycle OK (template → register → claude/codex dispatch)"

echo "== [7/8] sage validate --check --schema (전체 PASS 기대) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" validate --check --schema --root "$PROJ"

echo "== [8/8] Fast Cycle wheel 진입점 + strict audit runtime =="
env -u SAGE_RESOURCE_ROOT "$SAGE" fast-cycle --help | grep -q "open"
"$PY" - "$PROJ" <<'PY'
import os, sys
root = sys.argv[1]
runtime = os.path.join(root, "scripts", "sage_harness", "hooks", "runtime")
sys.path.insert(0, runtime)
import fast_cycle_audit
run_id = fast_cycle_audit.open_fast(
    root, cycle_stem="wheel-fast", actual_risk="L2", fast_review_level="L2",
    reason="wheel packaging smoke", minimum_rounds=1,
    lenses=["correctness", "error_handling"], profile_hash="p", plan_hash_open="h")
summary = fast_cycle_audit.audit_summary(root)
state = summary["runs"][run_id]
assert summary["file_ok"] is True and state["chain_ok"] is True and state["seq_ok"] is True
assert state["cycle_stem"] == "wheel-fast" and state["lenses"] == ["correctness", "error_handling"]
PY
echo "   Fast Cycle packaging OK (CLI + runtime + strict-chain open)"

echo "✅ 순수 wheel 단독배포 게이트 PASS — 번들 리소스만으로 install→generate→validate 폐루프 동작"
