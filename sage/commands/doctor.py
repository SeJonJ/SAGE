"""sage doctor — 옵션 의존성 점검 + reviewer_resolution 노출 (step10).

Cross-invocation은 반대 runtime CLI를 직접 호출하며, peer 미가용 시 Phase 05를 fail-closed로 차단한다.
reviewer_resolution 은 순수 판정 함수, doctor 가 옵션 의존성(gstack/codegraph/vault) + reviewer mode 를 정보성 출력.
gstack 가용성 = profile requires/capabilities + PATH which (개인경로 의존 금지).
exit: 정상/degraded/의존성미설치 = 0, profile YAML 파싱 오류(설정 무시됨) = 1 (Codex P1: 실패 원인 구분).
"""

import os
import platform
import shutil
import sys
from pathlib import Path

from sage.runtime_hosts import (active_host, configured_hosts, profile_issues,
                                receipt_hosts, receipt_issues)
from sage.hook_launcher import resolve_sage_hook
from sage.profile_layers import load_profile_layers, local_profile_git_issues
from sage.i18n import language_of, render_issue, tr


def register(sub, context):
    p = sub.add_parser("doctor", help=tr(context, "cli.doctor.doctor"))
    p.add_argument("--profile", default=None, help=tr(context, "cli.doctor.profile"))
    p.set_defaults(func=run)


def reviewer_resolution(profile: dict, caps: dict, current: str | None = None) -> dict:
    """Phase 05 reviewer 해석 (순수). caps={'codex':bool,'claude':bool} 는 doctor 가 주입(peer CLI 가용성).

    7차 배치2: gstack 의존 폐기. cross-model 리뷰는 SAGE 가 반대 런타임 CLI 를 직접 호출하므로
    (claude-host→`codex exec`, codex-host→`claude -p`), **peer 런타임 CLI 가용성만으로** 판정한다.
    이전의 `which gstack` 판정(1-a 오탐: gstack 은 PATH 바이너리가 아니라 ~/.claude/skills 폴더라 항상
    false)과 codex-host 의 invocation 문자열 요구를 모두 제거 — host 대칭.

    결정표:
    - cross_model off                       → clean_context_same_runtime (의도적, degraded=false)
    - cross on, claude-host, codex CLI 가용  → opposite_runtime(codex) via `codex exec`
    - cross on, claude-host, codex CLI 불가  → blocked (codex_cli_unavailable)
    - cross on, codex-host, claude CLI 가용  → opposite_runtime(claude) via `claude -p`
    - cross on, codex-host, claude CLI 불가  → blocked (claude_cli_unavailable)
    """
    # current 를 주면 그 host 는 리뷰어에서 제외된다(실행 중인 프로세스가 자기 코드를 리뷰하지 않도록).
    # 미지정이면 reviewer_selection 이 실행 환경에서 판별하고, 판별 실패 시 프로필로 내려간다.
    host = current or active_host(profile)
    cross = bool((profile.get("options", {}) or {}).get("cross_model", False))

    def res(mode, rt, fb, deg, reason, notice):
        return {"reviewer_mode": mode, "reviewer_runtime": rt, "fallback_used": fb,
                "reviewer_degraded": deg, "reviewer_degrade_reason": reason, "notice": notice}

    if not cross:
        return res("clean_context_same_runtime", host, False, False, None,
                   "cross_model off — 의도적 same-runtime (degraded 아님)")
    from sage.model_routing import reviewer_selection
    peer, _ = reviewer_selection(profile, current)
    if caps.get(peer):
        invoker = "codex exec" if peer == "codex" else "claude -p"
        return res("opposite_runtime", peer, False, False, None,
                   f"{host}-host → {peer} via `{invoker}` (SAGE 직접 호출, gstack 불요)")
    return res("blocked", peer, False, True, f"{peer}_cli_unavailable",
               f"cross_model on 이나 {peer} CLI 미가용 → Phase 05 BLOCKED")


_DEFAULT_PROFILE = {"runtime": {"host": "claude"}, "options": {"cross_model": False}}


