"""sage generate — spec-SSOT → 런타임 산출물 생성 (Codex 2R 합의).

결정론 코어 = hook 등록 산출물(settings.json/hooks.json) + manifest 스탬프.
- adapter 본문은 재생성 안 함(§5.5 M4: reverse_extract 정본). 없으면 FAIL.
- agent/skill render 는 interpretive(런타임 AI) → generate 는 안내 + manifest 스탬프만(스켈레톤은 extract_* 드라이버).
- generate CLI 는 편집도구 밖이라 write guard 대상 아님(§5.6 G3).
등록 순서는 hook id lexicographic 정렬로 결정론 보장.
"""
import json
import os
import re
import stat
import sys
from copy import deepcopy
from pathlib import Path

from sage import __version__
from sage import overlay_common as _oc
from sage.asset_paths import AssetPaths, docs_dir, hook_runtime_files
from sage.commands._common import contract_version_of
from sage.hook_launcher import command_template as hook_command_template, valid_hook_id
from sage.hook_runtime_hash import calculate_hook_runtime_hash
from sage.install_transaction import (
    DestinationLock,
    InstallBusyError,
    InstallDriftError,
    InstallTransaction,
    capture_paths,
)
from sage.manifest_io import atomic_write_json
from sage.i18n import tr


def register(sub, context):
    p = sub.add_parser("generate", help=tr(context, "cli.generate.generate"))
    p.add_argument("--kind", choices=["hook", "agent", "skill", "roster", "mcp"], required=True)
    p.add_argument("--id", default=None, help=tr(context, "cli.generate.id"))
    p.add_argument("--write", action="store_true", help=tr(context, "cli.generate.write"))
    p.add_argument("--target", choices=["claude", "codex", "both"], default="claude",
                   help=tr(context, "cli.generate.target"))
    p.add_argument("--dest", default=".", help=tr(context, "cli.generate.dest"))
    p.add_argument("--root", default=None, help=tr(context, "cli.generate.root"))
    p.add_argument("--from-existing", default=None, metavar="AGENT_ID",
                   help=tr(context, "cli.generate.from_existing"))
    p.add_argument("--deploy-codex", action="store_true",
                   help=tr(context, "cli.generate.deploy_codex"))
    p.set_defaults(func=run)


