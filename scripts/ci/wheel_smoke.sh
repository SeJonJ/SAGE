#!/usr/bin/env bash
# 순수 wheel 단독배포 게이트 (P2-10 wheel 패키징 독립 게이팅 마일스톤).
#
# clean venv 에 wheel 만 설치(SAGE_RESOURCE_ROOT 없음, repo 체크아웃 접근 없음)하고
# sage install→generate(전 hook)→validate 전체 사이클이 sage/_bundle 리소스만으로 PASS 하는지 검증.
# 리소스 번들 회귀(setup.py BundleResources / _resources 번들 감지)를 빌드 단계에서 잡는다.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root
# template 을 준다. BSD mktemp 는 인수 없는 -d 의 위치를 TMPDIR 로 보장하지 않는다.
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sage-wheel.XXXXXX")"
trap 'rm -rf "$WORK" "${ISO:-}"' EXIT

echo "== [1/11] wheel 빌드 (격리 build venv — 시스템 python PEP668 회피) =="
python3 -m venv "$WORK/buildenv"
"$WORK/buildenv/bin/pip" install --quiet build >/dev/null
( cd "$HERE" && rm -rf dist build && "$WORK/buildenv/bin/python" -m build --wheel >/dev/null )
WHL="$(ls "$HERE"/dist/*.whl | head -1)"
echo "   wheel: $(basename "$WHL")"

# 중립 CWD 로 이동 — repo 루트(./sage 존재)에서 실행하면 stdin/console 스크립트가 cwd 의 repo sage 를
# site-packages wheel 보다 먼저 import 해 번들 검증이 무력화된다. $WORK 엔 sage/ 가 없어 wheel 이 import 됨.
cd "$WORK"

echo "== [2/11] clean venv 설치 (wheel + jsonschema 만) =="
python3 -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install --quiet "$WHL" jsonschema >/dev/null
SAGE="$WORK/venv/bin/sage"
PY="$WORK/venv/bin/python"

echo "== [3/11] sage_root 가 번들(sage/_bundle)로 해석되는지 (repo fallback 아님) =="
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
from sage.done_criteria_contract import parse_done_criteria, phase00_text_hash
plan = "Done-Criteria-Revision: 1\n## 5. Done Criteria\n- [x] wheel contract\n"
result = parse_done_criteria(plan, mode="standard")
assert result.status == "valid" and not result.unresolved
assert phase00_text_hash(plan).startswith("sha256:")
print(f"   sage_root = {root} (번들 OK)")
PYEOF

PROJ="$WORK/proj"; mkdir -p "$PROJ"
echo "== [4/11] sage install (번들 → 신규 프로젝트 복사) =="
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
echo "== [4b/11] 부트스트랩 게이트 (빈 profile → generate BLOCK 기대) =="
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

echo "== [5/11] sage generate --kind hook --write (등록 산출물 + manifest 스탬프) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" generate --kind hook --write --dest "$PROJ" >/dev/null
test -f "$PROJ/.claude/settings.json" || { echo "❌ generate 가 .claude/settings.json 미생성"; exit 1; }
echo "   generate OK (.claude/settings.json 등록 산출물)"

echo "== [6/11] 설치 template 기반 project hook 등록 + 양 host 실제 dispatch =="
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

echo "== [7/11] sage validate --check --schema (전체 PASS 기대) =="
env -u SAGE_RESOURCE_ROOT "$SAGE" validate --check --schema --root "$PROJ"

echo "== [8/11] Fast Cycle wheel 진입점 + strict audit runtime =="
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

cat > "$WORK/check_status.py" <<'CHECKPY'
import json, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["schema_version"] == 1, payload
assert payload["status"] in ("READY", "ATTENTION", "BLOCKED", "ERROR"), payload["status"]
assert payload["runtime_api"]["current"] >= 1, payload["runtime_api"]
# marker 는 install/generate 가 스탬프한다 — 이 프로젝트는 방금 둘 다 거쳤다.
assert payload["runtime_api"]["required"] == payload["runtime_api"]["current"], payload["runtime_api"]
# 승인 설계가 요구한 수집 영역이 전부 실려야 한다. 하나가 빠지면 그 축은 조용히
# 판정되지 않은 채 READY 로 보인다.
assert set(payload) >= {"project", "version", "runtime_api", "profile", "host",
                        "cycle", "gate"}, sorted(payload)
