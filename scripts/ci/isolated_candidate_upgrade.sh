#!/usr/bin/env bash
# AC32 — 격리 1.0 후보 빌드 + 실제 v0.9.84 소비자 upgrade E2E.
#
# FR-R03: "임시 source copy만 `1.0.0`으로 stamp해 후보를 만들 수 있으며 저장소 전후 상태는
# 같아야 한다." 이 저장소(HEAD)는 절대 건드리지 않는다 — `git archive HEAD` 로 임시 디렉터리에
# 뽑은 복사본에서만 버전을 바꾸고, 그 복사본에서 wheel 을 빌드한다. 실제 저장소의 버전·태그·git
# 상태는 스크립트 시작과 끝이 완전히 같아야 한다(마지막에 diff 로 확인한다).
#
# 두 wheel:
#   OLD = 이 저장소 HEAD 그대로 빌드(현재 실제 버전, 지금은 0.9.84) — "이미 설치된 소비자" 를 만드는 데 쓴다.
#   NEW = 격리 복사본에서 1.0.0 으로 stamp 후 빌드 — "1.0 후보" 이며, 이 wheel 의 `sage upgrade` 로
#         OLD 소비자를 실제로 승격시킨다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CANDIDATE_VERSION="1.0.0"

echo "== [1/9] 저장소 시작 상태 기록 (끝에서 비교) =="
BEFORE_STATUS="$(git -C "$HERE" status --porcelain)"
BEFORE_VERSION="$(python3 -c "import re; print(re.search(r'__version__ = \"([^\"]+)\"', open('$HERE/sage/__init__.py').read()).group(1))")"
echo "   HEAD version = $BEFORE_VERSION, working tree $( [ -z "$BEFORE_STATUS" ] && echo clean || echo DIRTY )"

echo "== [2/9] OLD wheel 빌드 (이 저장소 HEAD 그대로, 버전 $BEFORE_VERSION) =="
python3 -m venv "$WORK/buildenv"
"$WORK/buildenv/bin/pip" install --quiet build >/dev/null
( cd "$HERE" && rm -rf dist build && "$WORK/buildenv/bin/python" -m build --wheel --outdir "$WORK/old-dist" >/dev/null )
OLD_WHL="$(ls "$WORK"/old-dist/*.whl | head -1)"
echo "   old wheel: $(basename "$OLD_WHL")"

echo "== [3/9] 격리 source copy 생성 + 1.0.0 stamp (저장소 밖, HEAD 는 안 건드림) =="
mkdir -p "$WORK/candidate-src"
( cd "$HERE" && git archive HEAD | tar -x -C "$WORK/candidate-src" )
python3 - "$WORK/candidate-src" "$CANDIDATE_VERSION" <<'PYEOF'
import re, sys
root, version = sys.argv[1], sys.argv[2]
init_path = f"{root}/sage/__init__.py"
init = open(init_path, encoding="utf-8").read()
new_init, n = re.subn(r'__version__ = "[^"]+"', f'__version__ = "{version}"', init)
assert n == 1, f"__version__ 치환 실패({n}건)"
open(init_path, "w", encoding="utf-8").write(new_init)

pyproject_path = f"{root}/pyproject.toml"
pyproject = open(pyproject_path, encoding="utf-8").read()
new_pyproject, n = re.subn(r'(?m)^version = "[^"]+"', f'version = "{version}"', pyproject)
assert n == 1, f"pyproject version 치환 실패({n}건)"
open(pyproject_path, "w", encoding="utf-8").write(new_pyproject)
print(f"   stamped {init_path}, {pyproject_path} -> {version}")
PYEOF

