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
import sys
from pathlib import Path


def register(sub):
    p = sub.add_parser("generate", help="spec → 등록 산출물(settings.json/hooks.json) + manifest 스탬프")
    p.add_argument("--kind", choices=["hook", "agent", "skill"], required=True)
    p.add_argument("--id", default=None, help="단일 자산 (없으면 kind 전체)")
    p.add_argument("--write", action="store_true", help="파일 기록 (없으면 dry-run 미리보기)")
    p.add_argument("--target", choices=["claude", "codex", "both"], default="claude",
                   help="등록 대상 런타임 (both 는 cross_model on)")
    p.add_argument("--dest", default=".", help="등록 산출물 기록 루트 (기본 cwd)")
    p.add_argument("--root", default=None, help="SAGE 루트 (manifest 탐색)")
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
    """런타임별 등록 command 문자열 (관측된 런타임 command 형식)."""
    if target == "claude":
        return f'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/{hook_id}.sh"'
    # codex: PROJECT_ROOT/CODEX_HOME wrapper
    return ("bash -c 'PROJECT_ROOT=\"${CODEX_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}\"; "
            f"CODEX_HOME=\"${{CODEX_HOME:-$PROJECT_ROOT/.codex}}\"; bash \"$CODEX_HOME/hooks/{hook_id}.sh\"'")