def _load_profile_context(path):
    """반환 (profile|None, status). status 로 실패 원인 구분(Codex P1):
    'ok' | 'missing_file' | 'missing_pyyaml' | 'parse_error:<예외명>'.
    (이전엔 셋 다 None 으로 뭉개 사용자가 설정 무시 여부를 알 수 없었음.)"""
    if not os.path.exists(path):
        return None, "missing_file", None
    try:
        import yaml  # pyyaml (선언 의존성)
    except ImportError:
        return None, "missing_pyyaml", None
    layers = load_profile_layers(path)
    shared_load_error = next(
        (message for severity, message in layers.issues
         if severity == "FAIL" and getattr(message, "code", None) == "layers.yaml_parse_error"
         and message.arguments.get("label") == "shared"), None)
    if shared_load_error:
        return None, f"parse_error:{shared_load_error.arguments['kind']}", layers
    if layers.has_fail:
        return layers.effective, "layer_error", layers
    return layers.effective, "ok", layers


def _load_profile(path):
    profile, status, _ = _load_profile_context(path)
    return profile, status


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_codex_skill_deployment(prof_path, profile, language=None):
    """manifest-추적 skill 의 codex 전역 배포 상태 점검(Part C). 환경 부수상태라 WARN 만(FAIL 아님).

    repo .codex/skills/<id>/SKILL.md(정본) 대비 $CODEX_HOME/skills/<prefix>-<id>/SKILL.md(배포 캐시):
    미배포/내용불일치 → WARN + `sage generate --kind skill --deploy-codex` 안내. 정본 부재 skill 은 N/A(스킵).
    """
    import json
    # codex 전역 skill 발견은 codex-host 에서만 의미(claude-host 는 codex skill 미사용 → N/A 스킵).
    # 전역 배포는 opt-in(--deploy-codex)이므로 claude-host 에 거짓 WARN 을 내지 않는다(codex 리뷰 P1).
    if "codex" not in configured_hosts(profile):
        return
    # root 파생: 실제 프로젝트 profile(<root>/sage/project-profile.yaml)에서만. templates 기본은 스킵.
    # realpath 정규화(상대 --profile·심링크도 cwd 무관하게 올바른 root 파생 — codex 리뷰 P2).
    norm = os.path.normpath(os.path.realpath(prof_path))
    if not norm.endswith(os.path.join("sage", "project-profile.yaml")):
        return
    root = os.path.dirname(os.path.dirname(norm))
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    if not os.path.exists(manifest_path):
        return
    try:
        with open(manifest_path, encoding="utf-8") as f:
            assets = (json.loads(f.read()) or {}).get("assets", {})
    except Exception:
        return
    skill_ids = [k.split("/", 1)[1] for k in assets if k.startswith("skills/")]
    if not skill_ids:
        return
    from sage.commands.install import _codex_skills_root
    prefix = str((profile.get("project") or {}).get("prefix") or "").strip()
    g_root = _codex_skills_root()
    print(tr(language, 'cli.doctor.msg01'))
    if not prefix:
        # generate --deploy-codex 가 prefix 없이는 fail-closed(전역 네임스페이스 충돌 방지) → doctor 도 bare-id 점검 금지.
        print(tr(language, 'cli.doctor.msg02'))
        return
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_-]+$", prefix):
        # generate 와 동일 검증(경로 탈출 방지) — 안전치 않은 prefix 는 점검 불가.
        print(tr(language, 'cli.doctor.msg03', prefix=prefix))
        return
    for sid in sorted(skill_ids):
        if not _re.match(r"^[A-Za-z0-9_-]+$", sid):
            print(tr(language, 'cli.doctor.msg04', sid=sid))
            continue
        canon = os.path.join(root, ".codex", "skills", sid, "SKILL.md")
        if not os.path.exists(canon):
            print(tr(language, 'cli.doctor.msg05', sid=sid))
            continue
        gid = f"{prefix}-{sid}"
        gdst = os.path.join(g_root, gid, "SKILL.md")
        if not os.path.exists(gdst):
            print(tr(language, 'cli.doctor.msg06', sid=sid, gdst=gdst, sid2=sid))
        elif _sha256_file(gdst) != _sha256_file(canon):
            print(tr(language, 'cli.doctor.msg07', sid=sid, sid2=sid))
        else:
            print(tr(language, 'cli.doctor.msg08', sid=sid, gid=gid))


def _project_root_from_profile(prof_path):
    """실제 프로젝트 profile(<root>/sage/project-profile.yaml)에서 root 파생. templates 기본은 None.
    realpath 정규화(상대 --profile·심링크도 cwd 무관하게 올바른 root — codex 리뷰 P2와 동일 패턴)."""
    norm = os.path.normpath(os.path.realpath(prof_path))
    if not norm.endswith(os.path.join("sage", "project-profile.yaml")):
        return None
    return os.path.dirname(os.path.dirname(norm))


