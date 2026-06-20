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

from sage.asset_paths import AssetPaths
from sage.commands._common import contract_version_of


def register(sub):
    p = sub.add_parser("generate", help="spec 파일을 읽어 Claude/Codex용 설정 파일을 생성합니다")
    p.add_argument("--kind", choices=["hook", "agent", "skill", "roster", "mcp"], required=True)
    p.add_argument("--id", default=None, help="단일 자산 (없으면 kind 전체; roster 는 profile.components 에서 파생)")
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
        _stamp_manifest(root, stamp_ids)
    return rc


def _stamp_manifest(root, hook_ids):
    import hashlib
    def sha(p):
        return "sha256:" + hashlib.sha256(Path(p).read_bytes()).hexdigest()
    m = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
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
        json.dumps(m, ensure_ascii=False, indent=2))
    print("✅ manifest 스탬프 갱신")


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
- model: {model}
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
    - claims/render/manifest 등록은 기존 interpretive agent 파이프라인(extract_agent --register)이 처리
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
    print("  다음: 런타임 AI 가 spec 렌더 → extract_agent --register 로 claims/manifest 등록(기존 agent 파이프라인).")
    return 0


def _gen_mcp(args, root):
    """MCP(4번째 kind): spec md(payload SSOT) → .mcp.json(claude) + config.toml managed-block(codex) + manifest 스탬프.

    대상 id: --id 단일 / profile.mcp.enabled 목록 / 둘 다 없으면 mcps/ 전체(default-on, hook 과 동형).
    시크릿 FAIL 은 산출 전 중단(fail-closed). claude=SAGE 전용 .mcp.json 전체 쓰기, codex=공유 config.toml managed-block 교체.
    """
    from sage import mcp_common as M
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    manifest = json.loads(Path(manifest_path).read_text())
    all_spec_ids = M.list_mcp_specs(args.dest if os.path.isdir(os.path.join(args.dest, "docs", "sage_harness", "mcps")) else root)
    spec_root = args.dest if os.path.isdir(os.path.join(args.dest, "docs", "sage_harness", "mcps")) else root

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
        spec_path = os.path.join(spec_root, "docs", "sage_harness", "mcps", f"{sid}.md")
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
            spec_path = os.path.join(spec_root, "docs", "sage_harness", "mcps", f"{mdl['id']}.md")
            e["spec_hash"] = "sha256:" + hashlib.sha256(Path(spec_path).read_bytes()).hexdigest()
            rh = {}
            for tgt in mdl["runtime_targets"]:
                rh[tgt] = sha(M.canonical_render(mdl, tgt))
            e["render_hash"] = rh
            e["conformance"] = "PASS"
        Path(manifest_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        print("✅ manifest 스탬프 갱신 (mcps/)")
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
    # agent/skill: render 는 interpretive(런타임 AI). generate 는 안내만.
    drv = "extract_agent.py" if args.kind == "agent" else "extract_skill.py"
    print(f"== sage generate ({args.kind}) ==")
    print(f"{args.kind} render 는 interpretive(런타임 AI 영역) — generate 가 결정론 생성하지 않음.")
    print(f"→ 스펙/claims 산출은 scripts/sage_harness/{drv} 드라이버 사용(--write --register).")
    print(f"→ 런타임 산출물(.claude/.codex agents/skills 의 .md)은 런타임 AI 가 spec+claims 로 렌더.")
    return 0