def _build_registration(root, target, hook_ids):
    """hook id 정렬 → target 별 {Event: [{matcher, hooks:[...]}]} 등록 dict (결정론).

    같은 event+matcher 는 한 블록에 hooks append. adapter 파일 존재 확인(없으면 (None, missing))."""
    missing = []
    # event → matcher → [command블록]  (matcher 안정 정렬)
    by_event = {}
    for hid in sorted(hook_ids):   # lexicographic 정렬(결정론)
        spec = os.path.join(root, "docs", "sage_harness", "hooks", f"{hid}.md")
        if not os.path.exists(spec):
            missing.append(f"spec:{hid}"); continue
        rb = _parse_runtime_bindings(spec)
        if target not in rb:
            continue
        # adapter/native 파일 존재 확인
        snake = hid.replace("-", "_")
        adapter = os.path.join(root, "scripts", "sage_harness", "hooks", "adapters", target, f"{hid}.sh")
        native = os.path.join(root, "scripts", "sage_harness", "hooks", f"{hid}.sh")
        if not (os.path.exists(adapter) or os.path.exists(native)):
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
        f'ROOT="${{{root_env}:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}}"\n'
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
    """sage/project-profile.yaml → project-profile.json (hook 런타임은 의존성 0 = JSON 만 읽음).

    반환: "none"(profile 파일 없음) | "ok"(컴파일 성공) | "fail"(profile 존재하나 컴파일 실패).
    fail-closed(Codex 2R): profile 이 있는데 컴파일 실패하면 hook 이 조용히 pass-open 되어
    risk gate 가 무력화된다 → generate 가 실패로 보고한다. pyyaml 은 generate(빌드) 의존성(pyproject 선언).
    """
    yml = os.path.join(dest, "sage", "project-profile.yaml")
    if not os.path.exists(yml):
        yml = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(yml):
        return "none"
    try:
        import yaml
        data = yaml.safe_load(Path(yml).read_text(encoding="utf-8")) or {}
    except ImportError:
        print("   ❌ profile 컴파일 실패: pyyaml 미설치 (generate 빌드 의존성 — pip install pyyaml).", file=sys.stderr)
        return "fail"
    except Exception as e:
        print(f"   ❌ profile 컴파일 실패: YAML 파싱 오류 ({type(e).__name__}: {e}).", file=sys.stderr)
        return "fail"
    outp = os.path.join(dest, "sage", "project-profile.json")
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    Path(outp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ↳ profile 컴파일: {os.path.relpath(outp, dest)} (hook 런타임 입력)")
    return "ok"


def _gen_hook(args, root):
    manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
    hook_ids = [k.split("/", 1)[1] for k in manifest["assets"] if k.startswith("hooks/")]
    if args.id:
        if args.id not in hook_ids:
            print(f"[sage generate] TOOL ERROR: manifest 에 hooks/{args.id} 없음", file=sys.stderr); return 2
        hook_ids = [args.id]

    # profile 컴파일 먼저(fail-closed): 실패면 산출물 쓰기 전에 중단 — hook risk gate 무력화 방지(Codex 2R)
    if args.write:
        status = _compile_profile(root, args.dest)
        if status == "fail":
            print("[sage generate] FAIL: profile 컴파일 실패 → hook risk gate 무력화 위험. "
                  "pyyaml 설치 또는 YAML 수정 후 재실행(profile 없는 프로젝트면 sage/project-profile.yaml 제거).",
                  file=sys.stderr)
            return 1

    targets = ["claude", "codex"] if args.target == "both" else [args.target]
    rc = 0
    for tgt in targets:
        reg, missing = _build_registration(root, tgt, hook_ids)
        if missing:
            print(f"[sage generate] FAIL ({tgt}): 누락 — {', '.join(missing)} (adapter 는 reverse_extract 정본)", file=sys.stderr)
            rc = 1
            continue
        if tgt == "claude":
            doc = {"hooks": reg}
            outp = os.path.join(args.dest, ".claude", "settings.json")
        else:
            doc = {"hooks": reg}
            outp = os.path.join(args.dest, ".codex", "hooks.json")
        body = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        if args.write:
            os.makedirs(os.path.dirname(outp), exist_ok=True)
            # 기존 settings.json 에 hooks 키만 갱신(다른 설정 보존)
            if tgt == "claude" and os.path.exists(outp):
                try:
                    existing = json.loads(Path(outp).read_text())
                    existing["hooks"] = reg
                    body = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
                except Exception:
                    pass
            Path(outp).write_text(body, encoding="utf-8")
            print(f"✅ ({tgt}) 등록 생성: {os.path.relpath(outp, args.dest)} — {sum(len(v) for v in reg.values())} event 블록")
            # 등록만으로는 실행 불가 → hook 실행 shim 을 {host}/hooks/ 에 배치(P0-2)
            _write_hook_shims(args, root, manifest, hook_ids, tgt)
        else:
            print(f"== generate {tgt} (dry-run) ==\n{body}")

    # manifest 스탬프 (--write) — profile 컴파일은 위에서 fail-closed 처리됨
    if args.write and rc == 0:
        _stamp_manifest(root, hook_ids)
    return rc


def _stamp_manifest(root, hook_ids):
    import hashlib
    def sha(p):
        return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()
    H = os.path.join(root, "scripts", "sage_harness", "hooks")
    m = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
    for hid in hook_ids:
        e = m["assets"].get(f"hooks/{hid}")
        if not e:
            continue
        spec = os.path.join(root, "docs", "sage_harness", "hooks", f"{hid}.md")
        if os.path.exists(spec):
            e["spec_hash"] = sha(spec)
        snake = hid.replace("-", "_")
        if e.get("form") == "native":
            nat = os.path.join(H, f"{hid}.sh")
            if os.path.exists(nat):
                e["canonical_hash"] = sha(nat); e["render_hash"] = {"native": sha(nat)}
        else:
            core = os.path.join(H, f"{snake}_core.py")
            if os.path.exists(core):
                e["canonical_hash"] = sha(core)
            ah = {}
            for rt in ("claude", "codex"):
                ap = os.path.join(H, "adapters", rt, f"{hid}.sh")
                if os.path.exists(ap):
                    ah[rt] = sha(ap)
            if ah:
                e["adapter_hash"] = ah; e["render_hash"] = ah
    Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).write_text(
        json.dumps(m, ensure_ascii=False, indent=2))
    print("✅ manifest 스탬프 갱신")


def run(args) -> int:
    root = _find_root(args.root or args.dest)   # --dest 프로젝트의 manifest 를 우선(Codex P1: dest 무시 버그)
    if not root:
        print("[sage generate] TOOL ERROR: manifest 미발견", file=sys.stderr)
        return 2
    if args.kind == "hook":
        return _gen_hook(args, root)
    # agent/skill: render 는 interpretive(런타임 AI). generate 는 안내만.
    drv = "extract_agent.py" if args.kind == "agent" else "extract_skill.py"
    print(f"== sage generate ({args.kind}) ==")
    print(f"{args.kind} render 는 interpretive(런타임 AI 영역) — generate 가 결정론 생성하지 않음.")
    print(f"→ 스펙/claims 산출은 scripts/sage_harness/{drv} 드라이버 사용(--write --register).")
    print(f"→ 런타임 산출물(.claude/.codex agents/skills 의 .md)은 런타임 AI 가 spec+claims 로 렌더.")
    return 0