def _emit_core_drift(kind, id_, status, dst, stale, missing, language=None):
    if status == "ok":
        print(tr(language, 'cli.doctor.msg09', kind=kind, id_=id_, dst=dst))
    elif status == "missing":
        print(tr(language, 'cli.doctor.msg10', kind=kind, id_=id_, dst=dst))
        missing.append((kind, id_))
    elif status == "stale":
        print(tr(language, 'cli.doctor.msg11', kind=kind, id_=id_, dst=dst))
        stale.append((kind, id_))
    elif status == "source_missing":
        print(tr(language, 'cli.doctor.msg12', kind=kind, id_=id_))
    else:
        # status == "error" 면 dst 자리에는 경로가 아니라 진단이 온다 — 렌더를 거쳐야 문장이 된다.
        print(tr(language, 'cli.doctor.msg13', kind=kind, id_=id_,
                 dst=render_issue(language, dst)))


def _report_codex_core_skill_scope(root, manifest, language=None):
    """Report live Codex CORE skill copies without claiming undocumented host precedence."""
    print("## Codex CORE skill scope")
    if root is None or "codex" not in receipt_hosts(manifest, "claude"):
        print(tr(language, 'cli.doctor.msg14'))
        return
    from sage.commands import install
    receipts = manifest.get("core_skill_receipts") if isinstance(manifest, dict) else None
    receipt = receipts.get("codex") if isinstance(receipts, dict) else None
    if not install._valid_core_skill_receipt(receipt):
        print(tr(language, 'cli.doctor.msg15'))
        selected = None
    else:
        selected = receipt["scope"]
        print(f"  intended scope: {selected} (receipt SAGE {receipt['sage_version']})")

    duplicates = []
    conflicts = []
    cleanup_paths = set()
    for skill_id in install.core_skill_ids():
        surfaces = install.codex_core_skill_surfaces(root, skill_id)
        present = [(name, status, path) for name, (status, path) in surfaces.items()
                   if status != "missing"]
        if len(present) > 1:
            duplicates.append(skill_id)
            if any(status != "ok" for _name, status, _path in present):
                conflicts.append(skill_id)
            print(f"  ⚠️  ${skill_id}: duplicate; precedence=ambiguous")
            for name, status, path in present:
                intended = " (intended)" if name == selected else ""
                print(f"      {name}{intended}: {status} — {path}")
                if name != selected and path:
                    cleanup_paths.add(os.path.dirname(path))
    if not duplicates:
        print(tr(language, 'cli.doctor.msg16'))
    else:
        print(tr(language, 'cli.doctor.msg17', count=len(duplicates)))
        if conflicts:
            print("  ❌ version/content conflict: " + ", ".join(f"${sid}" for sid in conflicts))
        print(tr(language, 'cli.doctor.msg18'))
        for path in sorted(cleanup_paths):
            print(f"    - {path}")
        print(tr(language, 'cli.doctor.msg19'))


