"""sage sync-overlays — CORE 렌더 오버레이 재물리화(블록만) + core_renders 앵커 갱신.

오버레이(sage/asset_overrides/{agents,skills}/<id>.md)를 편집한 뒤 base 재복사 없이 렌더의
관리 블록만 다시 수렴시킨다(install --force 와 달리 CORE base 를 건드리지 않음). install·L1·
validate 와 동일한 overlay_materialize 로직을 경유한다.

fail-closed: 오타/미지 CORE id, (c)/미분류 자산 오버레이 파일은 하드-리포트(exit 1). (a)/(b)만
합성되고, 삭제된 오버레이의 잔존 블록은 제거된다.
"""
import json
import os
import sys
from pathlib import Path

from sage import __version__
from sage.build_identity import source_core_content_hash
from sage import overlay_classify as _cls
from sage import overlay_common as _oc
from sage import overlay_materialize as _mat
from sage.i18n import language_of, render_issue, tr


def register(sub, context):
    p = sub.add_parser("sync-overlays",
                       help=tr(context, "cli.sync_overlays.sync_overlays"))
    p.add_argument("--root", default=None, help=tr(context, "cli.sync_overlays.root"))
    p.set_defaults(func=run)


def _find_root(start):
    """docs/sage_harness/.manifest.json 을 가진 상위 디렉토리 탐색(validate 와 동일 규약)."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cur, "docs", "sage_harness", ".manifest.json")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def _installed_hosts(manifest):
    hosts = manifest.get("installed_hosts") if isinstance(manifest, dict) else None
    if not isinstance(hosts, list):
        hosts = [manifest.get("host_runtime")] if isinstance(manifest, dict) else []
    return list(dict.fromkeys(h for h in hosts if h in ("claude", "codex")))


def run(args):
    root = _find_root(args.root)
    if not root:
        print(tr(language_of(args), "cli.sync_overlays.msg01"), file=sys.stderr)
        return 2
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(tr(language_of(args), "cli.sync_overlays.msg02", e=e), file=sys.stderr)
        return 2
    if not isinstance(manifest, dict):
        print(tr(language_of(args), "cli.sync_overlays.msg03"), file=sys.stderr)
        return 2
    hosts = _installed_hosts(manifest)
    if not hosts:
        print(tr(language_of(args), "cli.sync_overlays.msg04"),
              file=sys.stderr)
        return 2

    hard_fail = False
    skill_scopes = {}
    for host in hosts:
        if host != "codex":
            skill_scopes[host] = None
            continue
        receipt_state, _receipt_scope = _mat.codex_skill_scope_receipt_state(manifest)
        if receipt_state == "malformed":
            print(tr(language_of(args), "cli.sync_overlays.msg05"),
                  file=sys.stderr)
            hard_fail = True
        skill_scopes[host] = _mat.resolve_codex_skill_scope(root, manifest=manifest)

    # FB12 migration safety: 일반 preflight가 blocked overlay 파일 때문에 실패하더라도 과거에
    # 물리화된 gate-bearing managed block은 남겨두지 않는다. SAGE 마커 구간만 제거하고 manifest는
    # 갱신하지 않는다.
    cleanup_plans = []
    for host in hosts:
        host_cleanup, cleanup_errors = _mat.plan_blocked_cleanup(
            root, host, codex_skill_scope=skill_scopes[host])
        for p, msg in cleanup_errors:
            print(tr(language_of(args), "cli.sync_overlays.msg06", host=host,
                     os_path=os.path.relpath(p, root),
                     msg=render_issue(language_of(args), msg)), file=sys.stderr)
            hard_fail = True
        cleanup_plans.extend(host_cleanup)
    deduped_cleanup = {plan[0]: plan for plan in cleanup_plans}
    cleanup_changed = _mat.apply_materialization(deduped_cleanup.values())
    for p in sorted(cleanup_changed):
        print(tr(language_of(args), "cli.sync_overlays.msg07", os_path=os.path.relpath(p, root)))
    if hard_fail:
        suffix = (tr(language_of(args), "cli.sync_overlays.suffix_cleanup_only")
                  if cleanup_changed else
                  tr(language_of(args), "cli.sync_overlays.suffix_render_manifest_unchanged"))
        print(tr(language_of(args), "cli.sync_overlays.msg16", suffix=suffix))
        return 1

    # cleanup은 업그레이드 source/version skew 자체가 생기는 FB12 migration에서도 먼저 수행해야 한다.
    # 이후 검사는 일반 overlay/receipt를 재스탬프하지 못하게 기존 fail-closed 순서를 유지한다.
    installed_hash = manifest.get("installed_core_content_hash")
    if installed_hash and installed_hash != source_core_content_hash():
        print(tr(language_of(args), "cli.sync_overlays.msg08"), file=sys.stderr)
        return 1

    existing_renders = manifest.get("core_renders")
    existing_renders = existing_renders if isinstance(existing_renders, dict) else {}
    skew = [key for key, value in existing_renders.items()
            if key.split("/", 1)[0] in hosts
            and (not isinstance(value, dict) or value.get("sage_version") != __version__)]
    if skew:
        print(tr(language_of(args), "cli.sync_overlays.msg09", count=len(skew), version=__version__), file=sys.stderr)
        return 1

    # 1. 오버레이 파일 선열거 → 오타/미지 CORE id, (c)/미분류 자산은 하드-리포트(fail-closed).
    for kind, id, path in _cls.overlay_files(root):
        rel = os.path.relpath(path, root)
        filename_error = _cls.overlay_filename_error(kind, id, path)
        if filename_error:
            print(f"❌ {filename_error}: {rel}", file=sys.stderr)
            hard_fail = True
        elif not _cls.is_core(kind, id):
            print(tr(language_of(args), "cli.sync_overlays.msg10", rel=rel, id_=id, kind=kind), file=sys.stderr)
            hard_fail = True
        elif _cls.classify(kind, id) == "blocked":
            print(tr(language_of(args), "cli.sync_overlays.msg11", rel=rel, kind=kind, id_=id), file=sys.stderr)
            hard_fail = True

    if hard_fail:
        suffix = (tr(language_of(args), "cli.sync_overlays.suffix_blocked_cleanup_only")
                  if cleanup_changed else
                  tr(language_of(args), "cli.sync_overlays.suffix_render_manifest_unchanged"))
        print(tr(language_of(args), "cli.sync_overlays.msg16", suffix=suffix))
        return 1

    # 2. 설치된 모든 host를 물리화한다. 한 host만 갱신하면 다른 discovery surface와 앵커가
    #    stale해지므로 manifest.installed_hosts가 동기화 범위의 단일 출처다.
    merged_renders = dict(existing_renders)
    all_plans = []
    for host in hosts:
        host_renders, host_plans, errors = _mat.plan_materialize(
            root, host, skill_scopes[host])
        for p, msg in errors:
            print(tr(language_of(args), "cli.sync_overlays.msg12", host=host,
                     os_path=os.path.relpath(p, root),
                     msg=render_issue(language_of(args), msg)), file=sys.stderr)
            hard_fail = True
        if errors:
            continue
        all_plans.extend(host_plans)
        merged_renders = {key: value for key, value in merged_renders.items()
                          if not key.startswith(host + "/")}
        merged_renders.update(host_renders)

    if hard_fail:
        print(tr(language_of(args), "cli.sync_overlays.msg13"))
        return 1

    # 모든 host가 preflight를 통과한 뒤에만 렌더를 쓴다. 파일시스템 장애 자체를 원자적으로
    # 롤백할 수는 없지만, 알려진 host별 검증 오류로 mixed state가 생기는 것은 방지한다.
    changed = _mat.apply_materialization(all_plans)
    for p in sorted(set(changed)):
        print(tr(language_of(args), "cli.sync_overlays.msg14", os_path=os.path.relpath(p, root)))

    # 3. manifest.core_renders 앵커 갱신(엔진 소유 최상위 맵만 교체, 나머지 보존).
    manifest["core_renders"] = merged_renders
    _oc.write_text_lf(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    print(tr(language_of(args), "cli.sync_overlays.msg15", count=len(set(changed)), count2=len(merged_renders), hosts=hosts))
    return 0