assert payload["cycle"]["mode"] in ("STANDARD", "FAST", "UNKNOWN", None), payload["cycle"]
# 도구가 자기 일을 못 한 상태로 배포본이 나가면 안 된다.
assert payload["status"] != "ERROR", payload["diagnostics"]
for entry in payload["diagnostics"]:
    assert set(entry) == {"code", "severity", "evidence", "recovery"}, entry
    assert entry["severity"] != "BLOCK" or entry["recovery"], entry
    for step in entry["recovery"]:
        assert set(step) == {"id", "command", "mutating"}, step
CHECKPY

echo "== [9/11] 운영 진단 명령 + runtime API preflight (설치 wheel 단독) =="
# 설치본에서 실제로 도는지 본다. 엔진 소스 트리에서 도는 것은 배포 증거가 아니다.
# 조회가 상태를 만들지 않는다. 앞 단계(Fast Cycle open)가 남긴 파일은 정상이므로
# 존재 여부가 아니라 **조회 전후의 차이**를 본다.
ls -a "$PROJ/.sage" > "$WORK/sage_before.txt" 2>/dev/null || : > "$WORK/sage_before.txt"
env -u SAGE_RESOURCE_ROOT "$SAGE" status --root "$PROJ" --json > "$WORK/status.json" || true
ls -a "$PROJ/.sage" > "$WORK/sage_after.txt" 2>/dev/null || : > "$WORK/sage_after.txt"
diff "$WORK/sage_before.txt" "$WORK/sage_after.txt" > "$WORK/sage_diff.txt" \
  || { echo "❌ status 조회가 .sage 를 바꿨다"; cat "$WORK/sage_diff.txt"; exit 1; }
"$PY" "$WORK/check_status.py" "$WORK/status.json"
env -u SAGE_RESOURCE_ROOT "$SAGE" explain --path "src/wheel-smoke.py" --root "$PROJ" > "$WORK/explain.txt" || { echo "❌ explain 실패"; cat "$WORK/explain.txt"; exit 1; }
grep -q "Path risk floor:" "$WORK/explain.txt" || { echo "❌ explain 출력에 위험도 하한 없음"; exit 1; }
! grep -q "ALLOW" "$WORK/explain.txt" || { echo "❌ explain 이 허용을 단정함"; exit 1; }
env -u SAGE_RESOURCE_ROOT "$SAGE" explain --path "../outside.py" --root "$PROJ" > "$WORK/escape.txt" 2>&1 && { echo "❌ root 이탈 경로가 통과함"; exit 1; }
grep -q "explain.path_outside_root" "$WORK/escape.txt" || { echo "❌ 이탈 거부 code 없음"; exit 1; }
env -u SAGE_RESOURCE_ROOT "$SAGE" explain --path "src/x.py" --root "$WORK/no-such-project" >/dev/null 2>&1 \
  && { echo "❌ 없는 root 를 정상 프로젝트로 설명함"; exit 1; }
echo "   operability OK (7영역 + explain 비보증 + 경로 봉쇄 + 조회 무변경)"

cat > "$WORK/check_audit.py" <<'CHECKPY'
import json, os, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
project = sys.argv[2]
assert payload["schema_version"] == 1, payload
assert payload["status"] in ("OK", "ATTENTION", "ISSUES", "ERROR"), payload["status"]
# v1 최상위 계약. 빠지는 것도 늘어나는 것도 소비자에게는 같은 무게의 변경이다.
assert set(payload) == {"schema_version", "ok", "status", "exit_code", "ordering", "selection",
                        "sources", "events", "returned", "omitted", "truncated",
                        "diagnostics"}, sorted(payload)