def _check_core_render_drift(profile, prof_path, language=None):
    """Hand-shipped CORE renders (CORE skills 7종 + roster agents 6종) are not
    manifest-tracked. A stale copy silently runs outdated profile/review-loop rules, and
    `sage install --force` overwrites local edits without warning. Diagnose stale/missing
    for the profile's host across BOTH skills and agents so that divergence is visible
    (이전엔 codex + 스킬만 점검 — claude host 와 에이전트는 사각지대였음).

    - 스킬: claude=repo `.claude/skills/<id>/SKILL.md`, codex=전역 `$CODEX_HOME/skills/<id>/SKILL.md`.
    - 에이전트: claude=`.claude/agents/<id>.md`, codex=`.codex/agents/<id>.md` (둘 다 repo 렌더, 동일 소스).
    로컬 커스터마이즈는 CORE 렌더 직접수정이 아니라 `sage/asset_overrides/**`(install-safe)로 두어 보존한다.
    """
    from sage.commands import install
    root = _project_root_from_profile(prof_path)   # None → templates 기본(프로젝트 아님)
    host = active_host(profile)
    manifest = None
    if root is not None:
        import json
        try:
            manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
        except Exception:
            manifest = None
    hosts = receipt_hosts(manifest, host)
    print(tr(language, 'cli.doctor.msg20'))
    print(tr(language, 'cli.doctor.msg21', hosts=hosts))
    for _, message in receipt_issues(profile, manifest):
        print(tr(language, 'cli.doctor.msg22', message=message))
    stale, missing = [], []

    for installed_host in hosts:
        print(f"  [{installed_host}] discovery surface")
        for sid in install.core_skill_ids():
            if installed_host == "codex":
                receipts = manifest.get("core_skill_receipts") if isinstance(manifest, dict) else None
                receipt = receipts.get("codex") if isinstance(receipts, dict) else None
                scope = receipt.get("scope") if install._valid_core_skill_receipt(receipt) else None
                if scope == "disabled":
                    continue
                if scope not in ("global", "project-local"):
                    print(tr(language, 'cli.doctor.msg23', sid=sid))
                    continue
                status, dst = install.codex_core_skill_status(sid, dest=root, scope=scope)
            elif root is not None:
                status, dst = install.core_render_status(
                    install._core_skill_source(sid),
                    os.path.join(root, ".claude", "skills", sid, "SKILL.md"))
            else:
                continue
            _emit_core_drift("skill", sid, status, dst, stale, missing, language)

    # install 이 쓰기 전에 거부하는 것과 **같은 검사**. 여기서 잡히면 렌더 대조는 의미가 없다.
    invalid = [m for sev, m in install.team_runtime_issues(profile) if sev == "FAIL"]
    for msg in invalid:
        print(f"  ❌ [agent] {msg}")

    if root is not None and not invalid:
        for installed_host in hosts:
            agent_dir = ".claude" if installed_host == "claude" else ".codex"
            for aid in install.core_agent_ids():
                overrides = install.agent_frontmatter_overrides(profile, aid) if installed_host == "claude" else {}
                status, dst = install.core_render_status(
                    install._core_agent_source(aid),
                    os.path.join(root, agent_dir, "agents", f"{aid}.md"), overrides)
                _emit_core_drift("agent", aid, status, dst, stale, missing, language)
    elif root is None:
        print(tr(language, 'cli.doctor.msg24'))

    # 오버레이 물리화 drift 표면화(진단용). 권위 게이트는 `sage validate`(exit 1) — 여기선 가시성만 제공.
    if root is not None:
        from sage import overlay_materialize as _mat
        _mani = manifest
        cr = _mani.get("core_renders") if isinstance(_mani, dict) else None
        if cr:
            for installed_host in hosts:
                ov = _mat.check(root, installed_host, cr)
                if ov:
                    print(tr(language, 'cli.doctor.msg25', installed_host=installed_host))
                    for sev, key, msg in ov:
                        print(f"    {'❌' if sev == 'FAIL' else '🕒'} {sev} [{key}] {msg}")
        elif isinstance(_mani, dict) and "core_renders" not in _mani:
            print(tr(language, 'cli.doctor.msg26'))

    if invalid:
        # 이 profile 로는 install 이 거부한다 → `--force` 를 권하면 유저가 헛돈다. stale/missing 안내는
        # profile 을 고치고 재진단한 뒤에만 의미가 있으므로 여기서 멈춘다.
        print(tr(language, 'cli.doctor.msg27', count=len(invalid)))
        if stale or missing:
            print(tr(language, 'cli.doctor.msg28', count=len(stale) + len(missing)))
        return 1
    if stale or missing:
        repair_host = hosts[0] if len(hosts) == 1 else "<host>"
        repair_scope = None
        if repair_host == "codex" and isinstance(manifest, dict):
            receipts = manifest.get("core_skill_receipts")
            receipt = receipts.get("codex") if isinstance(receipts, dict) else None
            if install._valid_core_skill_receipt(receipt):
                repair_scope = receipt["scope"]
        scope_arg = (f" --skill-scope {repair_scope}"
                     if repair_scope in ("global", "project-local") else "")
        if stale:
            print(tr(language, 'cli.doctor.msg29', count=len(stale), repair_host=repair_host, scope_arg=scope_arg))
        if missing:
            print(tr(language, 'cli.doctor.msg30', count=len(missing), repair_host=repair_host, scope_arg=scope_arg))
        print(tr(language, 'cli.doctor.msg31'))
    else:
        print(tr(language, 'cli.doctor.msg32'))

    if root is not None:
        print("## critical-domain protocol pointers")
        for domain in (profile.get("risk") or {}).get("domains") or []:
            pointer = domain.get("protocol_pointer") if isinstance(domain, dict) else None
            if pointer and os.path.isfile(os.path.join(root, pointer)):
                print(f"  ✅ {domain.get('id')}: {pointer}")
            else:
                print(tr(language, 'cli.doctor.msg33', domain_get=domain.get('id'), arg=pointer or 'unset'))
    return 0