def _find_root(start):
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "docs", "sage_harness", ".manifest.json")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _parse_runtime_bindings(spec_path):
    """hook spec frontmatter 의 runtime_bindings YAML 블록을 간이 파싱(pyyaml 비의존).

    형식: runtime_bindings:\n  claude: { event: X, matcher: "Y", timeout: N }\n  codex: {...}
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}
    fm = m.group(1)
    out = {}
    in_rb = False
    for line in fm.splitlines():
        if re.match(r"^runtime_bindings:\s*$", line):
            in_rb = True
            continue
        if in_rb:
            rm = re.match(r'^\s+(claude|codex):\s*\{(.+)\}\s*$', line)
            if rm:
                rt, body = rm.group(1), rm.group(2)
                d = {}
                for kv in re.finditer(r'(\w+):\s*("(?:[^"]*)"|[^,}]+)', body):
                    k, v = kv.group(1), kv.group(2).strip().strip('"')
                    d[k] = int(v) if v.isdigit() else v
                out[rt] = d
            elif not line.startswith(" "):
                break
    return out


def _command_template(target, hook_id):
    """런타임별 등록 command 문자열.

    Windows는 bash 비의존 console entrypoint를 유지한다. POSIX는 GUI/IDE가 사용자 PATH를
    상속하지 않는 경우에도 pipx 기본 app 경로를 찾고, 커스텀 설치는 SAGE_HOOK_BIN으로 지정한다.
    """
    return hook_command_template(target, hook_id, platform_name=os.name)


def _build_registration(root, target, hook_ids, project_hooks=None):
    """hook id 정렬 → target 별 {Event: [{matcher, hooks:[...]}]} 등록 dict (결정론).

    같은 event+matcher 는 한 블록에 hooks append. adapter 파일 존재 확인(없으면 (None, missing))."""
    missing = []
    project_hooks = project_hooks or {}
    # event → matcher → [command블록]  (matcher 안정 정렬)
    by_event = {}
    for hid in sorted(hook_ids):   # lexicographic 정렬(결정론)
        if not valid_hook_id(hid):
            missing.append(f"hook-id:{hid}")
            continue
        ap = AssetPaths(root, "hook", hid)
        if not os.path.exists(ap.spec):
            missing.append(f"spec:{hid}"); continue
        rb = (project_hooks[hid]["bindings"] if hid in project_hooks
              else _parse_runtime_bindings(ap.spec))
        if target not in rb:
            continue
        # adapter/native 파일 존재 확인 (경로 규약 AssetPaths 단일소스 — P2-6)
        if hid not in project_hooks and not (os.path.exists(ap.adapter(target)) or os.path.exists(ap.native)):
            missing.append(f"adapter:{target}:{hid}")
            continue
        ev = rb[target].get("event", "PreToolUse")
        mt = rb[target].get("matcher", "")
        to = rb[target].get("timeout", 10)
        blk = {"type": "command", "command": _command_template(target, hid), "timeout": to}
        by_event.setdefault(ev, {}).setdefault(mt, []).append(blk)

    reg = {}
    for ev in sorted(by_event):
        reg[ev] = [{"matcher": mt, "hooks": by_event[ev][mt]} for mt in sorted(by_event[ev])]
    return reg, missing


_RUNTIME_DIR = {"claude": ".claude", "codex": ".codex"}
_ROOT_ENV = {"claude": "CLAUDE_PROJECT_DIR", "codex": "CODEX_PROJECT_ROOT"}


def _shim_body(target, hook_id, form):
    """{host}/hooks/{id}.sh — 생성된 얇은 shim. 정본 adapter/native 는 scripts/ 에 단일소스로 둔다.

    런타임에 PROJECT_ROOT 를 해석해 SAGE_HOOK_CORE_DIR/SAGE_PROFILE 를 주입하고 정본을 exec.
    (정본을 {host}/ 로 복붙하지 않음 → 상대 CORE_DIR 깨짐 방지 + 단일소스 유지.)
    """
    root_env = _ROOT_ENV[target]
    canon = (f'$ROOT/scripts/sage_harness/hooks/adapters/{target}/{hook_id}.sh'
             if form != "native" else f'$ROOT/scripts/sage_harness/hooks/{hook_id}.sh')
    return (
        "#!/usr/bin/env bash\n"
        "# generated by sage generate — do not edit. canonical: scripts/sage_harness/hooks (단일소스).\n"
        f'ROOT="${{SAGE_PROJECT_ROOT:-${{{root_env}:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}}}"\n'
        'export SAGE_HOOK_CORE_DIR="$ROOT/scripts/sage_harness/hooks"\n'
        '[ -z "${SAGE_PROFILE:-}" ] && [ -f "$ROOT/sage/project-profile.json" ] && '
        'export SAGE_PROFILE="$ROOT/sage/project-profile.json"\n'
        f'exec bash "{canon}" "$@"\n'
    )


def _write_hook_shims(args, root, manifest, hook_ids, target):
    """등록된 CORE hook 마다 {host}/hooks/{id}.sh shim 생성(실행권한)."""
    hooks_dir = os.path.join(args.dest, _RUNTIME_DIR[target], "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    written = 0
    for hid in sorted(hook_ids):
        form = manifest["assets"].get(f"hooks/{hid}", {}).get("form", "core_adapter")
        # 해당 target adapter/native 정본 존재 확인(없으면 shim 생략)
        canon = (os.path.join(root, "scripts", "sage_harness", "hooks", "adapters", target, f"{hid}.sh")
                 if form != "native" else os.path.join(root, "scripts", "sage_harness", "hooks", f"{hid}.sh"))
        if not os.path.exists(canon):
            continue
        p = os.path.join(hooks_dir, f"{hid}.sh")
        Path(p).write_text(_shim_body(target, hid, form), encoding="utf-8")
        os.chmod(p, 0o755)
        written += 1
    print(f"   ↳ ({target}) hook shim {written}건: {os.path.relpath(hooks_dir, args.dest)}/*.sh")


def _compile_profile(root, dest):
    """Compile a profile in memory; callers own validation and transactional writing.

    반환: (status, data, body, output_path). status = none|ok|fail.
    fail-closed(Codex 2R): profile 이 있는데 컴파일 실패하면 hook 이 조용히 pass-open 되어
    risk gate 가 무력화된다 → generate 가 실패로 보고한다. pyyaml 은 generate(빌드) 의존성(pyproject 선언).
    """
    yml = os.path.join(dest, "sage", "project-profile.yaml")
    if not os.path.exists(yml):
        yml = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(yml):
        return "none", None, None, None
    try:
        import yaml
        data = yaml.safe_load(Path(yml).read_text(encoding="utf-8")) or {}
    except ImportError:
        print("   ❌ profile 컴파일 실패: pyyaml 미설치 (generate 빌드 의존성 — pip install pyyaml).", file=sys.stderr)
        return "fail", None, None, None
    except Exception as e:
        print(f"   ❌ profile 컴파일 실패: YAML 파싱 오류 ({type(e).__name__}: {e}).", file=sys.stderr)
        return "fail", None, None, None
    from sage.profile_compile import ProfileCompileError, materialize_profile
    try:
        data = materialize_profile(data)
    except ProfileCompileError as e:
        print(f"   ❌ profile 컴파일 실패: raw risk 필드 타입 오류 ({e}).", file=sys.stderr)
        return "fail", None, None, None
    outp = os.path.join(dest, "sage", "project-profile.json")
    body = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return "ok", data, body, outp


def _existing_mode(path, default_mode):
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return default_mode
    if not stat.S_ISREG(current.st_mode):
        raise InstallDriftError(f"generate output is not a regular file: {path}")
    return stat.S_IMODE(current.st_mode)


def _transaction_write(transaction, path, body, default_mode, preserve_existing_mode):
    mode = (_existing_mode(path, default_mode) if preserve_existing_mode else default_mode)
    transaction.stage_write(path)
    transaction.declare_file_output(path, body, mode)
    _oc.write_text_lf(path, body, mode=mode)
    transaction.record_output(path)


def _host_registration_body(target, outp, registration):
    document = {"hooks": registration}
    if os.path.exists(outp):
        try:
            existing = json.loads(Path(outp).read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"{target} hook registration JSON 손상: {exc}") from exc
        if not isinstance(existing, dict):
            raise ValueError(f"{target} hook registration JSON 루트는 object여야 함")
        existing["hooks"] = registration
        document = existing
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def _stamped_manifest(root, manifest, hook_ids, runtime_hash):
    import hashlib

    def sha(path):
        return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

    stamped = deepcopy(manifest)
    stamped["generator_version"] = __version__
    stamped["hook_runtime_hash"] = runtime_hash
    for hid in hook_ids:
        entry = stamped["assets"].get(f"hooks/{hid}")
        if not entry:
            continue
        paths = AssetPaths(root, "hook", hid)
        if os.path.exists(paths.spec):
            entry["spec_hash"] = sha(paths.spec)
        if entry.get("form") == "native":
            if os.path.exists(paths.native):
                entry["canonical_hash"] = sha(paths.native)
                entry["render_hash"] = {"native": sha(paths.native)}
            continue
        if os.path.exists(paths.core):
            entry["canonical_hash"] = sha(paths.core)
            contract_version = contract_version_of(paths.core)
            if contract_version:
                entry["adapter_contract_version"] = contract_version
        adapter_hashes = {}
        for runtime in ("claude", "codex"):
            adapter = paths.adapter(runtime)
            if os.path.exists(adapter):
                adapter_hashes[runtime] = sha(adapter)
        if adapter_hashes:
            entry["adapter_hash"] = adapter_hashes
            entry["render_hash"] = adapter_hashes
    return stamped


def _gen_hook(args, root):
    """Serialize write-mode planning and apply with the install destination lock."""
    if not args.write:
        return _gen_hook_locked(args, root)
    lock_roots = sorted({os.path.abspath(args.dest), os.path.abspath(root)})
    locks = [DestinationLock(path) for path in lock_roots]
    try:
        for lock in locks:
            lock.acquire()
        return _gen_hook_locked(args, root)
    except (OSError, ValueError, InstallBusyError, InstallDriftError) as exc:
        print(f"[sage generate] FAIL: 생성 preflight 실패 — {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    finally:
        for lock in reversed(locks):
            lock.release()


def _gen_hook_locked(args, root):
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    preflight_fingerprints = capture_paths([manifest_path])
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), dict):
        print("[sage generate] FAIL: manifest 루트/assets 구조가 손상됨", file=sys.stderr)
        return 2
    manifest = deepcopy(manifest)
    assets = manifest["assets"]
    all_hook_ids = [k.split("/", 1)[1] for k in assets if k.startswith("hooks/")]
    registered_inputs = []
    for hook_id in all_hook_ids:
        paths = AssetPaths(root, "hook", hook_id)
        registered_inputs.extend((paths.spec, paths.core, paths.native,
                                  paths.adapter("claude"), paths.adapter("codex")))
    for runtime_paths in hook_runtime_files(root).values():
        registered_inputs.extend(runtime_paths)
    preflight_fingerprints.update(capture_paths(registered_inputs))
    project_hooks = {}
    canonical_adapter_writes = []

    from sage.project_hook_contract import adapter_body, inspect_project_hook
    if args.id and args.id not in all_hook_ids:
        spec_candidate = os.path.join(root, "docs", "sage_harness", "hooks", f"{args.id}.md")
        core_candidate = os.path.join(root, "scripts", "sage_harness", "hooks",
                                      f"{args.id.replace('-', '_')}_core.py")
        preflight_fingerprints.update(capture_paths([spec_candidate, core_candidate]))
        if not (os.path.lexists(spec_candidate) or os.path.lexists(core_candidate)):
            print(f"[sage generate] TOOL ERROR: manifest 에 hooks/{args.id} 없음", file=sys.stderr)
            return 2
        if args.write and args.target != "both":
            print("[sage generate] TOOL ERROR: 신규 project hook 등록은 --target both 가 필수입니다",
                  file=sys.stderr)
            return 2
        metadata, issues = inspect_project_hook(root, args.id)
        if issues:
            for issue in issues:
                print(f"[sage generate] TOOL ERROR: {issue}", file=sys.stderr)
            return 2
        assets[f"hooks/{args.id}"] = {
            "origin": "project", "form": "core_adapter", "conformance": "UNKNOWN",
            "adapter_contract_version": metadata["contract_version"],
        }
        all_hook_ids.append(args.id)
        project_hooks[args.id] = metadata

    from sage.commands.install import _CORE_HOOKS
    engine_hook_ids = {hook_id for hook_id, _form in _CORE_HOOKS}
    for hid in sorted(all_hook_ids):
        entry = assets.get(f"hooks/{hid}")
        paths_for_id = AssetPaths(root, "hook", hid)
        if not isinstance(entry, dict):
            print(f"[sage generate] TOOL ERROR: manifest hooks/{hid} entry는 object여야 함",
                  file=sys.stderr)
            return 2
        has_project_sources = (
            hid not in engine_hook_ids
            and os.path.isfile(paths_for_id.spec) and os.path.isfile(paths_for_id.core)
        )
        if has_project_sources and entry.get("form") != "core_adapter":
            print(f"[sage generate] TOOL ERROR: project hook hooks/{hid} form 손상 — "
                  "core_adapter 필요; canonical form은 자동 변환하지 않습니다", file=sys.stderr)
            return 2
        # Authored spec+core is sufficient provenance to route every generation mode through
        # the strict project contract. Otherwise an all-hook run could fall back to the legacy
        # CORE frontmatter parser and publish bindings that the project validator rejects.
        recoverable_project = (
            hid not in engine_hook_ids
            and entry.get("form") == "core_adapter" and has_project_sources
        )
        if entry.get("origin") != "project" and not recoverable_project:
            continue
        if entry.get("form") != "core_adapter":
            print(f"[sage generate] TOOL ERROR: project hook hooks/{hid} form 손상 — core_adapter 필요",
                  file=sys.stderr)
            return 2
        project_paths = AssetPaths(root, "hook", hid)
        preflight_fingerprints.update(capture_paths([project_paths.spec, project_paths.core]))
        metadata, issues = inspect_project_hook(root, hid)
        if issues:
            for issue in issues:
                print(f"[sage generate] TOOL ERROR: {issue}", file=sys.stderr)
            return 2
        entry["origin"] = "project"
        entry["adapter_contract_version"] = metadata["contract_version"]
        project_hooks[hid] = metadata

    for hid, metadata in sorted(project_hooks.items()):
        import hashlib
        adapter_hashes = {}
        for runtime in ("claude", "codex"):
            adapter_path = AssetPaths(root, "hook", hid).adapter(runtime)
            preflight_fingerprints.update(capture_paths([adapter_path]))
            expected_body = adapter_body(runtime, hid)
            adapter_hashes[runtime] = "sha256:" + hashlib.sha256(
                expected_body.encode("utf-8")).hexdigest()
            if os.path.lexists(adapter_path):
                if (not os.path.isfile(adapter_path) or os.path.islink(adapter_path)
                        or Path(adapter_path).read_text(encoding="utf-8") != expected_body):
                    print(f"[sage generate] TOOL ERROR: project hook adapter 손상/비정본: {adapter_path}",
                          file=sys.stderr)
                    return 2
            else:
                canonical_adapter_writes.append((adapter_path, expected_body, 0o755))
        assets[f"hooks/{hid}"]["adapter_hash"] = adapter_hashes
        assets[f"hooks/{hid}"]["render_hash"] = dict(adapter_hashes)
    if args.id:
        if args.id not in all_hook_ids:
            print(f"[sage generate] TOOL ERROR: manifest 에 hooks/{args.id} 없음", file=sys.stderr); return 2
        stamp_ids = [args.id]
    else:
        stamp_ids = all_hook_ids
    # F6: 등록(settings.json)/shim 은 항상 전체 hook 으로 구성한다. --id 로 좁히면 나머지 hook 의
    # 등록이 settings.json 에서 사라져 조용히 비활성화되므로(register 클로버) — --id 는 "스탬프 범위"만 한정.
    reg_ids = all_hook_ids

    # profile 컴파일 먼저(fail-closed): 실패면 산출물 쓰기 전에 중단 — hook risk gate 무력화 방지(Codex 2R)
    profile_sources = [os.path.join(args.dest, "sage", "project-profile.yaml")]
    if os.path.abspath(args.dest) != os.path.abspath(root):
        profile_sources.append(os.path.join(root, "sage", "project-profile.yaml"))
    preflight_fingerprints.update(capture_paths(profile_sources))
    profile_status, profile_data, profile_body, profile_path = _compile_profile(root, args.dest)
    runtime_hash = None
    if args.write:
        status = profile_status
        if status == "fail":
            print("[sage generate] FAIL: profile 컴파일 실패 → hook risk gate 무력화 위험. "
                  "pyyaml 설치 또는 YAML 수정 후 재실행(profile 없는 프로젝트면 sage/project-profile.yaml 제거).",
                  file=sys.stderr)
            return 1
        # R2/P0-2: 컴파일된 profile 구조+의미 검증. FAIL(오타 키·전략 모듈 부재·미정의 phase 참조)이면
        # 산출물 쓰기 전 중단 — "유효 YAML 이지만 게이트가 침묵 비활성되는" profile 의 배포 차단.
        if status == "ok":
            from sage.profile_validate import severity_of, validate_profile
            issues = validate_profile(profile_data, root)
            for sev, msg in issues:
                mark = {"FAIL": "❌", "WARN": "⚠️ ", "INFO": "ℹ️ "}.get(sev, "")
                print(f"   {mark} profile {sev}: {msg}", file=sys.stderr if sev == "FAIL" else sys.stdout)
            if severity_of(issues) == "FAIL":
                print("[sage generate] FAIL: profile 검증 실패 → 게이트 침묵 비활성 위험. "
                      "위 항목 수정 후 재실행.", file=sys.stderr)
                return 1
        # hook 공용 런타임이 없으면 registration/settings 를 먼저 쓰고 manifest 에서 실패하는
        # 부분 산출물이 생긴다. 산출 전 preflight 로 닫는다.
        runtime_hash, missing_runtime = calculate_hook_runtime_hash(root)
        if missing_runtime:
            print("[sage generate] FAIL: hook_runtime_hash 스탬프 불가 — runtime 파일 누락: " +
                  ", ".join(os.path.relpath(p, root) for p in missing_runtime), file=sys.stderr)
            return 1

    # 엔진 저장소에서 릴리즈 스탬프용으로 generate 를 돌리면(정당한 용도) 부수적으로 host 등록
    # 산출물이 저장소 루트에 생겼다. 그러면 다음 세션에서 SAGE 자신의 게이트가 프로필 없는
    # 디렉터리를 fail-closed 로 막아 SAGE 개발이 멈춘다(2026-06-17·07-24 두 번). 스탬프는 그대로
    # 하고 등록·shim 쓰기만 막는다 — 검증(누락 adapter FAIL)은 유지하고 내용은 dry-run 으로 보인다.
    from sage import _resources
    engine_tree = _resources.is_engine_source_tree(args.dest)
    if args.write and engine_tree:
        print("  ℹ️  엔진 저장소 — host 등록 산출물(.claude/settings.json · hooks/*.sh) 쓰기 생략. "
              "엔진 저장소는 설치 산출물을 보유하지 않습니다(manifest 스탬프는 그대로 수행).")

    targets = ["claude", "codex"] if args.target == "both" else [args.target]
    planned = []
    for tgt in targets:
        reg, missing = _build_registration(root, tgt, reg_ids, project_hooks=project_hooks)
        if missing:
            print(f"[sage generate] FAIL ({tgt}): 누락 — {', '.join(missing)} (adapter 는 reverse_extract 정본)", file=sys.stderr)
            return 1
        outp = os.path.join(args.dest, _RUNTIME_DIR[tgt],
                            "settings.json" if tgt == "claude" else "hooks.json")
        preflight_fingerprints.update(capture_paths([outp]))
        try:
            body = _host_registration_body(tgt, outp, reg)
        except ValueError as exc:
            print(f"[sage generate] FAIL: {exc}", file=sys.stderr)
            return 1
        shims = []
        for hid in sorted(reg_ids):
            form = manifest["assets"].get(f"hooks/{hid}", {}).get("form", "core_adapter")
            canonical = (os.path.join(root, "scripts", "sage_harness", "hooks", "adapters", tgt, f"{hid}.sh")
                         if form != "native" else os.path.join(root, "scripts", "sage_harness", "hooks", f"{hid}.sh"))
            if hid in project_hooks or os.path.exists(canonical):
                shim_path = os.path.join(args.dest, _RUNTIME_DIR[tgt], "hooks", f"{hid}.sh")
                shims.append((shim_path, _shim_body(tgt, hid, form)))
        planned.append((tgt, reg, outp, body, shims))
        if not args.write or engine_tree:
            label = "engine-skip" if engine_tree else "dry-run"
            print(f"== generate {tgt} ({label}) ==\n{body}")

    if not args.write:
        return 0

    stamped = _stamped_manifest(root, manifest, stamp_ids, runtime_hash)
    manifest_body = json.dumps(stamped, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    # JSON documents preserve an existing project mode. Security/runtime artifacts converge
    # to their declared modes even when an older generator left broader or non-executable modes.
    writes = [(manifest_path, manifest_body, 0o644, True)]
    if profile_status == "ok":
        writes.append((profile_path, profile_body, 0o600, False))
    if not engine_tree:
        for _tgt, _reg, outp, body, shims in planned:
            writes.append((outp, body, 0o644, True))
            writes.extend((path, body, 0o755, False) for path, body in shims)
    writes.extend((path, body, mode, False)
                  for path, body, mode in canonical_adapter_writes)

    lock_roots = sorted({os.path.abspath(args.dest), os.path.abspath(root)})
    transaction = None
    try:
        expected = dict(preflight_fingerprints)
        uncaptured = [path for path, _body, _mode, _preserve_mode in writes
                      if os.path.abspath(path) not in expected]
        expected.update(capture_paths(uncaptured))
        transaction = InstallTransaction(expected=expected, write_roots=lock_roots)
        for path, body, mode, preserve_mode in writes:
            _transaction_write(transaction, path, body, mode, preserve_mode)
        transaction.verify_unconsumed()
        transaction.verify_outputs()
        cleanup_errors = transaction.commit()
        if cleanup_errors:
            print("[sage generate] WARN: transaction backup 정리 실패 — " + "; ".join(cleanup_errors),
                  file=sys.stderr)
    except (OSError, ValueError, InstallBusyError, InstallDriftError) as exc:
        rollback_errors = transaction.rollback() if transaction is not None else []
        suffix = ("; rollback 경고: " + "; ".join(rollback_errors)) if rollback_errors else ""
        print(f"[sage generate] FAIL: 원자적 생성 실패 — {type(exc).__name__}: {exc}{suffix}",
              file=sys.stderr)
        return 1
    if profile_status == "ok":
        print(f"   ↳ profile 컴파일: {os.path.relpath(profile_path, args.dest)} (hook 런타임 입력)")
    if not engine_tree:
        for tgt, reg, outp, _body, shims in planned:
            print(f"✅ ({tgt}) 등록 생성: {os.path.relpath(outp, args.dest)} — "
                  f"{sum(len(v) for v in reg.values())} event 블록")
            print(f"   ↳ ({tgt}) hook shim {len(shims)}건: {_RUNTIME_DIR[tgt]}/hooks/*.sh")
    print("✅ manifest 스탬프 갱신")
    return 0


def _stamp_generator_version(root):
    """Stamp a successful non-hook generate write with the executing package version."""
    path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")
    manifest["generator_version"] = __version__
    atomic_write_json(path, manifest)


def _load_profile_dict(root, dest):
    """profile.yaml → dict. 없으면 {}(components 없음=폴백). 파싱 실패 → None. (EH-1 roster 용)"""
    yml = os.path.join(dest, "sage", "project-profile.yaml")
    if not os.path.exists(yml):
        yml = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(yml):
        return {}
    try:
        import yaml
        return yaml.safe_load(Path(yml).read_text(encoding="utf-8")) or {}
    except Exception:
        return None


def _implementer_spec_md(comp_id, paths, model, active_runtime="claude", runtime_model=None):
    """profile.components[comp_id] → 중립 implementer 에이전트 spec(.md) 결정론 직렬화 (EH-1).

    스택/경로는 profile 에서만 옴(엔진 도메인값 0). owns=component.paths, intent 는 컴포넌트 id 만 참조."""
    owns = ", ".join(paths) if paths else f"(profile.components[{comp_id}].paths)"
    return f"""---
