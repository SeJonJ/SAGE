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

from sage.asset_paths import AssetPaths, docs_dir
from sage.commands._common import contract_version_of
from sage.hook_runtime_hash import calculate_hook_runtime_hash


def register(sub):
    p = sub.add_parser("generate", help="spec 파일을 읽어 Claude/Codex용 설정 파일을 생성합니다")
    p.add_argument("--kind", choices=["hook", "agent", "skill", "roster", "mcp"], required=True)
    p.add_argument("--id", default=None, help="단일 자산 (없으면 kind 전체; roster 는 profile.components 에서 파생)")
    p.add_argument("--write", action="store_true", help="파일 기록 (없으면 dry-run 미리보기)")
    p.add_argument("--target", choices=["claude", "codex", "both"], default="claude",
                   help="등록 대상 런타임 (both 는 cross_model on)")
    p.add_argument("--dest", default=".", help="등록 산출물 기록 루트 (기본 cwd)")
    p.add_argument("--root", default=None, help="SAGE 루트 (manifest 탐색)")
    p.add_argument("--deploy-codex", action="store_true",
                   help="(--kind skill) repo .codex/skills 정본을 codex 전역 $CODEX_HOME/skills 에 배포(prefix 네임스페이스). "
                        "codex 는 repo-스코프 skill 미자동발견 → 전역 배포해야 호출 가능. 명시적 opt-in(환경 부작용 분리).")
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
        ap = AssetPaths(root, "hook", hid)
        if not os.path.exists(ap.spec):
            missing.append(f"spec:{hid}"); continue
        rb = _parse_runtime_bindings(ap.spec)
        if target not in rb:
            continue
        # adapter/native 파일 존재 확인 (경로 규약 AssetPaths 단일소스 — P2-6)
        if not (os.path.exists(ap.adapter(target)) or os.path.exists(ap.native)):
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
    all_hook_ids = [k.split("/", 1)[1] for k in manifest["assets"] if k.startswith("hooks/")]
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
    if args.write:
        status = _compile_profile(root, args.dest)
        if status == "fail":
            print("[sage generate] FAIL: profile 컴파일 실패 → hook risk gate 무력화 위험. "
                  "pyyaml 설치 또는 YAML 수정 후 재실행(profile 없는 프로젝트면 sage/project-profile.yaml 제거).",
                  file=sys.stderr)
            return 1
        # R2/P0-2: 컴파일된 profile 구조+의미 검증. FAIL(오타 키·전략 모듈 부재·미정의 phase 참조)이면
        # 산출물 쓰기 전 중단 — "유효 YAML 이지만 게이트가 침묵 비활성되는" profile 의 배포 차단.
        if status == "ok":
            from sage.profile_validate import severity_of, validate_profile
            compiled = os.path.join(args.dest, "sage", "project-profile.json")
            try:
                prof = json.loads(Path(compiled).read_text(encoding="utf-8"))
            except Exception:
                prof = None
            if prof is not None:
                issues = validate_profile(prof, root)
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

    targets = ["claude", "codex"] if args.target == "both" else [args.target]
    rc = 0
    for tgt in targets:
        reg, missing = _build_registration(root, tgt, reg_ids)
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
            _write_hook_shims(args, root, manifest, reg_ids, tgt)
        else:
            print(f"== generate {tgt} (dry-run) ==\n{body}")

    # manifest 스탬프 (--write) — profile 컴파일은 위에서 fail-closed 처리됨. --id 면 그 hook 만 재스탬프.
    if args.write and rc == 0:
        if not _stamp_manifest(root, stamp_ids, runtime_hash=runtime_hash):
            return 1
    return rc