echo "== [4/9] NEW(1.0 후보) wheel 빌드 (격리 복사본에서만) =="
( cd "$WORK/candidate-src" && rm -rf dist build && "$WORK/buildenv/bin/python" -m build --wheel --outdir "$WORK/new-dist" >/dev/null )
NEW_WHL="$(ls "$WORK"/new-dist/*.whl | head -1)"
echo "   candidate wheel: $(basename "$NEW_WHL")"
case "$(basename "$NEW_WHL")" in
  *"$CANDIDATE_VERSION"*) ;;
  *) echo "❌ 후보 wheel 파일명에 $CANDIDATE_VERSION 이 없다: $(basename "$NEW_WHL")"; exit 1 ;;
esac

echo "== [5/9] OLD wheel 로 '이미 설치된 v$BEFORE_VERSION 소비자' 구성 =="
python3 -m venv "$WORK/old-venv"
"$WORK/old-venv/bin/pip" install --quiet "$OLD_WHL" jsonschema >/dev/null
PROJ="$WORK/proj"; mkdir -p "$PROJ"
cd "$WORK"   # repo 루트가 아닌 cwd 로 이동 — wheel_smoke.sh 와 같은 이유(로컬 sage/ import 방지)
env -u SAGE_RESOURCE_ROOT "$WORK/old-venv/bin/sage" install --host claude --dest "$PROJ" >/dev/null
"$WORK/old-venv/bin/python3" - "$PROJ/sage/project-profile.yaml" "$PROJ/sage/project-profile.json" <<'PY'
import json
import sys
import yaml
from sage.profile_compile import materialize_profile

yaml_path, json_path = sys.argv[1], sys.argv[2]
text = open(yaml_path, encoding="utf-8").read()
text = text.replace('name: ""', 'name: "aged-consumer"')
text = text.replace('l2_path_globs: []', 'l2_path_globs: ["src/**"]')
open(yaml_path, "w", encoding="utf-8").write(text)

# /sage-init 는 yaml 편집 뒤 컴파일된 json 을 함께 갱신한다 — 여기서도 같은 짝을 맞춘다.
# (손으로 yaml 만 고치면 overlay_materialize 가 materialize.profile_yaml_json_mismatch 로 막는다.)
profile = yaml.safe_load(open(yaml_path, encoding="utf-8"))
compiled = materialize_profile(profile)
with open(json_path, "w", encoding="utf-8") as handle:
    json.dump(compiled, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
env -u SAGE_RESOURCE_ROOT "$WORK/old-venv/bin/sage" generate --kind hook --write --dest "$PROJ" >/dev/null
INSTALLED_VERSION="$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJ/sage/project-profile.yaml'))['sage']['required_version'])" 2>/dev/null || echo "?")"
echo "   consumer bootstrapped at $PROJ (profile required_version=$INSTALLED_VERSION)"

echo "== [5b/9] upgrade 전 사용자 데이터 마커 배치 (보존 확인용) =="
mkdir -p "$PROJ/sage"
cat > "$PROJ/sage/project-profile.local.yaml" <<'EOF'
interface:
  language: en
EOF
mkdir -p "$PROJ/src"
echo "// user-authored, must survive upgrade untouched" > "$PROJ/src/user_owned.src"
USER_FILE_BEFORE="$(sha256sum "$PROJ/src/user_owned.src" | cut -d' ' -f1)"
LOCAL_PROFILE_BEFORE="$(sha256sum "$PROJ/sage/project-profile.local.yaml" | cut -d' ' -f1)"

echo "== [6/9] NEW(1.0 후보) wheel 을 별도 venv 에 설치 =="
python3 -m venv "$WORK/new-venv"
"$WORK/new-venv/bin/pip" install --quiet "$NEW_WHL" jsonschema >/dev/null
NEW_SAGE="$WORK/new-venv/bin/sage"

echo "== [7/9] 1.0 후보로 v$BEFORE_VERSION 소비자 upgrade 실행 (check → apply → 재apply 멱등) =="
env -u SAGE_RESOURCE_ROOT "$NEW_SAGE" upgrade --check --root "$PROJ" || true
REPORT="$(ls -t "$PROJ"/.sage/upgrades/*.json | head -1)"
python3 - "$REPORT" "$CANDIDATE_VERSION" <<'PY'
import json, sys
report, expected = sys.argv[1], sys.argv[2]
payload = json.load(open(report, encoding="utf-8"))
assert payload["engine_version"] == expected, f"engine_version={payload['engine_version']!r}, expected {expected!r}"
print(f"   check OK: engine_version={payload['engine_version']}")
PY