def _is_repo_boundary(path):
    """git 저장소 경계. `.git`(디렉토리·worktree 파일) 또는 bare repo 레이아웃.
    상위 저장소의 profile 을 집어 남의 프로젝트를 진단하지 않도록 여기서 상승을 멈춘다."""
    if os.path.exists(os.path.join(path, ".git")):
        return True
    # bare repo: HEAD 는 파일, objects/refs 는 디렉토리. 존재만 보면 평범한 디렉토리를 오인한다.
    return (os.path.isfile(os.path.join(path, "HEAD"))
            and all(os.path.isdir(os.path.join(path, n)) for n in ("objects", "refs")))


def _discover_profile(start=None):
    """cwd 부터 위로 올라가며 `<root>/sage/project-profile.yaml` 을 찾는다.

    없으면 None → 호출자가 templates 기본으로 폴백. 자동탐색이 없으면 설치된 프로젝트에서
    맨손 `sage doctor` 가 templates profile 을 읽어 **로스터 에이전트 drift 점검을 통째로 건너뛴다**
    (프로젝트 루트를 못 구해서). 즉 stale 안내가 사실상 동작하지 않는다(codex 2R).
    """
    cur = os.path.realpath(start or os.getcwd())
    while True:
        cand = os.path.join(cur, "sage", "project-profile.yaml")
        if os.path.isfile(cand):
            return cand
        if _is_repo_boundary(cur):
            return None
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _report_model_routing(profile, current=None, language=None):
    """Compare explicit profile model selections with read-only local catalogs."""
    from sage.model_catalog import discover
    from sage.model_routing import catalog_status, profile_issues as routing_issues, reviewer_selection

    print("## host model routing")
    for severity, message in routing_issues(profile):
        print(f"  {'❌' if severity == 'FAIL' else '⚠️ '} {severity} {message}")

    selected = []
    components = profile.get("components") if isinstance(profile, dict) else None
    if isinstance(components, list):
        for index, component in enumerate(components):
            if not isinstance(component, dict):
                continue
            cid = component.get("id") or f"index-{index}"
            models = component.get("runtime_models")
            if isinstance(models, dict):
                for host, model in models.items():
                    if host in ("claude", "codex") and isinstance(model, str) and model:
                        selected.append((f"component:{cid}", host, model))
    cross = profile.get("cross_model") if isinstance(profile, dict) else None
    dropped = None
    if isinstance(cross, dict) and cross.get("reviewer") is not None:
        host, model = reviewer_selection(profile, current)
        # 실행 시 버려질 모델을 "선택됨" 으로 보여주면 진단이 실제와 어긋난다 — 같은 필터를 태운다.
        from sage.commands.review import _model_for_peer
        model, dropped = _model_for_peer(profile, host, model)
        if model:
            selected.append(("cross-reviewer", host, model))
        elif dropped:
            print(f"  cross-reviewer : {host}/(peer CLI default) — {dropped}")
    if not selected:
        if not dropped:
            print(tr(language, 'cli.doctor.msg34'))
        return

    catalogs = {host: discover(host) for host in {host for _, host, _ in selected}}
    for owner, host, model in selected:
        status = catalog_status(catalogs[host], model)
        print(f"  {owner} : {host}/{model} → {status}")
    for host, catalog in sorted(catalogs.items()):
        print(f"  catalog:{host} source={catalog['source']} verification={catalog['verification']}"
              f" stale={catalog.get('stale')}")


def _report_version_contract(profile, manifest, language=None):
    from sage import __version__
    from sage.version_contract import version_axes, version_contract_issues

    axes = version_axes(profile, manifest, __version__)
    print("## SAGE version contract")
    print(f"  required  : {axes.required}")
    print(f"  installed : {axes.installed}")
    print(f"  generated : {axes.generated}")
    print(f"  runtime   : {axes.runtime}")
    failed = False
    for issue in version_contract_issues(profile, manifest, __version__):
        mark = "❌" if issue.severity == "FAIL" else ("⚠️ " if issue.severity == "WARN" else "ℹ️ ")
        print(f"  {mark} {issue.severity} [{issue.axis}] "
              f"{render_issue(language, issue.message)}")
        if issue.remediation:
            print(f"      → `{render_issue(language, issue.remediation)}`")
        failed = failed or issue.severity == "FAIL"
    return failed