id: implementer-{comp_id}
kind: agent
# generated by `sage generate --kind roster` from profile.components[{comp_id}] (EH-1 dynamic roster).
# neutral — edit profile.components, not stack values here.
---
## intent
Design, implementation, and component-level unit tests for the `{comp_id}` component,
plus production code-convention verification within its boundary.

## advisory_scope
- owns: {owns}
- role_boundary: integration / HTTP / boundary-value / scenario tests are the qa agent's scope;
  this agent writes component-level unit tests only. Cross-component work coordinates at integration points.
- uses: convention/test skills declared in profile.team
- convention_doc: (component convention doc declared in profile.conventions)

## runtime_bindings
- model: {model}   # work-intensity tier (opus=heavy / sonnet=standard); claude-host maps it to the
                   # Claude subagent model, codex-host treats it as a nominal tier (Codex uses its own model)
- active_host: {active_runtime}
- runtime_model: {runtime_model or 'host-default'}   # profile.components[].runtime_models selection
- claims/allowlist are auto-derived into {{id}}.claims.yml by reverse_extract

## drift_checks
- conformance: required/forbidden claim presence (machine-check, no LLM judge)
"""


def _overlay_source_path(dest, aid):
    return os.path.join(dest, "sage", "asset_overrides", "agents", f"{aid}.md")


# compose_block 이 본문 앞에 붙이는 고정 헤더(additive-only 고지). 시드에는 옮기지 않는다 —
# 새 렌더는 CORE 에 "더하는" 관리 구간이 아니라 그 자체가 프로젝트 소유 본문이기 때문이다.
_OVERLAY_HEADER_PREFIXES = ("## Project-Local Additions", "아래는 이 프로젝트", "AGENT_GUIDE·phase")


def _overlay_body_from_render(src_text):
    """설치본 렌더에 물리 합성된 오버레이 본문만 뽑는다(마커·고지 헤더 제외).

    오버레이 원본(`sage/asset_overrides/`)이 사라진 프로젝트에서는 규칙이 합성 결과에만 남아
    있다. 원본만 보고 시드하면 그 프로젝트의 규칙이 조용히 증발한다.
    """
    block = _oc.extract_block(src_text or "")
    if not block:
        return ""
    lines = [ln for ln in block.splitlines()
             if ln not in (_oc.MARKER_START, _oc.MARKER_END)]
    while lines and lines[0].startswith(_OVERLAY_HEADER_PREFIXES):
        lines.pop(0)
    return "\n".join(lines).strip()


def _seed_description(new_id, comp):
    """시드 렌더의 frontmatter description(호출 트리거 문장) 결정론 생성.

    description 은 자유 산문이 아니라 **host 가 이 워커를 언제 부를지** 판정하는 트리거 문장이다.
    원본 것을 물려주면 결제 워커가 자기를 "Implementer A"·"구현자A" 로 소개해, 호출 트리거가 새
    정체성이 아니라 원본을 가리킨다. id·컴포넌트만으로 완전히 재생성할 수 있는 자리라 추측이 없다.
    """
    return (f"SAGE implementer for the `{comp}` component — design, implementation, and "
            f"component-level unit tests within its ownership boundary. Invoke when the leader "
            f"distributes a `{comp}` task, or when the user says /{new_id}, {new_id} agent.")


def _with_seed_description(text, new_id, comp):
    """frontmatter 의 description 한 줄을 재생성값으로 교체(없으면 원문 그대로).

    첫 `---` 블록 안의 단일 라인만 다룬다 — CORE 렌더 규약이 그렇고, 블록 스칼라(`>`/`|`)까지
    다루려다 잘못 자르면 frontmatter 가 깨져 host 가 렌더를 통째로 못 읽는다.
    """
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end == -1:
        return text
    head, rest = text[4:end], text[end:]
    value = _seed_description(new_id, comp).replace("\\", "\\\\").replace('"', '\\"')
    new_head, count = re.subn(r'(?m)^description:[ \t]*\S.*$', f'description: "{value}"', head, count=1)
    return "---\n" + (new_head if count else head) + rest


def _promoted_render(src_text, overlay_text, src_id, new_id, comp, paths=()):
    """CORE 렌더(+프로젝트 오버레이) → 새 컴포넌트 정체성의 **프로젝트 소유 렌더 시드** → (text, error).

    `implementer-a` 의 렌더는 CORE 라 `sage install --force` 가 덮어쓴다. 그래서 프로젝트 규칙은
    오버레이로 쌓인다. 새 `implementer-<comp>` 는 반대로 프로젝트 소유 자산이라 오버레이 대상이
    아니고 렌더를 직접 편집한다 — 그러므로 승계는 **합성 결과(base + 오버레이)를 마커 없는 평문
    렌더로 펴서** 넘기는 것이다. 마커를 그대로 옮기면 install/validate 가 이걸 CORE 관리 구간으로
    오인한다.

    정체성 치환은 id 토큰만 결정론으로 한다. 산문에 남는 원본 언급(`implementer A` 같은 표현,
    다른 워커와의 협업 문장)은 호출자가 잔존 목록으로 보고한다 — 여기서 자연어를 추측해 고치면
    틀린 문장을 조용히 심게 되고, 그건 시드가 아니라 오염이다.
    """
    base, err = _oc.base_of(src_text)
    if err:
        return None, [], f"원본 렌더의 관리 구간이 손상됨({err})"
    text = re.sub(rf"(?<![\w-]){re.escape(src_id)}(?![\w-])", new_id, base.rstrip("\n"))
    # CORE 렌더는 소유 경계를 죽은 필드(`team.core.<id>.owns`)로 가리킨다. 승격 대상은 어떤
    # 컴포넌트인지 이미 확정돼 있으므로 살아있는 출처로 바꿔준다 — 시드가 죽은 지시를 물려주면
    # 새 워커가 읽을 수 없는 값을 소유 경계로 삼는다.
    text = re.sub(rf"`?profile\.team\.core\.{re.escape(new_id)}\.owns`?",
                  f"`profile.components[{comp}].paths`", text)
    text = re.sub(rf"`?team\.core\.{re.escape(new_id)}\.owns`?",
                  f"`components[{comp}].paths`", text)
    # description 은 원본 산문을 물려받으면 안 되는 자리다(호출 트리거) — 통째로 재생성한다.
    text = _with_seed_description(text, new_id, comp)
    # 제목도 같은 자기소개 자리다. 새 id 로 시작하는 첫 H1 만, id·컴포넌트로 재생성한다
    # (다른 H1 은 원본 문서 구조라 건드리지 않는다).
    text = re.sub(rf"(?m)^# {re.escape(new_id)} —.*$",
                  f"# {new_id} — SAGE implementer for the `{comp}` component", text, count=1)
    # 잔존 판정은 배너·오버레이 절을 붙이기 **전에** 한다 — 둘 다 원본 id 를 담고 있어
    # (provenance) 나중에 재면 자기 자신을 잔존으로 보고한다.
    residuals = _residual_identity(text, src_id)
    body = (overlay_text or "").strip()
    if body:
        text += f"\n\n## Inherited Project Rules (seeded from {src_id} overlay)\n{body}"
    text += "\n"
    owned = ", ".join(f"`{p}`" for p in paths) or f"(profile.components[{comp}].paths)"
    banner = (f"<!-- seeded by `sage generate --kind roster --from-existing {src_id}` "
              f"for profile.components[{comp}]. This render is project-owned: edit it directly "
              f"(no overlay), then run `sage generate --kind agent --id {new_id} --write`. -->\n"
              # 소유 경계를 시드 시점에 못박는다 — 원본 렌더의 문장은 "네게 배정된 컴포넌트"
              # 라는 일반형이라, 그대로 물려주면 새 워커가 자기 경계를 스스로 추측한다.
              f"\n> **Ownership (seeded from profile.components[{comp}].paths):** {owned}\n")
    # frontmatter 는 맨 앞이어야 하므로 배너는 그 뒤에 넣는다.
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            head, rest = text[:end + 5], text[end + 5:]
            return head + banner + rest, residuals, None
    return banner + text, residuals, None


def _residual_identity(text, src_id):
    """치환 후에도 남은 원본 정체성 언급(산문·다른 워커 참조) → 정렬된 토큰 목록."""
    found = set()
    for match in re.finditer(r"[Ii]mplementer[- ][A-Za-z][\w-]*", text):
        token = match.group(0)
        if token.lower().replace(" ", "-") != src_id.lower():
            continue
        found.add(token)
    # 다른 CORE 워커 참조(협업 문장)는 컴포넌트 로스터에선 대개 틀린 지시다.
    for other in ("implementer-a", "implementer-b"):
        if other != src_id and re.search(rf"(?<![\w-]){other}(?![\w-])", text):
            found.add(other)
    return sorted(found)


def _seed_from_existing(args, dest, src_id, comp_id, paths):
    """새 implementer 의 양 host 렌더를 원본에서 시드한다 → (written, notes, error).

    create-only: 이미 있는 렌더는 건드리지 않는다(손편집 보존).
    """
    new_id = f"implementer-{comp_id}"
    overlay_path = _overlay_source_path(dest, src_id)
    overlay_text = ""
    if os.path.isfile(overlay_path):
        overlay_text, err = _oc.read_text_lf(overlay_path)
        if err:
            return [], [], err            # 오버레이를 못 읽으면 규칙이 조용히 빠진 시드가 된다
    written, notes = [], []
    src_paths = _interpretive_render_paths(dest, "agent", src_id)
    new_paths = _interpretive_render_paths(dest, "agent", new_id)
    seeded_any = False
    for src, out in zip(src_paths, new_paths):
        if not os.path.isfile(src):
            continue                      # 그 host 는 설치돼 있지 않음
        if os.path.exists(out):
            notes.append(f"    skip(기존 렌더 보존): {os.path.relpath(out, dest)}")
            continue
        src_text, err = _oc.read_text_lf(src)
        if err:
            return [], notes, err
        # 원본 파일이 없으면 설치본에 합성돼 있는 본문으로 폴백한다(규칙 증발 방지).
        body = overlay_text or _overlay_body_from_render(src_text)
        text, residuals, err = _promoted_render(src_text, body, src_id, new_id, comp_id, paths)
        if err:
            return [], notes, f"{os.path.relpath(src, dest)}: {err}"
        if args.write:
            os.makedirs(os.path.dirname(out), exist_ok=True)
            _oc.write_text_lf(out, text)
        written.append(os.path.relpath(out, dest))
        seeded_any = True
        for token in residuals:
            notes.append(f"    ⚠️  {os.path.relpath(out, dest)}: 원본 정체성 잔존 — `{token}`")
    if not seeded_any and not notes:
        return [], notes, f"원본 렌더를 찾지 못함: {src_id} (.claude/.codex agents 어디에도 없음)"
    return written, notes, None


def _gen_roster(args, root):
    """EH-1: profile.components 기반 동적 implementer 에이전트 spec 생성 (install-time 고정 → generate-time 파생).

    - components 비면 → 고정 implementer-a/b 폴백 유지(하위호환, 생성 안 함).
    - 비어있지 않으면 컴포넌트당 `implementer-<id>.md` spec 을 중립 템플릿에서 결정론 scaffold.
      naming = implementer-<comp>(접두 — 함수역할 leader/qa/reviewer/convention-checker 와 충돌 회피).
    - create-only: 기존 spec(손편집 가능) 은 보존(skip). --write 없으면 dry-run 미리보기.
    - component ID/path/runtime model 계약이 잘못되면 어떤 roster 파일도 쓰기 전에 FAIL.
    - claims/render/manifest 등록은 interpretive agent 파이프라인(`sage generate --kind agent`)이 처리
      → "중대" cross-cutting(manifest/conformance/reverse_extract) 재작성 회피, 잘 격리된 추가 경로."""
    prof = _load_profile_dict(root, args.dest)
    print("== sage generate (roster) — 동적 implementer 파생 (EH-1) ==")
    if prof is None:
        print("  ❌ profile.yaml 파싱 실패 — components 읽기 불가 (YAML 수정 필요)", file=sys.stderr)
        return 1
    components = prof.get("components") or []
    if not components:
        print("  ℹ️  profile.components 비어있음 → 고정 implementer-a/b 폴백 유지(하위호환). 생성 없음.")
        return 0
    agents_dir = os.path.join(args.dest, "docs", "sage_harness", "agents")
    from sage.model_routing import component_issues, component_model
    from sage.runtime_hosts import active_host
    failures = [message for severity, message in component_issues(prof) if severity == "FAIL"]
    if failures:
        for message in failures:
            print(f"  ❌ {message}", file=sys.stderr)
        print("  profile.components 오류를 수정한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1
    runtime = active_host(prof)
    source = getattr(args, "from_existing", None)
    if source and not re.fullmatch(r"[A-Za-z0-9][\w-]{0,79}", source):
        print(f"  ❌ --from-existing id 형식 오류: {source!r}", file=sys.stderr)
        return 1
    written, skipped, bad, seeded, seed_notes = [], [], [], [], []
    for comp in components:
        cid = (comp or {}).get("id")
        if not cid:
            bad.append(repr(comp)); continue
        aid = f"implementer-{cid}"
        out = os.path.join(agents_dir, f"{aid}.md")
        if os.path.exists(out):
            skipped.append(aid)             # create-only — 기존(손편집 가능) spec 보존
        else:
            if args.write:
                os.makedirs(agents_dir, exist_ok=True)
                Path(out).write_text(
                    _implementer_spec_md(cid, comp.get("paths") or [], comp.get("model") or "opus",
                                         runtime, component_model(comp, runtime)),
                    encoding="utf-8")
            written.append(aid)
        # 시드는 spec 생성 여부와 **독립**이다. 이미 `--kind roster` 를 한 번 돌린 프로젝트는
        # spec 만 있고 렌더는 없는 상태인데, spec 이 있다고 건너뛰면 승격 경로가 영원히 닫힌다
        # (게다가 rc=0 · 시드 0건이라 사용자는 승계가 끝났다고 오인한다). 렌더 쪽 create-only 는
        # _seed_from_existing 이 따로 판정한다.
        if source:
            files, notes, err = _seed_from_existing(args, args.dest, source, cid,
                                                    comp.get("paths") or [])
            if err:
                print(f"  ❌ {aid} 시드 실패 — {err}", file=sys.stderr)
                return 1
            seeded.extend(files)
            seed_notes.extend(notes)
    mode = "생성" if args.write else "생성예정(dry-run — --write 로 기록)"
    print(f"  {mode}: {len(written)}건 — {', '.join(written) or '없음'}")
    if skipped:
        print(f"  skip(기존 보존): {len(skipped)}건 — {', '.join(skipped)}")
    if bad:
        print(f"  ⚠️  id 없는 component {len(bad)}건 무시: {', '.join(bad)}")
    if source:
        label = "시드" if args.write else "시드예정(dry-run)"
        print(f"  {label}(--from-existing {source}): {len(seeded)}건 — {', '.join(seeded) or '없음'}")
        for note in seed_notes:
            print(note)
        if not seeded:
            # 0 건을 조용히 성공으로 끝내면 승계가 끝났다고 오인한다. 이유를 못박아 출력한다.
            print("  ℹ️  승격된 렌더 없음 — 대상 렌더가 이미 존재합니다(create-only). "
                  "다시 시드하려면 해당 렌더를 지우고 재실행하세요.")
        print("  다음(2단계): 시드된 렌더는 **프로젝트 소유**입니다 — 오버레이가 아니라 렌더를 직접 편집하세요.")
        print("    1) 위 잔존 항목을 포함해 `/sage-asset` 으로 컴포넌트 정체성에 맞게 다듬고,")
        print("    2) `sage generate --kind agent --id implementer-<comp> --write` 로 spec+claims 추출 + manifest 등록.")
        return 0
    print("  다음(2단계): 이 명령은 spec 만 scaffold 합니다. 렌더는 런타임 AI 가 저작합니다 —")
    print("    1) `/sage-asset`(claude) 또는 `$sage-asset`(codex)로 각 implementer 의 양 host 렌더")
    print("       (.claude/agents/<id>.md + .codex/agents/<id>.md)를 저작하고,")
    print("    2) 저작 후 `sage generate --kind agent --id <id> --write` 로 spec+claims 추출 + manifest 등록.")
    print("    (1 없이 2 를 먼저 실행하면 '렌더 누락' 으로 실패합니다 — 이 명령은 렌더를 만들지 않습니다.)")
    print("    (기존 implementer 의 프로젝트 규칙을 물려받으려면 `--from-existing implementer-a`.)")
    return 0


def _gen_mcp(args, root):
    """MCP(4번째 kind): spec md(payload SSOT) → .mcp.json(claude) + config.toml managed-block(codex) + manifest 스탬프.

    대상 id: --id 단일 / profile.mcp.enabled 목록 / 둘 다 없으면 mcps/ 전체(default-on, hook 과 동형).
    시크릿 FAIL 은 산출 전 중단(fail-closed). claude=SAGE 전용 .mcp.json 전체 쓰기, codex=공유 config.toml managed-block 교체.
    """
    from sage import mcp_common as M
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    manifest = json.loads(Path(manifest_path).read_text())
    spec_root = args.dest if os.path.isdir(docs_dir(args.dest, "mcp")) else root  # 경로 규약 단일소스(N-R2/P2-6)
    all_spec_ids = M.list_mcp_specs(spec_root)

    if args.id:
        if args.id not in all_spec_ids:
            print(f"[sage generate] TOOL ERROR: docs/sage_harness/mcps/{args.id}.md 없음", file=sys.stderr)
            return 2
        target_ids = [args.id]
    else:
        prof = _load_profile_dict(root, args.dest)
        enabled = ((prof or {}).get("mcp") or {}).get("enabled")
        if enabled is not None:
            missing = [e for e in enabled if e not in all_spec_ids]
            if missing:
                print(f"[sage generate] FAIL: profile.mcp.enabled 가 없는 spec 참조: {', '.join(missing)}", file=sys.stderr)
                return 1
            target_ids = sorted(enabled)
        else:
            target_ids = all_spec_ids

    print(f"== sage generate (mcp) — {len(target_ids)} spec ==")
    if not target_ids:
        print("  ℹ️  mcp spec 0건 (docs/sage_harness/mcps/ 비어있음 또는 enabled 빈값) — 생성 없음.")
        return 0

    # 1. 파싱 + 시크릿 거부(fail-closed): FAIL 하나라도 있으면 산출 전 중단
    models, had_fail = [], False
    for sid in target_ids:
        spec_path = AssetPaths(spec_root, "mcp", sid).spec   # 경로 규약 단일소스(N-R2/P2-6)
        try:
            mdl = M.parse_mcp_spec(spec_path)
        except M.MCPSpecError as e:
            print(f"  ❌ {sid}: spec 오류 — {e}", file=sys.stderr); had_fail = True; continue
        for sev, msg in M.check_secrets(mdl):
            mark = "❌" if sev == "FAIL" else "⚠️ "
            print(f"  {mark} {sid}: {msg}", file=sys.stderr if sev == "FAIL" else sys.stdout)
            if sev == "FAIL":
                had_fail = True
        models.append(mdl)
    if had_fail:
        print("[sage generate] FAIL: spec 오류/시크릿 위반 → 산출 전 중단(fail-closed).", file=sys.stderr)
        return 1

    targets = ["claude", "codex"] if args.target == "both" else [args.target]
    # 2. 전 target 직렬화 + 사전검증을 '쓰기 전'에 모두 수행(원자성 — codex R3 P1: 부분상태 방지).
    #    하나라도 FAIL 이면 아무 파일도 안 쓴다.
    plan = []  # [(label, outp, body, dry_preview)]
    if "claude" in targets and any("claude" in m["runtime_targets"] for m in models):
        body = M.serialize_claude(models)
        plan.append(("claude", os.path.join(args.dest, ".mcp.json"), body, None))
    if "codex" in targets and any("codex" in m["runtime_targets"] for m in models):
        block = M.serialize_codex_block(models)
        outp = os.path.join(args.dest, ".codex", "config.toml")
        existing = Path(outp).read_text(encoding="utf-8") if os.path.exists(outp) else ""
        managed_names = {m["id"] for m in models if "codex" in m["runtime_targets"]}
        collide = sorted(managed_names & set(M.codex_servers_outside_block(existing)))
        if collide:
            print(f"[sage generate] FAIL (codex): managed-block 밖에 [mcp_servers.{', '.join(collide)}] 가 이미 선언됨 "
                  "→ SAGE 가 소유하려면 수동 정의를 제거하세요(소유권 충돌). 산출 없음.", file=sys.stderr)
            return 1
        new_text, err = M.replace_codex_block(existing, block)
        if err:
            print(f"[sage generate] FAIL (codex): {err} 산출 없음.", file=sys.stderr); return 1
        ok, note = M.verify_toml(new_text)
        if not ok:
            print(f"[sage generate] FAIL (codex): 생성 TOML 무효 — {note} 산출 없음.", file=sys.stderr); return 1
        if note:
            print(f"   ↳ (codex) {note}")
        plan.append(("codex", outp, new_text, block))

    # 3. 쓰기(전 target 검증 통과 후에만) 또는 dry-run.
    #    ★ codex R4 P1: temp 파일에 전부 쓴 뒤 os.replace 로 일괄 승격(all-or-nothing). 중간 OSError 시
    #    기존 파일 무손상(temp 만 정리) — 부분상태 방지.
    from sage import _resources
    # hook 등록과 같은 이유로 엔진 저장소에는 host 산출물을 쓰지 않는다(.mcp.json·config.toml).
    # manifest 스탬프(4단계)는 그대로 수행한다 — 그건 엔진 저장소가 소유하는 파일이다.
    write_host = args.write and not _resources.is_engine_source_tree(args.dest)
    if args.write and not write_host:
        print("  ℹ️  엔진 저장소 — host MCP 산출물 쓰기 생략(엔진 저장소는 설치 산출물을 보유하지 않습니다).")
    if write_host:
        staged = []  # [(tmp, final, label)]
        try:
            for label, outp, body, _dry in plan:
                d = os.path.dirname(outp)
                if d:
                    os.makedirs(d, exist_ok=True)
                tmp = outp + ".sage-tmp"
                Path(tmp).write_text(body, encoding="utf-8")
                staged.append((tmp, outp, label))
            for tmp, outp, label in staged:
                os.replace(tmp, outp)
                owner = "SAGE 소유(write-guard 대상)" if label == "claude" else "managed-block 교체(블록 밖 보존)"
                print(f"✅ ({label}) {os.path.relpath(outp, args.dest)} — {owner}")
        except OSError as e:
            for tmp, _o, _l in staged:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError:
                    pass
            print(f"[sage generate] FAIL: 산출물 쓰기 실패 — {e} (기존 파일 무손상).", file=sys.stderr)
            return 1
    else:
        label_kind = "engine-skip" if args.write else "dry-run"
        for label, _outp, body, dry in plan:
            print(f"== generate {label} ({label_kind}) ==\n{dry if dry is not None else body}")

    # 4. manifest 스탬프 (--write)
    if args.write:
        import hashlib
        def sha(s):
            return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()
        for mdl in models:
            key = f"mcps/{mdl['id']}"
            e = manifest["assets"].setdefault(key, {"conformance": "PASS", "form": "declarative"})
            e["form"] = "declarative"
            e["runtime_targets"] = list(mdl["runtime_targets"])
            e["adapter_contract_version"] = M.CONTRACT_VERSION   # N-R2/P1-3: MCP 직렬화 계약버전 스탬프(다른 kind 와 대칭)
            spec_path = AssetPaths(spec_root, "mcp", mdl["id"]).spec   # 경로 규약 단일소스(N-R2/P2-6)
            e["spec_hash"] = "sha256:" + hashlib.sha256(Path(spec_path).read_bytes()).hexdigest()
            rh = {}
            for tgt in mdl["runtime_targets"]:
                rh[tgt] = sha(M.canonical_render(mdl, tgt))
            e["render_hash"] = rh
            e["conformance"] = "PASS"
        try:
            atomic_write_json(manifest_path, manifest)
        except OSError as exc:
            print(f"[sage generate] FAIL: MCP manifest 스탬프 원자적 교체 실패 — {exc}", file=sys.stderr)
            return 1
        print("✅ manifest 스탬프 갱신 (mcps/)")
    return 0


def _interpretive_render_paths(dest, kind, aid):
    """agent/skill 의 claude·codex 렌더 경로(repo 정본). codex skill 정본도 repo .codex/skills/(전역은 배포 캐시)."""
    if kind == "agent":
        return (os.path.join(dest, ".claude", "agents", f"{aid}.md"),
                os.path.join(dest, ".codex", "agents", f"{aid}.md"))
    return (os.path.join(dest, ".claude", "skills", aid, "SKILL.md"),
            os.path.join(dest, ".codex", "skills", aid, "SKILL.md"))


def _scan_interpretive_ids(dest, kind):
    """렌더 디렉토리(claude+codex)에서 자산 id 수집 — --id 미지정 시 일괄 처리 대상."""
    ids = set()
    if kind == "agent":
        for rt in (".claude", ".codex"):
            d = os.path.join(dest, rt, "agents")
            if os.path.isdir(d):
                ids.update(f[:-3] for f in os.listdir(d) if f.endswith(".md"))
    else:  # skill: <rt>/skills/<id>/SKILL.md
        for rt in (".claude", ".codex"):
            d = os.path.join(dest, rt, "skills")
            if os.path.isdir(d):
                ids.update(sub for sub in os.listdir(d)
                           if os.path.exists(os.path.join(d, sub, "SKILL.md")))
    return ids


def _component_path_glob(p):
    """컴포넌트 경로 글롭 1개 → owned_paths 인식 regex (과매칭 방지). 안전치 않으면 None.

    안전 케이스만 파생: (1) 완전 리터럴(`src/x/util.py`) → 정확/하위 매칭, (2) 리터럴 디렉토리 prefix +
    순수 와일드카드 세그먼트(`src/backend/**`, `src/backend/*`) → 하위 매칭.
    제외(과매칭 위험): 선행 와일드카드(`**/x`), 세그먼트 내 와일드카드(`src/foo*.py`·`src/[ab]/**` → prefix
    가 디렉토리 경계 아님), 중간 와일드카드 뒤 리터럴(`src/*/service` → prefix `src` 과소). (codex 리뷰 P2)
    """
    if not isinstance(p, str) or not p:
        return None
    segs = p.split("/")
    wi = next((i for i, s in enumerate(segs) if re.search(r"[*?\[]", s)), len(segs))
    literal = segs[:wi]
    if not literal:
        return None                              # 선행 와일드카드 — 쓸 prefix 없음
    prefix = "/".join(literal)
    # 토큰 경계(codex 리뷰 P2): 좌=앞에 단어/대시 없음(`asrc`·`my-src` 차단하되 경로 앵커 `./src`·`/src`·
    #   `../src` 와 공백은 허용), 우=뒤에 단어문자 없음(`util.py2` 차단, 문장끝 `util.py.` 허용).
    #   단일문자 lookbehind 한계로 `lib/src`(중간경로) 류는 관대 매칭될 수 있으나 owned_paths 는 advisory
    #   휴리스틱 claim 이라 수용(렌더가 실제로 경로를 언급한다는 사실은 유지).
    lb, rb = r"(?<![\w\-])", r"(?![\w])"
    if wi == len(segs):
        return lb + re.escape(prefix) + r"(?:/[\w.\-]+)*" + rb   # 완전 리터럴 — 정확 + 하위
    if segs[wi] not in ("*", "**"):
        return None                              # 세그먼트 내 와일드카드 — prefix 가 디렉토리 경계 아님
    if any(not re.search(r"[*?\[]", s) for s in segs[wi + 1:]):
        return None                              # 중간 와일드카드 뒤 리터럴 — prefix 과소
    return lb + re.escape(prefix) + r"/[\w.\-]+(?:/[\w.\-]+)*" + rb   # 디렉토리 prefix + 하위 경로


def _extract_config_from_profile(prof, root, dest):
    """profile → ExtractConfig (프로젝트 시그널 주입 — 엔진 도메인-0, 프로젝트값은 profile 에서).

    reverse_extract 의 DEFAULT(config=None)는 owned_paths/input_scope 등 프로젝트 claim 을 미추출한다.
    (1) components[].paths → component_path_globs(owned_paths 인식, 과매칭 방지 — _component_path_glob).
    (2) profile.extraction.config(module:VAR | repo-상대 *.json) → input_scope_patterns/signal_rules 등
        풍부한 시그널을 명시 주입(파생값 위에 병합, 명시 우선). json 은 프로젝트 루트 기준 해석(cwd 비의존).
    반환: dict(시그널 있음) | None(시그널 0 — 엔진 DEFAULT graceful).
    """
    cfg = {}
    comp_globs = [g for comp in (prof.get("components") or [])
                  for g in (_component_path_glob(p) for p in (comp.get("paths") or [])) if g]
    if comp_globs:
        cfg["component_path_globs"] = comp_globs
    ref = ((prof.get("extraction") or {}).get("config") or "").strip()
    if ref:
        try:
            if ref.endswith(".json"):
                path = ref if os.path.isabs(ref) else os.path.join(dest, ref)
                if not os.path.exists(path):
                    path = os.path.join(root, ref)   # dest 에 없으면 SAGE 루트 기준(cwd 비의존)
                import json as _json
                with open(path, encoding="utf-8") as f:
                    loaded = _json.load(f)
            else:
                import importlib
                mod, _, var = ref.partition(":")
                m = importlib.import_module(mod)
                loaded = getattr(m, var) if var else getattr(m, "CONFIG")
            cfg.update(loaded or {})   # 명시 config 가 파생값을 덮어씀(프로젝트 의도 우선)
        except Exception as e:
            print(f"  ⚠️ extraction.config 로드 실패('{ref}'): {type(e).__name__}: {e} — 파생 config 만 사용", file=sys.stderr)
    return cfg or None


def _gen_interpretive(args, root, kind):
    """agent/skill(interpretive): 런타임 AI 가 저작한 렌더(claude+codex) → spec+claims 추출 + manifest 등록 (Gap-3).

    드라이버(extract_agent/extract_skill)의 extract() 를 래핑 — 사용자가 다인자 수동 실행하던 등록을 자동화
    (드라이버 help 가 명시: "manifest 등록은 sage generate 흐름에서"). reverse_extract 가 두 렌더의
    교집합으로 required claims 를 도출하므로 양 host 렌더가 모두 있어야 한다(fail-closed, 부분등록 금지).
    CORE 부트스트랩 렌더(roster/CORE skill)는 manifest 비추적 → --id 없이 스캔 시 제외(직접 지정만 허용).
    """
    import importlib
    from sage import _resources
    from sage.commands.install import _CORE_AGENTS, _CORE_SKILLS

    dest = os.path.abspath(args.dest)
    scripts_dir = os.path.dirname(_resources.hooks_src_dir())   # scripts/sage_harness (드라이버 위치)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    drv = importlib.import_module("extract_agent" if kind == "agent" else "extract_skill")
    import manifest_util as mu
    upsert = mu.upsert_agent if kind == "agent" else mu.upsert_skill
    core_names = set(_CORE_AGENTS if kind == "agent" else _CORE_SKILLS)
    if kind == "skill":
        from sage.commands.install import _CORE_BOOTSTRAP_SKILLS
        core_names.update(_CORE_BOOTSTRAP_SKILLS)

    if args.id:
        ids = [args.id]
    else:
        ids = sorted(_scan_interpretive_ids(dest, kind) - core_names)

    print(f"== sage generate ({kind}) — {len(ids)} 자산 (interpretive 추출+등록) ==")
    if not ids:
        print(f"  ℹ️  대상 {kind} 0건 (렌더 없음 또는 전부 CORE 부트스트랩). 단일은 --id 로 지정.")
        return 0

    # profile 1회 로드 — 추출 config 파생(P1) + deploy host/prefix 양쪽에서 재사용.
    prof = _load_profile_dict(root, args.dest) or {}
    config = _extract_config_from_profile(prof, root, dest)
    if config is None:
        print("  ℹ️  추출 config 시그널 0(profile.components/extraction.config 미설정) — owned_paths 등 "
              "프로젝트 claim 이 추출되지 않을 수 있음(엔진 DEFAULT). components 를 채우면 owned_paths 가 게이트됨.")

    # Part C: codex 전역 배포는 skill 전용(codex 가 자동발견하는 건 전역 skill 뿐 — agent 는 .codex/agents repo 정본).
    deploy_codex = getattr(args, "deploy_codex", False)
    if deploy_codex and kind != "skill":
        print("  ⚠️  --deploy-codex 는 --kind skill 전용입니다(agent 는 repo .codex/agents 정본, 전역 배포 없음). 무시.", file=sys.stderr)
        deploy_codex = False
    prefix = ""
    if deploy_codex:
        from sage.runtime_hosts import active_host
        host = active_host(prof, default="")
        if host != "codex":
            # codex 전역 skill 발견은 codex-host 에서만 의미(claude-host 는 codex skill 미사용) — doctor 점검과 일관.
            # claude-host 가 전역에 orphan 배포를 만들지 않도록 배포 생략(등록은 진행, codex 리뷰 P2).
            print("  ⚠️  --deploy-codex 는 codex-host 프로젝트에서만 유효(claude-host 는 codex skill 미사용) → 배포 생략, 등록만 진행.",
                  file=sys.stderr)
            deploy_codex = False
        else:
            prefix = str((prof.get("project") or {}).get("prefix") or "").strip()
            if not prefix:
                # 전역 $CODEX_HOME/skills 는 공유 네임스페이스 — prefix 없이 bare id 로 배포하면
                # 타 프로젝트와 충돌(clobber). prefix 필수(fail-closed, 충돌 방지 — codex 리뷰 P1).
                print("  ❌ --deploy-codex 에는 project.prefix 가 필요합니다 "
                      "(전역 $CODEX_HOME/skills 공유 네임스페이스 충돌 방지). profile 의 project.prefix 를 설정 후 재실행.",
                      file=sys.stderr)
                return 1
            if not re.match(r"^[A-Za-z0-9_-]+$", prefix):
                # 경로 탈출 방어(codex 리뷰 P2): prefix 가 전역 경로 조립에 들어가므로 / · .. 등 차단.
                print(f"  ❌ project.prefix 가 안전하지 않습니다('{prefix}') — [A-Za-z0-9_-] 만 허용(전역 경로 탈출 방지).",
                      file=sys.stderr)
                return 1

    guide = os.path.join(dest, "AGENT_GUIDE.md")
    out_dir = docs_dir(root, kind)
    # manifest.test 는 비운다. 예전에는 엔진의 reverse_extract 회귀 테스트를 가리켰는데, 그 테스트는
    # 합성 입력으로 추출기를 검증하는 엔진 소유물이라 install 이 배포하지 않고(프로젝트엔
    # scripts/sage_harness/hooks/ 만 온다) 프로젝트 자산의 회귀도 아니다. 결과는 validate 가
    # 없는 경로로 FAIL 하는 것뿐이었다. 자산별 회귀가 실제로 있으면 프로젝트가 직접 채운다.
    test_path = None
    written, failed, deployed = [], [], []
    for aid in ids:
        if aid in core_names:
            print(f"  ⏭️  {aid}: CORE 부트스트랩 자산 — manifest 비추적(스킵). 직접편집 자산이라 generate 대상 아님.")
            continue
        if not re.match(r"^[A-Za-z0-9_-]+$", aid):
            # id 는 렌더/spec/claims/전역경로 조립에 모두 들어가므로 가장 먼저 검증(경로 탈출 방지 — codex 리뷰 P2).
            print(f"  ❌ {aid}: 안전하지 않은 자산 id — [A-Za-z0-9_-] 만 허용(경로 탈출 방지)", file=sys.stderr)
            failed.append(aid); continue
        claude_r, codex_r = _interpretive_render_paths(dest, kind, aid)
        missing = [os.path.relpath(p, dest) for p in (claude_r, codex_r) if not os.path.exists(p)]
        if missing:
            print(f"  ❌ {aid}: 렌더 누락 — {', '.join(missing)} "
                  f"(양 host 렌더 필요 — reverse_extract 가 교집합으로 claims 도출)", file=sys.stderr)
            print(f"     이 명령은 렌더를 만들지 않습니다(추출+등록 전용). 먼저 `/sage-asset`(claude) 또는 "
                  f"`$sage-asset`(codex)로 {aid} 의 렌더를 저작한 뒤 재실행하세요.", file=sys.stderr)
            failed.append(aid); continue
        try:
            spec_md, claims_yaml, claims = drv.extract(aid, claude_r, codex_r, guide, config)
        except Exception as e:
            print(f"  ❌ {aid}: 추출 실패 — {type(e).__name__}: {e}", file=sys.stderr)
            failed.append(aid); continue
        if args.write:
            os.makedirs(out_dir, exist_ok=True)
            Path(os.path.join(out_dir, f"{aid}.md")).write_text(spec_md, encoding="utf-8")
            Path(os.path.join(out_dir, f"{aid}.claims.yml")).write_text(claims_yaml, encoding="utf-8")
            upsert(root, aid, claude_render=claude_r, codex_render=codex_r,
                   test=test_path, unresolved=claims["unresolved"])
            print(f"  ✅ {aid}: spec+claims 기록 + manifest 등록 "
                  f"(required={len(claims['required_claims'])}, unresolved={len(claims['unresolved'])})")
            # Part C: codex 전역 배포(opt-in) — repo 정본(codex_r)을 $CODEX_HOME/skills/<prefix>-<id> 로 복사.
            #   manifest 는 repo 정본만 추적(clone-stable); 전역은 codex 자동발견용 배포 캐시(force 갱신).
            if deploy_codex:
                from sage.commands.install import _install_codex_global_skill
                gid = f"{prefix}-{aid}"   # prefix·aid 안전(위에서 검증) — 전역 공유 네임스페이스 충돌/경로탈출 방지
                status, gdst = _install_codex_global_skill(codex_r, force=True, skill_id=gid)
                if status == "installed":
                    print(f"     ↳ codex 전역 배포: {gdst}")
                    deployed.append(aid)
                elif status == "missing":
                    print(f"     ⚠️ codex 전역 배포 실패 — 정본 {os.path.relpath(codex_r, dest)} 없음", file=sys.stderr)
                else:
                    print(f"     ⚠️ codex 전역 배포 {status}: {gdst}", file=sys.stderr)
        else:
            print(f"  (dry-run) {aid}: 추출 OK — --write 로 기록+등록 "
                  f"(required={len(claims['required_claims'])}, unresolved={len(claims['unresolved'])})"
                  + ("  [+codex 전역 배포 예정]" if deploy_codex else ""))
        written.append(aid)

    if deployed:
        print(f"  codex 전역 배포 {len(deployed)}건 — codex 에서 호출명 ${prefix}-<id> "
              f"(repo .codex/skills 정본은 manifest 추적, 전역은 발견용 캐시).")
    if failed:
        print(f"  실패 {len(failed)}건: {', '.join(failed)} — `/sage-asset`(claude)/`$sage-asset`(codex)로 "
              f"렌더 저작 후 재실행", file=sys.stderr)
        return 1
    return 0


def run(args) -> int:
    root = _find_root(args.root or args.dest)   # --dest 프로젝트의 manifest 를 우선(Codex P1: dest 무시 버그)
    if not root:
        print("[sage generate] TOOL ERROR: manifest 미발견", file=sys.stderr)
        return 2
    # 강제 게이트(C): 미부트스트랩/미설치/손상 profile 이면 전 kind 차단(거버넌스 무력화 방지).
    from sage.commands._common import bootstrap_block_text, bootstrap_gate_reason
    reason = bootstrap_gate_reason(root, args.dest)
    if reason:
        print(bootstrap_block_text(reason), file=sys.stderr)
        return 2
    if args.kind == "hook":
        return _gen_hook(args, root)
    if args.kind == "roster":
        rc = _gen_roster(args, root)   # EH-1: profile.components → 동적 implementer spec
    elif args.kind == "mcp":
        rc = _gen_mcp(args, root)   # MCP 4번째 kind: spec md → .mcp.json + config.toml managed-block
    # agent/skill: render 는 interpretive(런타임 AI 저작) → generate 가 spec+claims 추출 + manifest 등록 (Gap-3).
    elif args.kind in ("agent", "skill"):
        rc = _gen_interpretive(args, root, args.kind)
    else:
        rc = 0
    if rc == 0 and args.write:
        try:
            _stamp_generator_version(root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"[sage generate] FAIL: generator_version 스탬프 실패 — {exc}", file=sys.stderr)
            return 1
    return rc
