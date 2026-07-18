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


def register(sub):
    p = sub.add_parser("sync-overlays",
                       help="오버레이 편집 후 CORE 렌더의 관리 블록을 다시 물리화합니다")
    p.add_argument("--root", default=None, help="SAGE 레포 루트 (기본: cwd 에서 탐색)")
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
        print("[sage sync-overlays] TOOL ERROR: docs/sage_harness/.manifest.json 을 찾을 수 없음", file=sys.stderr)
        return 2
    manifest_path = os.path.join(root, "docs", "sage_harness", ".manifest.json")
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[sage sync-overlays] TOOL ERROR: manifest 파싱 실패: {e}", file=sys.stderr)
        return 2
    if not isinstance(manifest, dict):
        print("[sage sync-overlays] TOOL ERROR: manifest 최상위가 object 아님", file=sys.stderr)
        return 2
    hosts = _installed_hosts(manifest)
    if not hosts:
        print("[sage sync-overlays] TOOL ERROR: 설치 host 영수증 없음 — `sage install --host ... --force` 필요",
              file=sys.stderr)
        return 2

    hard_fail = False

    # FB12 migration safety: 일반 preflight가 blocked overlay 파일 때문에 실패하더라도 과거에
    # 물리화된 gate-bearing managed block은 남겨두지 않는다. SAGE 마커 구간만 제거하고 manifest는
    # 갱신하지 않는다.
    cleanup_plans = []
    for host in hosts:
        host_cleanup, cleanup_errors = _mat.plan_blocked_cleanup(root, host)
        for p, msg in cleanup_errors:
            print(f"❌ blocked block 정리 실패[{host}]({os.path.relpath(p, root)}): {msg}", file=sys.stderr)
            hard_fail = True
        cleanup_plans.extend(host_cleanup)
    deduped_cleanup = {plan[0]: plan for plan in cleanup_plans}
    cleanup_changed = _mat.apply_materialization(deduped_cleanup.values())
    for p in sorted(cleanup_changed):
        print(f"  ~ blocked 관리 블록 제거: {os.path.relpath(p, root)}")
    if hard_fail:
        suffix = "정리 가능한 blocked 관리 블록만 제거됨, manifest 미갱신" if cleanup_changed else "렌더/manifest 미갱신"
        print(f"---- sync-overlays: FAIL ({suffix}) ----")
        return 1

    # cleanup은 업그레이드 source/version skew 자체가 생기는 FB12 migration에서도 먼저 수행해야 한다.
    # 이후 검사는 일반 overlay/receipt를 재스탬프하지 못하게 기존 fail-closed 순서를 유지한다.
    installed_hash = manifest.get("installed_core_content_hash")
    if installed_hash and installed_hash != source_core_content_hash():
        print("❌ 현재 SAGE 엔진과 install source identity가 다름 — blocked block 정리 후 "
              "`sage install --force` 로 base/영수증을 함께 갱신하세요", file=sys.stderr)
        return 1

    existing_renders = manifest.get("core_renders")
    existing_renders = existing_renders if isinstance(existing_renders, dict) else {}
    skew = [key for key, value in existing_renders.items()
            if key.split("/", 1)[0] in hosts
            and (not isinstance(value, dict) or value.get("sage_version") != __version__)]
    if skew:
        print(f"❌ {len(skew)}개 CORE 렌더가 현재 SAGE {__version__}와 다른 버전 — blocked block 정리 후 "
              "`sage install --force`를 요구합니다", file=sys.stderr)
        return 1

    # 1. 오버레이 파일 선열거 → 오타/미지 CORE id, (c)/미분류 자산은 하드-리포트(fail-closed).
    for kind, id, path in _cls.overlay_files(root):
        rel = os.path.relpath(path, root)
        filename_error = _cls.overlay_filename_error(kind, id, path)
        if filename_error:
            print(f"❌ {filename_error}: {rel}", file=sys.stderr)
            hard_fail = True
        elif not _cls.is_core(kind, id):
            print(f"❌ 미지/오타 CORE 자산 오버레이: {rel} — '{id}' 는 CORE {kind} 가 아닙니다", file=sys.stderr)
            hard_fail = True
        elif _cls.classify(kind, id) == "blocked":
            print(f"❌ 오버레이 미지원 자산: {rel} — {kind}/{id} 는 게이트-미보증(SD-8 전까지 blocked)", file=sys.stderr)
            hard_fail = True

    if hard_fail:
        suffix = "blocked 관리 블록만 제거됨, 일반 렌더/manifest 미갱신" if cleanup_changed else "렌더/manifest 미갱신"
        print(f"---- sync-overlays: FAIL ({suffix}) ----")
        return 1

    # 2. 설치된 모든 host를 물리화한다. 한 host만 갱신하면 다른 discovery surface와 앵커가
    #    stale해지므로 manifest.installed_hosts가 동기화 범위의 단일 출처다.
    merged_renders = dict(existing_renders)
    all_plans = []
    for host in hosts:
        host_renders, host_plans, errors = _mat.plan_materialize(root, host)
        for p, msg in errors:
            print(f"❌ 물리화 실패[{host}]({os.path.relpath(p, root)}): {msg}", file=sys.stderr)
            hard_fail = True
        if errors:
            continue
        all_plans.extend(host_plans)
        merged_renders = {key: value for key, value in merged_renders.items()
                          if not key.startswith(host + "/")}
        merged_renders.update(host_renders)

    if hard_fail:
        print("---- sync-overlays: FAIL (렌더/manifest 미갱신) ----")
        return 1

    # 모든 host가 preflight를 통과한 뒤에만 렌더를 쓴다. 파일시스템 장애 자체를 원자적으로
    # 롤백할 수는 없지만, 알려진 host별 검증 오류로 mixed state가 생기는 것은 방지한다.
    changed = _mat.apply_materialization(all_plans)
    for p in sorted(set(changed)):
        print(f"  ~ 물리화: {os.path.relpath(p, root)}")

    # 3. manifest.core_renders 앵커 갱신(엔진 소유 최상위 맵만 교체, 나머지 보존).
    manifest["core_renders"] = merged_renders
    _oc.write_text_lf(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

    print(f"---- sync-overlays: OK ({len(set(changed))}개 갱신, {len(merged_renders)}개 앵커, "
          f"hosts={hosts}) ----")
    return 0