def run(args):
    from sage import _resources
    language = language_of(args)
    prof_path = (args.profile or _discover_profile()
                 or os.path.join(_resources.templates_dir(), "project-profile.yaml"))
    profile, status, layers = _load_profile_context(prof_path)
    print("== sage doctor ==")
    print(f"  profile: {prof_path}")
    rc = 0
    if status == "ok":
        pass  # profile 정상 로드
    elif status == "missing_file":
        print(tr(language_of(args), 'cli.doctor.msg35', prof_path=prof_path))
        profile = dict(_DEFAULT_PROFILE)
    elif status == "missing_pyyaml":
        print(tr(language_of(args), 'cli.doctor.msg36'))
        profile = dict(_DEFAULT_PROFILE)
    elif status.startswith("parse_error"):
        rc = 1  # profile 이 존재하나 깨짐 = 실제 오류(설정이 조용히 무시되는 것 방지)
        print(tr(language_of(args), 'cli.doctor.msg37', status_split=status.split(':', 1)[1], prof_path=prof_path))
        print(tr(language_of(args), 'cli.doctor.msg38'))
        profile = dict(_DEFAULT_PROFILE)
    elif status == "layer_error":
        rc = 1
        print(tr(language_of(args), 'cli.doctor.msg39'))
        for severity, message in layers.issues:
            if severity in ("FAIL", "WARN"):
                print(f"        {severity}: {render_issue(language_of(args), message)}")

    if layers is not None:
        local_state = "loaded" if layers.local is not None else "missing (legacy/default behavior)"
        print(f"  local profile: {layers.local_path} — {local_state}")
        root = _project_root_from_profile(prof_path)
        if root is not None:
            for severity, message in local_profile_git_issues(root, layers.local_path):
                print(f"  {'⚠️ ' if severity == 'WARN' else 'ℹ️ '} {severity} "
                      f"{render_issue(language_of(args), message)}")

    # 실행 환경: generate 가 등록한 command와 같은 launcher 후보를 점검한다.
    sage_hook, sage_hook_source = resolve_sage_hook()
    bash_path = shutil.which("bash")
    print(tr(language_of(args), 'cli.doctor.msg40'))
    print(f"  OS       : {platform.system()} ({os.name})")
    print(f"  python   : {platform.python_version()} (sys.executable={sys.executable})")
    print(f"  sage-hook: {sage_hook or 'NOT FOUND'}"
          + (f" (source={sage_hook_source})" if sage_hook else tr(
             language, "cli.doctor.no_hook_entry_windows" if os.name == "nt"
             else "cli.doctor.no_hook_entry_posix")))
    print(f"  bash     : {bash_path or 'NOT FOUND'}"
          + ("" if bash_path else tr(language, "cli.doctor.bash_optional_full")))
    if os.name == "nt" or platform.system() == "Windows":
        print(tr(language_of(args), 'cli.doctor.msg41'))

    # 옵션 의존성
    caps_prof = profile.get("capabilities", {}) or {}
    # 7차 배치2: cross-model 은 peer 런타임 CLI 직접 호출(codex exec / claude -p) — peer CLI 가용성으로 판정.
    codex_avail = bool(shutil.which("codex")) or bool(caps_prof.get("codex"))
    claude_avail = bool(shutil.which("claude")) or bool(caps_prof.get("claude"))
    opts = profile.get("options", {}) or {}
    # 진단 전체가 하나의 host 판정을 쓴다. 앞뒤가 서로 다른 기준을 쓰면 stale pin 상황에서 같은
    # 실행이 peer=codex 와 reviewer runtime=claude 를 동시에 보고해, 사용자가 멀쩡한 설정을 고치게 된다.
    from sage.runtime_hosts import detect_current_host, running_host
    from sage.commands.review import host_detection_notes
    detected = detect_current_host()
    host = running_host(profile, None) or active_host(profile)
    from sage.model_routing import reviewer_selection as _reviewer_selection
    peer, _ = _reviewer_selection(profile, detected)
    peer_avail = codex_avail if peer == "codex" else claude_avail
    _kc = profile.get("knowledge_capture")
    vault = _kc.get("vault_path", "") if isinstance(_kc, dict) else ""   # 비-dict kc 방어(codex A)
    print(tr(language_of(args), 'cli.doctor.msg42'))
    desired_hosts = configured_hosts(profile)
    print(f"  active_host : {host}" + ("" if detected else tr(language_of(args), 'cli.doctor.msg43')))
    print(tr(language_of(args), 'cli.doctor.msg44', desired_hosts=desired_hosts))
    for note in host_detection_notes(profile, detected):
        print(f"  ⚠️  WARN {note}")
    for severity, message in profile_issues(profile):
        if severity in ("FAIL", "WARN"):
            print(f"  {'❌' if severity == 'FAIL' else '⚠️ '} {severity} "
                  f"{render_issue(language_of(args), message)}")
    from sage.commands.review import effort_issue, resolve_effort   # review→doctor import 순환 회피(함수 지역)
    _eff, _set = resolve_effort(profile)   # `or` 로 판정하면 effort: false/0 을 "기본값" 이라 거짓 보고한다
    _issue = effort_issue(peer, _eff) if _set is not None else None
    _note = " — 기본값" if _set is None else (f" — ❌ {_issue}" if _issue else "")
    print(f"  cross_model : {opts.get('cross_model', False)} (peer={peer}, effort={_eff!r}{_note})")
    _invoker = "codex exec" if peer == "codex" else "claude -p"
    print(tr(language_of(args), 'cli.doctor.msg45', peer=peer, arg='available' if peer_avail else 'unavailable', peer2=peer, peer3=peer, invoker=_invoker))
    print(tr(language_of(args), 'cli.doctor.msg46', opts_get=opts.get('codegraph', 'optional')))
    print(f"  obsidian    : vault_path={'set' if vault else tr(language_of(args), 'cli.doctor.msg47')}")
    _report_model_routing(profile, detected, language)

    # codex skill 전역 배포 점검(Part C) — manifest-추적 프로젝트 skill 이 codex 전역에 배포됐는지.
    #   정본 = repo .codex/skills/<id>/SKILL.md (manifest 추적), 전역 = $CODEX_HOME/skills/<prefix>-<id> (발견용 캐시).
    #   validate 는 전역을 무시(clone-stable repo 정본만) → 전역 staleness 는 여기(환경 진단)에서 WARN.
    root = _project_root_from_profile(prof_path)
    manifest = None
    if root is not None:
        try:
            import json
            manifest = json.loads(Path(os.path.join(root, "docs", "sage_harness", ".manifest.json")).read_text())
        except Exception:
            manifest = None
    if _report_version_contract(profile, manifest, language):
        rc = 1
    _report_codex_core_skill_scope(root, manifest, language)
    if _check_core_render_drift(profile, prof_path, language):
        rc = 1   # 에이전트 frontmatter 로 주입될 값이 무효 = 설정이 조용히 무시되는 것 방지
    _check_codex_skill_deployment(prof_path, profile, language)

    # reviewer resolution — 위에서 판별한 같은 값을 쓴다(감지 중복·기준 분기 방지).
    rr = reviewer_resolution(profile, {"codex": codex_avail, "claude": claude_avail}, detected)
    print("## Phase 05 reviewer")
    print(f"  detected: {detected or tr(language_of(args), 'cli.doctor.msg48')}")
    print(f"  mode    : {rr['reviewer_mode']} (runtime={rr['reviewer_runtime']})")
    print(f"  notice  : {rr['notice']}")
    if rr["reviewer_mode"] == "blocked":
        print(f"  ⛔ L3 REVIEW BLOCKED: {rr['reviewer_degrade_reason']}")
    elif rr["reviewer_degraded"]:
        print(f"  ⚠️  L3 REVIEW DEGRADED: {rr['reviewer_degrade_reason']}")

    # Loop A (review_loop) — 켜졌는지 + 설정 유효성(profile_validate 의 review_loop 발 이슈만 표면화).
    # 환경 진단이라 정보성. 강제(fail-closed)는 generate/validate 가 담당(같은 validate_profile 경유).
    _report_review_loop(profile, language)
    _report_acceptance_policy(profile, _project_root_from_profile(prof_path), language)
    # Loop C (retro gate) — 미완료로 종료된 사이클(retro --check 안 하고 06 완료)을 표면화(9-C v1).
    _report_retro_gate(profile, _project_root_from_profile(prof_path), language)
    return rc