env -u SAGE_RESOURCE_ROOT "$NEW_SAGE" upgrade --apply --force --root "$PROJ" >/dev/null
AFTER_VERSION="$(python3 -c "import yaml; print(yaml.safe_load(open('$PROJ/sage/project-profile.yaml'))['sage']['required_version'])")"
test "$AFTER_VERSION" = "$CANDIDATE_VERSION" || { echo "❌ apply 후 required_version=$AFTER_VERSION, 기대값 $CANDIDATE_VERSION"; exit 1; }
echo "   apply OK: profile required_version -> $AFTER_VERSION"

BEFORE_TREE="$(find "$PROJ" -type f -not -path '*/.sage/upgrades/*' | sort | xargs -I{} sha256sum {} | sha256sum)"
env -u SAGE_RESOURCE_ROOT "$NEW_SAGE" upgrade --apply --force --root "$PROJ" >/dev/null
AFTER_TREE="$(find "$PROJ" -type f -not -path '*/.sage/upgrades/*' | sort | xargs -I{} sha256sum {} | sha256sum)"
test "$BEFORE_TREE" = "$AFTER_TREE" || { echo "❌ 두 번째 apply 가 파일을 다시 썼다(비멱등)"; exit 1; }
echo "   reapply OK: 멱등(두 번째 apply 로 트리 변경 없음)"

echo "== [8/9] 사용자 데이터 보존 확인 (local profile · 사용자 파일) =="
USER_FILE_AFTER="$(sha256sum "$PROJ/src/user_owned.src" | cut -d' ' -f1)"
LOCAL_PROFILE_AFTER="$(sha256sum "$PROJ/sage/project-profile.local.yaml" | cut -d' ' -f1)"
test "$USER_FILE_BEFORE" = "$USER_FILE_AFTER" || { echo "❌ 사용자 파일이 upgrade 로 변경됐다(데이터 보존 위반)"; exit 1; }
test "$LOCAL_PROFILE_BEFORE" = "$LOCAL_PROFILE_AFTER" || { echo "❌ local profile 이 upgrade 로 변경됐다(데이터 보존 위반)"; exit 1; }
echo "   보존 OK: 사용자 파일·local profile 바이트 단위 불변"

echo "== [8b/9] upgrade 후 validate --check (1.0 후보 sage 로) =="
env -u SAGE_RESOURCE_ROOT "$NEW_SAGE" validate --check --root "$PROJ"

echo "== [9/9] 저장소 전후 상태 동일성 확인 (FR-R03) =="
AFTER_STATUS="$(git -C "$HERE" status --porcelain)"
AFTER_VERSION_REPO="$(python3 -c "import re; print(re.search(r'__version__ = \"([^\"]+)\"', open('$HERE/sage/__init__.py').read()).group(1))")"
test "$BEFORE_STATUS" = "$AFTER_STATUS" || { echo "❌ 저장소 working tree 가 스크립트 실행 중 바뀌었다"; exit 1; }
test "$BEFORE_VERSION" = "$AFTER_VERSION_REPO" || { echo "❌ 저장소 __version__ 이 $BEFORE_VERSION -> $AFTER_VERSION_REPO 로 바뀌었다"; exit 1; }
rm -rf "$HERE/dist" "$HERE/build"
echo "   저장소 불변 확인: version=$AFTER_VERSION_REPO, working tree $( [ -z "$AFTER_STATUS" ] && echo clean || echo DIRTY )"

echo ""
echo "✅ AC32 격리 1.0 후보 빌드 + v$BEFORE_VERSION→$CANDIDATE_VERSION 실제 upgrade E2E PASS"