assert payload["ok"] is (payload["exit_code"] == 0), payload["exit_code"]
assert payload["returned"] == len(payload["events"]), payload["returned"]
assert payload["truncated"] is (payload["omitted"] > 0), payload["omitted"]
assert set(payload["selection"]) == {"sources", "include_local", "cycle_stem",
                                     "run_id", "limit"}, payload["selection"]
assert payload["selection"]["limit"] == 100, payload["selection"]
# 진단의 정본은 하나다. `sources[]` 에 사본이 있으면 둘이 갈릴 수 있다.
# key 집합은 소비자 계약이므로 정상 경로에서도 정확히 고정한다.
for entry in payload["sources"]:
    assert "issues" not in entry, entry
    assert set(entry) == {"id", "path", "present", "record_count", "integrity",
                          "caveat", "policy", "tracking"}, sorted(entry)
# 도구가 자기 일을 못 한 상태로 배포본이 나가면 안 된다.
assert payload["status"] != "ERROR", payload["diagnostics"]
# 기본 조회는 공유 4종이다. 로컬 두 종이 관문 없이 섞이면 화면 공유만으로 개인 흔적이 나간다.
ids = [entry["id"] for entry in payload["sources"]]
assert ids == ["override", "acceptance", "review", "fast"], ids
# 앞 단계가 연 Fast run 이 보여야 한다. 안 보이면 설치본이 감사를 못 읽는 것이다.
fast = next(entry for entry in payload["sources"] if entry["id"] == "fast")
assert fast["present"] and fast["record_count"] >= 1, fast
assert fast["integrity"] == {"method": "strict_chain", "status": "valid"}, fast["integrity"]
# 검증이 없는 출처가 valid 로 표시되면 화면이 원본보다 강한 보증을 하는 것이다.
for entry in payload["sources"]:
    if entry["integrity"]["method"] == "none":
        assert entry["integrity"]["status"] != "valid", entry
# override 의 한계는 조건부로 숨기지 않는다.
override = next(entry for entry in payload["sources"] if entry["id"] == "override")
assert override["caveat"] == "audit.caveat.override_tracking_copy", override
# 절대경로·HOME 은 어떤 출력에도 없다. 주입한 줄은 `data` 가 아니라 `run_id`·`cycle_stem`·
# `ts` 에 경로를 넣는다 — allowlist 를 지나지 않는 자리라 "거를 key 를 고른" 구현은 통과시킨다.
blob = json.dumps(payload, ensure_ascii=False)
for leak in (project, os.path.expanduser("~"), "/Users/", "/home/"):
    assert leak not in blob, f"절대경로 노출: {leak}"
# 치환이 일어났다는 증거가 없으면 위 검사는 fixture 가 안 실린 채로도 통과한다.
assert "<redacted-path>" in blob, "주입한 경로 줄이 조회에 실리지 않았다"
injected = [item for item in payload["events"]
            if item["source"] == "override" and item["run_id"] == "<redacted-path>"]
assert injected, "meta 필드 치환 증거 없음"
assert injected[0]["cycle_stem"] == "<redacted-path>", injected[0]
assert injected[0]["occurred_at"] == "<redacted-path>", injected[0]
assert payload["ordering"] == "display_order_only", payload["ordering"]
for entry in payload["diagnostics"]:
    assert set(entry) == {"code", "severity", "evidence", "recovery"}, entry
    assert entry["severity"] != "BLOCK" or entry["recovery"], entry
    # source 결속은 evidence.source 하나로 한다. 전역 진단 둘만 예외다.
    if entry["code"] not in ("audit.source.truncated", "audit.selection.redacted"):
        assert "source" in entry["evidence"], entry
CHECKPY

echo "== [10/11] 통합 감사 조회 (설치 wheel 단독 · 조회 무변경 · 보증 미과장) =="
# 감사 파일을 쓸 수 있는 쪽은 메타 필드에 무엇이든 넣을 수 있다. 소비자 화면에서 그 값이
# 그대로 나오는지 여기서 본다 — 엔진 단위 검사만으로는 배포본의 화면을 증명하지 못한다.
LEAK="/Users/wheel-smoke/Obsidian/vault/leak.md"
mkdir -p "$PROJ/.sage"
printf '{"event":"grant","grant_id":"g-leak","ts":"%s","epoch":1767225600,"gate":"all","reason":"%s","ttl_seconds":60,"user":"smoke","run_id":"%s","cycle_stem":"%s"}\n' \
  "$LEAK" "$LEAK" "$LEAK" "$LEAK" >> "$PROJ/.sage/override.jsonl"
