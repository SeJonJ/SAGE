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

echo "== [1/6] wheel 빌드 (격리 build venv — 시스템 python PEP668 회피) =="
python3 -m venv "$WORK/buildenv"
"$WORK/buildenv/bin/pip" install --quiet build >/dev/null
( cd "$HERE" && rm -rf dist build && "$WORK/buildenv/bin/python" -m build --wheel >/dev/null )
WHL="$(ls "$HERE"/dist/*.whl | head -1)"
echo "   wheel: $(basename "$WHL")"

# 중립 CWD 로 이동 — repo 루트(./sage 존재)에서 실행하면 stdin/console 스크립트가 cwd 의 repo sage 를
# site-packages wheel 보다 먼저 import 해 번들 검증이 무력화된다. $WORK 엔 sage/ 가 없어 wheel 이 import 됨.
cd "$WORK"

echo "== [2/6] clean venv 설치 (wheel + jsonschema 만) =="
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet "$WHL" jsonschema >/dev/null
SAGE="$WORK/venv/bin/sage"
PY="$WORK/venv/bin/python"

echo "== [3/6] sage_root 가 번들(sage/_bundle)로 해석되는지 (repo fallback 아님) =="
unset SAGE_RESOURCE_ROOT
"$PY" - <<'PYEOF'
import os, sys
from sage import _resources
root = _resources.sage_root()
assert root.endswith(os.path.join("sage", "_bundle")), f"sage_root 가 번들이 아님: {root}"
assert os.path.isdir(os.path.join(root, "templates")), "번들에 templates 없음"
assert os.path.isfile(os.path.join(root, "scripts", "sage_harness", "hooks", "pre_implementation_gate_core.py")), "번들에 hook core 없음"
print(f"   sage_root = {root} (번들 OK)")
PYEOF

PROJ="$WORK/proj"; mkdir -p "$PROJ"
echo "== [4/6] sage install (번들 → 신규 프로젝트 복사) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" install --host claude --dest "$PROJ" >/dev/null
test -f "$PROJ/docs/sage_harness/.manifest.json" || { echo "❌ manifest 미생성"; exit 1; }
test -f "$PROJ/scripts/sage_harness/hooks/pre_implementation_gate_core.py" || { echo "❌ hook 정본 미복사"; exit 1; }
test -f "$PROJ/sage/project-profile.yaml" || { echo "❌ profile 미복사"; exit 1; }
echo "   install OK (manifest + hook 정본 + profile 복사)"

echo "== [5/6] sage generate --kind hook --write (등록 산출물 + manifest 스탬프) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" generate --kind hook --write --dest "$PROJ" >/dev/null
test -f "$PROJ/.claude/settings.json" || { echo "❌ generate 가 .claude/settings.json 미생성"; exit 1; }
echo "   generate OK (.claude/settings.json 등록 산출물)"

echo "== [6/6] sage validate --check --schema (전체 PASS 기대) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" validate --check --schema --root "$PROJ"

echo "✅ 순수 wheel 단독배포 게이트 PASS — 번들 리소스만으로 install→generate→validate 폐루프 동작"