def _report_retro_gate(profile, root, language=None):
    """retro_audit.jsonl 에서 최신 상태가 missing 인 run(= retro --check 없이 06 완료된 사이클)을
    표면화한다. Stop 훅이 남긴 영구 기록의 사람용 소비 경로(9-C v1 유저 스코프). root 미상이면 skip."""
    mode = ((profile.get("pdca") or {}).get("retro") or {}).get("report_gate_enforce") or "off"
    print("## Loop C (retro gate)")
    print(f"  enforce : {mode}")
    if root is None:
        print(tr(language, 'cli.doctor.msg49'))
        return
    try:
        from sage import _resources
        rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
        if rt not in sys.path:
            sys.path.insert(0, rt)
        import retro_audit
        # 신뢰불가(디렉토리·깨진 심링크·권한없음·비-UTF-8)를 '미완료 없음' 으로 오보하지 않는다
        # (codex 구현리뷰 3R·4R P1: 감사 불능이 '없음' 으로 둔갑 금지). status 로 분기.
        status, summary = retro_audit.audit_summary_status(root)
    except Exception:
        print(tr(language, 'cli.doctor.msg50'))
        return
    if status == "unreadable":
        print(tr(language, 'cli.doctor.msg51', retro_audit_audit_path=retro_audit.audit_path(root)))
        return
    missing = sorted(rid for rid, s in summary.items() if s.get("state") == "missing")
    if not missing:
        print(tr(language, 'cli.doctor.msg52'))
        return
    for rid in missing:
        print(tr(language, 'cli.doctor.msg53', rid=rid, rid2=rid, rid3=rid))