def _stamp_manifest(root, hook_ids, runtime_hash=None):
    import hashlib
    def sha(p):
        return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()
    m = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
    if runtime_hash is None:
        runtime_hash, missing_runtime = calculate_hook_runtime_hash(root)
        if missing_runtime:
            print("[sage generate] FAIL: hook_runtime_hash 스탬프 불가 — runtime 파일 누락: " +
                  ", ".join(os.path.relpath(p, root) for p in missing_runtime), file=sys.stderr)
            return False
    m["hook_runtime_hash"] = runtime_hash
    for hid in hook_ids:
        e = m["assets"].get(f"hooks/{hid}")
        if not e:
            continue
        paths = AssetPaths(root, "hook", hid)   # 경로 규약 단일소스(P2-6)
        if os.path.exists(paths.spec):
            e["spec_hash"] = sha(paths.spec)
        if e.get("form") == "native":
            if os.path.exists(paths.native):
                e["canonical_hash"] = sha(paths.native); e["render_hash"] = {"native": sha(paths.native)}
        else:
            if os.path.exists(paths.core):
                e["canonical_hash"] = sha(paths.core)
                cv = contract_version_of(paths.core)   # R3: core.CONTRACT_VERSION 스탬프(인터페이스 계약 드리프트 가드)
                if cv:
                    e["adapter_contract_version"] = cv
            ah = {}
            for rt in ("claude", "codex"):
                adp = paths.adapter(rt)
                if os.path.exists(adp):
                    ah[rt] = sha(adp)
            if ah:
                e["adapter_hash"] = ah; e["render_hash"] = ah
    Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n")
    print("✅ manifest 스탬프 갱신")
    return True


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


def _implementer_spec_md(comp_id, paths, model):
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
- claims/allowlist are auto-derived into {{id}}.claims.yml by reverse_extract

## drift_checks
- conformance: required/forbidden claim presence (machine-check, no LLM judge)
"""


def _gen_roster(args, root):
    """EH-1: profile.components 기반 동적 implementer 에이전트 spec 생성 (install-time 고정 → generate-time 파생).

    - components 비면 → 고정 implementer-a/b 폴백 유지(하위호환, 생성 안 함).
    - 비어있지 않으면 컴포넌트당 `implementer-<id>.md` spec 을 중립 템플릿에서 결정론 scaffold.
      naming = implementer-<comp>(접두 — 함수역할 leader/qa/reviewer/convention-checker 와 충돌 회피).
    - create-only: 기존 spec(손편집 가능) 은 보존(skip). --write 없으면 dry-run 미리보기.
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
    written, skipped, bad = [], [], []
    for comp in components:
        cid = (comp or {}).get("id")
        if not cid:
            bad.append(repr(comp)); continue
        aid = f"implementer-{cid}"
        out = os.path.join(agents_dir, f"{aid}.md")
        if os.path.exists(out):
            skipped.append(aid); continue   # create-only — 기존(손편집 가능) spec 보존
        if args.write:
            os.makedirs(agents_dir, exist_ok=True)
            Path(out).write_text(
                _implementer_spec_md(cid, comp.get("paths") or [], comp.get("model") or "opus"),
                encoding="utf-8")
        written.append(aid)
    mode = "생성" if args.write else "생성예정(dry-run — --write 로 기록)"
    print(f"  {mode}: {len(written)}건 — {', '.join(written) or '없음'}")
    if skipped:
        print(f"  skip(기존 보존): {len(skipped)}건 — {', '.join(skipped)}")
    if bad:
        print(f"  ⚠️  id 없는 component {len(bad)}건 무시: {', '.join(bad)}")
    print("  다음(2단계): 이 명령은 spec 만 scaffold 합니다. 렌더는 런타임 AI 가 저작합니다 —")
    print("    1) `/sage-asset`(claude) 또는 `$sage-asset`(codex)로 각 implementer 의 양 host 렌더")
    print("       (.claude/agents/<id>.md + .codex/agents/<id>.md)를 저작하고,")
    print("    2) 저작 후 `sage generate --kind agent --id <id> --write` 로 spec+claims 추출 + manifest 등록.")
    print("    (1 없이 2 를 먼저 실행하면 '렌더 누락' 으로 실패합니다 — 이 명령은 렌더를 만들지 않습니다.)")
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
    if args.write:
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
        for label, _outp, body, dry in plan:
            print(f"== generate {label} (dry-run) ==\n{dry if dry is not None else body}")

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
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
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
        host = str((prof.get("runtime") or {}).get("host") or "").strip()
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
    test_path = f"scripts/sage_harness/hooks/tests/test_reverse_extract_{kind}.py"
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
        return _gen_roster(args, root)   # EH-1: profile.components → 동적 implementer spec
    if args.kind == "mcp":
        return _gen_mcp(args, root)   # MCP 4번째 kind: spec md → .mcp.json + config.toml managed-block
    # agent/skill: render 는 interpretive(런타임 AI 저작) → generate 가 spec+claims 추출 + manifest 등록 (Gap-3).
    if args.kind in ("agent", "skill"):
        return _gen_interpretive(args, root, args.kind)
    return 0