# retro 의 노트 경로는 저장소 상대경로로 정상이어도 나가지 않는다 — 존재 여부만 답한다.
printf '{"event":"retro_check_ok","ts":"2026-01-01T00:00:00+00:00","run_id":"r-smoke","note_path":"docs/notes/smoke.md","digest":"sha256:deadbeef"}\n' \
  >> "$PROJ/.sage/retro_audit.jsonl"

# 엔진 저장소에서 도는 것은 소비자 증거가 아니다. 설치본이 자기 감사를 읽는지 여기서 본다.
ls -a "$PROJ/.sage" > "$WORK/audit_before.txt" 2>/dev/null || : > "$WORK/audit_before.txt"
env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" --json > "$WORK/audit.json" || true
ls -a "$PROJ/.sage" > "$WORK/audit_after.txt" 2>/dev/null || : > "$WORK/audit_after.txt"
diff "$WORK/audit_before.txt" "$WORK/audit_after.txt" > "$WORK/audit_diff.txt" \
  || { echo "❌ audit show 가 .sage 를 바꿨다 (lock 파일 포함)"; cat "$WORK/audit_diff.txt"; exit 1; }
"$PY" "$WORK/check_audit.py" "$WORK/audit.json" "$PROJ"

# 화면도 같이 본다. JSON 만 검사하면 renderer 한쪽에만 남은 경로를 놓친다.
env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" > "$WORK/audit.txt" 2>&1 || true
grep -qF "<redacted-path>" "$WORK/audit.txt" \
  || { echo "❌ 화면에서 치환이 일어나지 않았다"; cat "$WORK/audit.txt"; exit 1; }
for leak in "$LEAK" "$PROJ" "$HOME"; do
  grep -qF "$leak" "$WORK/audit.txt" \
    && { echo "❌ 화면에 절대경로가 남았다: $leak"; exit 1; } || :
done

# 필터 값도 감사 값과 같은 sanitizer 를 지난다 — 되비추는 자리가 새 누출 표면이 된다.
env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" --json \
  --cycle-stem "$LEAK" --run-id "$LEAK" > "$WORK/audit_filter.json" || true
"$PY" - "$WORK/audit_filter.json" "$PROJ" <<'PYEOF'
import json, os, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
blob = json.dumps(payload, ensure_ascii=False)
for leak in (sys.argv[2], os.path.expanduser("~"), "/Users/", "/home/"):
    assert leak not in blob, f"필터 값으로 절대경로가 노출됨: {leak}"
assert payload["selection"]["cycle_stem"] == "<redacted-path>", payload["selection"]
assert payload["selection"]["run_id"] == "<redacted-path>", payload["selection"]
codes = {entry["code"] for entry in payload["diagnostics"]}
assert "audit.selection.redacted" in codes, "치환을 조용히 삼켰다"
PYEOF

# 도구 실패 경로의 source schema. 정상 경로만 보면 예외 때만 달라지는 계약을 못 잡는다.
"$PY" - "$PROJ" <<'PYEOF'
import io, json, sys
from contextlib import redirect_stdout

from sage import audit_sources
from sage.commands import audit as A


class Args:
    def __init__(self, root):
        self.root = root
        self.source = None
        self.include_local = True
        self.cycle_stem = None
        self.run_id = None
        self.limit = A.DEFAULT_LIMIT
        self.json = True
        self.lang = None


def boom(*_a, **_kw):
    raise RuntimeError("load_source itself failed")


audit_sources.load_source = boom
buffer = io.StringIO()
with redirect_stdout(buffer):
    code = A.run_show(Args(sys.argv[1]))
payload = json.loads(buffer.getvalue())