def _report_review_loop(profile, language=None):
    rl = ((profile.get("pdca") or {}).get("review_loop")) or {}
    print("## Loop A (Phase 05 review_loop)")
    if not rl:
        print(tr(language, 'cli.doctor.msg54'))
        return
    enabled = rl.get("enabled") is True
    print(f"  enabled : {enabled} (lenses {len(rl.get('lenses') or [])}, refuters {rl.get('refuters')}, "
          f"max_iter {rl.get('max_iterations')})")
    # review_loop 발 검증 이슈만 추려 표면화(전체 profile 검증은 sage validate 담당).
    try:
        from sage.profile_validate import _review_loop_issues
        for sev, msg in _review_loop_issues(profile):
            if sev in ("FAIL", "WARN"):
                print(f"  {'❌' if sev == 'FAIL' else '⚠️ '} {sev} {msg}")
    except Exception:
        pass


def _report_acceptance_policy(profile, root, language=None):
    acceptance = ((profile.get("verification") or {}).get("acceptance") or {})
    print("## Acceptance report policy")
    if not isinstance(acceptance, dict) or acceptance.get("enabled") is not True:
        print("  enabled : false/unset")
        return
    by_risk = acceptance.get("report_gate_by_risk")
    legacy = acceptance.get("report_gate_enforce")
    if legacy is not None:
        behavior = "전 위험도 enforce 유지" if legacy == "enforce" else "L2 advisory/L3 enforce로 안전 승격"
        print(f"  ⚠️  legacy report_gate_enforce={legacy} — {behavior}")
        print("      migration: report_gate_by_risk: { L2: advisory, L3: enforce }")
    elif isinstance(by_risk, dict):
        print(f"  policy  : L2={by_risk.get('L2')} L3={by_risk.get('L3')} "
              "(unknown=enforce)")
    else:
        print("  policy  : default L2=advisory L3=enforce (unknown=enforce)")
    waiver = acceptance.get("waiver") if isinstance(acceptance.get("waiver"), dict) else {}
    enabled = waiver.get("enabled") is True
    print(f"  waiver  : {'enabled' if enabled else 'disabled'} "
          "(exact cycle + required acceptance ID, explicit CLI grant only)")
    if not enabled or root is None:
        return
    try:
        from sage.commands.acceptance_waiver import _load_runtime_modules
        aw, _, _ = _load_runtime_modules()
        summary = aw.audit_summary(root)
    except Exception as exc:
        print(tr(language, 'cli.doctor.msg55', arg=type(exc).__name__, exc=exc))
        return
    if not summary["valid"]:
        print(tr(language, 'cli.doctor.msg56') + "; ".join(summary["issues"][:3]))
    else:
        print(f"  active  : {len(summary['active'])} ({aw.audit_path(root)})")