assert code == 2 and payload["status"] == "ERROR", (code, payload["status"])
assert payload["ok"] is False, payload["ok"]
expected = {"id", "path", "present", "record_count", "integrity",
            "caveat", "policy", "tracking"}
for entry in payload["sources"]:
    assert set(entry) == expected, sorted(entry)
    assert entry["policy"] in ("shared", "local"), entry
    # 도구 실패는 부재가 아니다. `False` 로 접히면 "기록 없음" 으로 읽힌다.
    assert entry["present"] is None, entry
codes = {item["code"] for item in payload["diagnostics"]}
assert "audit.source.unavailable" in codes, codes
PYEOF

# 로컬 출처 조회. 여기서만 retro 가 보이고, 보이더라도 노트 위치는 나오지 않아야 한다.
env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" --include-local --json \
  > "$WORK/audit_local.json" || true
"$PY" - "$WORK/audit_local.json" <<'PYEOF'
import json, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
blob = json.dumps(payload, ensure_ascii=False)
assert "note_path" not in blob, "retro note_path 가 노출됐다"
assert "docs/notes/smoke.md" not in blob, "retro 노트 경로가 노출됐다"
retro = [item for item in payload["events"] if item["source"] == "retro"]
assert retro, "로컬 관문을 열었는데 retro 가 보이지 않는다"
assert retro[0]["data"] == {"state": "ok", "vault_note_present": True,
                            "digest_present": True}, retro[0]["data"]
# 정책과 실제 추적 상태는 서로 다른 사실이다. 하나로 접으면 둘을 구분할 수 없다.
policies = {entry["id"]: entry["policy"] for entry in payload["sources"]}
assert policies["retro"] == "local" and policies["review"] == "shared", policies
assert all("tracking" in entry for entry in payload["sources"]), payload["sources"]
PYEOF

# `--limit` 범위는 계약이다. 범위 밖을 조용히 끌어당기면 요청한 값과 받은 값이 갈린다.
for bad in 0 -1 10001; do
  env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" --limit "$bad" >/dev/null 2>&1 \
    && { echo "❌ --limit $bad 가 통과했다 (0 은 무제한이 아니다)"; exit 1; } || :
done
for good in 1 10000; do
  env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" --limit "$good" >/dev/null 2>&1 \
    || { echo "❌ 범위 안 --limit $good 이 거절됐다"; exit 1; }
done

# 로컬 출처로 가는 관문은 하나다. 없으면 빈 결과가 아니라 usage 오류여야 한다.
env -u SAGE_RESOURCE_ROOT "$SAGE" audit show --root "$PROJ" --source retro >/dev/null 2>&1 \
  && { echo "❌ --include-local 없이 로컬 출처가 조회됐다"; exit 1; }

# JSON 은 언어를 타지 않는다. 같은 상태가 언어에 따라 다르면 기계가 대조할 수 없다.
env -u SAGE_RESOURCE_ROOT "$SAGE" --lang ko audit show --root "$PROJ" --json > "$WORK/audit_ko.json" || true
env -u SAGE_RESOURCE_ROOT "$SAGE" --lang en audit show --root "$PROJ" --json > "$WORK/audit_en.json" || true
cmp -s "$WORK/audit_ko.json" "$WORK/audit_en.json" \
  || { echo "❌ audit show --json 이 언어를 탄다"; exit 1; }
echo "   audit OK (조회 무변경 + schema v1 계약 + 보증 2축 + 단일 관문 + limit 범위 + locale 독립)"

echo "== [11/11] vault 없이 feedback·knowledge 실행 (설치 wheel 단독) =="

# 격리 경계를 먼저 세운다. 개발자 머신에는 이미 vault 가 있고 HOME 에 상태가 쌓여 있어서,
# 그 상태에서 통과한 "vault 없이 된다" 는 "내 머신에서 된다" 의 다른 이름이다.
ISO="$(mktemp -d "${TMPDIR:-/tmp}/sage-wheel-iso.XXXXXX")"
ISO_HOME="$ISO/home"; ISO_STATE="$ISO/state"; ISO_CODEX="$ISO/codex"; SENTINEL="$ISO/sentinel"
mkdir -p "$ISO_HOME" "$ISO_STATE" "$ISO_CODEX" "$SENTINEL/nested"
printf 'this file must not change\n' > "$SENTINEL/untouched.txt"
printf 'nested too\n' > "$SENTINEL/nested/untouched.txt"

# sentinel 은 프로젝트와 상태 홈 **밖** 이다. 안에 두면 "밖에 쓰지 않는다" 를 증명하지 못한다 —
# 증명하려는 경계의 안쪽을 재는 셈이 된다.
sentinel_hash() {
  "$PY" - "$SENTINEL" <<'SENTEOF'
import hashlib, os, sys

root = sys.argv[1]
digest = hashlib.sha256()
for current, dirs, files in os.walk(root):
    dirs.sort()
    for name in sorted(files):
        full = os.path.join(current, name)
        # 목록과 내용 둘 다 증거다. 내용만 재면 파일이 새로 생긴 것을 놓친다.
        digest.update(os.path.relpath(full, root).encode("utf-8") + b"\0")
        with open(full, "rb") as handle:
            digest.update(handle.read())
print(digest.hexdigest())
SENTEOF
}
SENTINEL_BEFORE="$(sentinel_hash)"

# vault 를 가리킬 수 있는 환경변수는 전부 지운다. 남겨 두면 이 단계가 증명하려는 조건
# (vault 가 없다)이 애초에 성립하지 않는다.
iso_env() {
  env -u SAGE_RESOURCE_ROOT -u OBSIDIAN_VAULT -u OBSIDIAN_HOME -u SAGE_VAULT -u SAGE_VAULT_PATH \
      HOME="$ISO_HOME" XDG_STATE_HOME="$ISO_STATE" SAGE_STATE_HOME="$ISO_STATE" \
      CODEX_HOME="$ISO_CODEX" "$@"
}
# 이 둘은 OFF 구성에서 파이프라인이 성공한다는 것까지만 확인돼 있었다. 필수 인수는 "동작한다"
# 이므로 실제로 실행해서 본다 — 구성이 꺼져 있어도 파이프라인이 통과하는 것과, 기능이 vault
# 없이 동작하는 것은 다른 사실이다.

# feedback 스캔은 git 추적 파일만 본다. 저장소가 아니면 조용히 0건이라 검사가 공허해진다.
git -C "$PROJ" init -q
git -C "$PROJ" config user.email smoke@example.com
git -C "$PROJ" config user.name smoke
mkdir -p "$PROJ/src"
printf '# !sage-feedback :: this branch does not match the plan\nvalue = 1\n' > "$PROJ/src/wheel-smoke.py"
git -C "$PROJ" add -A >/dev/null
git -C "$PROJ" -c commit.gpgsign=false commit -qm smoke >/dev/null

"$PY" - "$PROJ/sage/project-profile.yaml" <<'PROFEOF'
import sys

path = sys.argv[1]
text = open(path, encoding="utf-8").read()
# feedback 섹션 안의 세 값만 바꾼다. 같은 이름을 쓰는 다른 섹션을 건드리지 않도록 구간을 자른다.
lines = text.split("\n")
start = next(i for i, line in enumerate(lines) if line.startswith("feedback:"))
# 다음 최상위 key 까지가 이 섹션이다. 섹션 이름으로 끝을 잡으면 profile 순서가 바뀔 때 깨진다.
end = next((i for i in range(start + 1, len(lines))
            if lines[i][:1] not in ("", " ", "\t", "#")), len(lines))
block = "\n".join(lines[start:end])
for before, after in (("enabled: false", "enabled: true"),
                      ("record: false", "record: true"),
                      ("record_target: auto", "record_target: sage")):
    assert before in block, f"profile 의 feedback 섹션에 {before!r} 가 없다"
    block = block.replace(before, after, 1)
open(path, "w", encoding="utf-8").write(
    "\n".join(lines[:start] + block.split("\n") + lines[end:]))
PROFEOF

iso_env "$SAGE" feedback --root "$PROJ" --output json > "$WORK/fb.json" \
  || { echo "❌ vault 없이 feedback 스캔 실패"; cat "$WORK/fb.json"; exit 1; }
"$PY" - "$WORK/fb.json" <<'FBEOF'
import json, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["enabled"] is True, payload
assert payload["counts"]["blocking"] >= 1, payload["counts"]
assert any(item["path"] == "src/wheel-smoke.py" for item in payload["markers"]), payload
FBEOF

iso_env "$SAGE" feedback --root "$PROJ" --record \
  --path src/wheel-smoke.py --line 1 --verdict undetermined --note smoke >/dev/null \
  || { echo "❌ vault 없이 feedback 기록 실패"; exit 1; }
test -f "$PROJ/.sage/feedback.jsonl" || { echo "❌ .sage/feedback.jsonl 미생성"; exit 1; }

# 기록된 것이 조회로 보여야 한다. 안 보이면 기록과 조회 중 어느 쪽이 틀렸는지 알 수 없다.
iso_env "$SAGE" audit show --root "$PROJ" --include-local \
  --source feedback --json > "$WORK/fb_audit.json" || true
"$PY" - "$WORK/fb_audit.json" <<'FBAEOF'
import json, sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
entry = next(item for item in payload["sources"] if item["id"] == "feedback")
assert entry["present"] and entry["record_count"] >= 1, entry
assert entry["policy"] == "local", entry
events = [item for item in payload["events"] if item["source"] == "feedback"]
# `undetermined` 는 코드·마커를 그대로 두는 분기다. 해소 분기를 쓰면 마커를 지우지 않은 채
# 해소로 기록하게 되어, 검사가 실제 워크플로와 다른 모양을 굳힌다.
assert events and events[0]["data"]["verdict"] == "undetermined", events
FBAEOF

# knowledge 는 `vault_path: ""` 에서 실제로 돌아 n/a 보고서를 남겨야 한다. 조용히 아무것도
# 하지 않으면 "스캔했는데 결과 없음" 과 "스캔 자체가 안 됨" 이 구분되지 않는다.
iso_env "$SAGE" knowledge scan --root "$PROJ" --query smoke > "$WORK/kn.txt" 2>&1 \
  || { echo "❌ vault 없이 knowledge scan 실패"; cat "$WORK/kn.txt"; exit 1; }
test -f "$PROJ/.sage/knowledge_scan.md" || { echo "❌ .sage/knowledge_scan.md 미생성"; exit 1; }
grep -qi "n/a" "$PROJ/.sage/knowledge_scan.md" \
  || { echo "❌ knowledge_scan 상태가 n/a 가 아님"; cat "$PROJ/.sage/knowledge_scan.md"; exit 1; }
grep -qi "vault_path empty" "$PROJ/.sage/knowledge_scan.md" \
  || { echo "❌ n/a 사유가 기록되지 않음"; cat "$PROJ/.sage/knowledge_scan.md"; exit 1; }

# vault 산출물 검사는 프로젝트 밖 격리 경계까지 본다. 프로젝트 안만 보면 HOME·상태 홈에
# 만들어진 vault 를 통과시킨다 — 정확히 no-vault 계약이 깨지는 자리를 안 보는 셈이다.
found="$(find "$PROJ" "$ISO" -iname "*vault*" -not -path "*/.git/*" | head -5)"
test -z "$found" || { echo "❌ vault 산출물이 생성됨: $found"; exit 1; }

SENTINEL_AFTER="$(sentinel_hash)"
test "$SENTINEL_BEFORE" = "$SENTINEL_AFTER" || {
  echo "❌ 프로젝트·상태 홈 밖 sentinel 이 변경됨"
  echo "   before=$SENTINEL_BEFORE after=$SENTINEL_AFTER"
  find "$SENTINEL" -type f
  exit 1
}
echo "   no-vault feedback·knowledge OK (격리 HOME·상태 홈 + 마커 스캔 + 기록 + 조회 + n/a 보고서"
echo "      + 경계 밖 vault 산출물 0건 + sentinel 무변경)"

echo "✅ 순수 wheel 단독배포 게이트 PASS — 번들 리소스만으로 install→generate→validate 폐루프 동작"
