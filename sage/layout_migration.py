"""구 레이아웃(`scripts/sage_harness/`) → 신 레이아웃(`sage_harness/`) 이행.

## 이 모듈이 하지 않는 것

**파일을 옮기지 않는다.** 앞선 초안들은 구 위치의 바이트를 신 위치로 나르는 설계였고, 그래서
교차 부모 rename·staging 트리·출처 receipt·복사 primitive 가 줄줄이 따라왔다. 전제가 틀렸다.

SAGE 배포 자산의 바이트는 **패키지가 원본을 갖고 있다.** 보존할 것이 없는 자리에 보존 장치를
설계할 이유가 없다. 그래서 이행은 이렇게 읽는다.

> 현재 패키지의 SAGE 자산을 신 경로에 **다시 생성**하고, 신 경로가 실제로 서는지 **검증**한
> 다음, 구 경로에서 SAGE 소유임을 **증명할 수 있는** 파일만 제거한다.

배치와 재생성과 검증은 `upgrade` 의 기존 단계가 이미 한다. 이 모듈은 **무엇을 지워도 되는가**와
**언제 전환하는가**만 소유한다.

## 활성 전환점

신 트리가 생겼다는 것은 "배치됐다" 는 뜻이지 "검증됐다" 는 뜻이 아니다. 그래서 전환 구간에서는
`hook_entry` 가 **구 경로를 우선**한다(`hook_entry._resolve_core_dir`). 지금까지 돌던 게이트가
계속 돈다.

전환점은 구 sentinel(`runtime/run_hook.py`)의 제거 하나다. 그 파일이 사라지는 순간부터 신
경로가 정본이고, 그 전까지는 아니다. 이 한 지점 말고 "이행이 어디까지 됐는가" 를 기록하는
상태는 두지 않는다 — 상태를 두면 그 상태와 실제 트리가 어긋나는 경우가 새로 생긴다.

## 사용자 코드는 옮기지 않는다

project hook 과 custom strategy 는 사용자가 쓴 코드다. 재생성할 수 없고, 도구가 옮길 자리를
임의로 정할 수도 없다. 발견하면 **첫 mutation 전에 차단하고 사람에게 넘긴다.**

조용히 비활성화하는 길은 두지 않는다. 등록된 게이트가 이행 뒤에 안 도는 상태는, 사용자가
게이트를 켜 둔 줄 알면서 실제로는 꺼져 있는 상태다.
"""

import hashlib
import os

from sage import asset_paths, _resources


def _bundle_hook_files():
    """install 이 hook 트리에 **배치하는** 파일의 상대경로 집합. 이것이 **닫힌 목록**이다.

    디렉터리째 지우지 않는 이유다 — 구 트리에 사용자가 넣은 파일이 있으면 트리 삭제는 그것도
    가져간다. 이름으로 증명되는 것만 지운다.

    `install` 과 **같은 함수**를 본다. 목록이 둘이면 하나만 갱신되는 날이 온다.
    """
    return _resources.installable_hook_relpaths()


# 판정과 같은 질문이므로 `asset_paths` 가 정본이다. 여기에 따로 두면 한쪽만 고쳐지는 날이 온다 —
# 실제로 `--unregister` 의 adapter 제거가 같은 결함을 다시 만들었고, 그때 이 함수는 이 모듈
# 안에만 있었다.
_escapes_root = asset_paths.escapes_root


def _same_bytes(left, right):
    try:
        with open(left, "rb") as a, open(right, "rb") as b:
            return a.read() == b.read()
    except OSError:
        return False


_SCHEMA_FILES = ("manifest.schema.json", "profile.schema.json", "profile.local.schema.json")

# 지원하는 구버전이 배치한 **정확한 바이트**. 이것과 같으면 SAGE 가 배치한 그대로라는 증명이다.
#
# 왜 필요한가 — 이 사이클이 번들 안 `verify-changes.sh` 의 문서 문자열을 신 레이아웃으로 고쳤다.
# 그래서 1.0 이 배치한 원본 그대로인 파일도 현재 번들과 바이트가 다르다. 그대로 두면 손대지 않은
# 파일이 전부 "사용자 수정" 으로 읽히고, `scripts/` 는 어느 프로젝트에서도 정리되지 않는다.
# **우리가 만든 차이를 사용자 탓으로 돌리는 셈이다.**
#
# 처음에는 경로 토큰을 양쪽에서 치환한 뒤 비교했다. 그 방식은 "우리가 바꾼 것" 을 코드가 추론하게
# 하고, 추론이 넓어지는 만큼 소유권 증명이 약해진다. 해시는 추론하지 않는다 — **그 판본이 그
# 바이트를 배치했다는 사실 하나**만 말한다.
#
# 범용 판본 registry 를 만들지 않는다. 지원할 구버전이 하나뿐인데 목록을 일반화하면, 그 일반화가
# 다음에 무엇을 넣어도 되는 자리로 읽힌다.
_LEGACY_COMPAT_SHA256 = {
    # v1.0.0 (tag 433bb82) 이 배치한 `scripts/verify-changes.sh`
    asset_paths.LEGACY_VERIFY_REL: {
        "40cc051c8cf42661f4e0d7ec3bfc7fde97d6bfd202b4bb885ebd9b8e81ff2712",
    },
}


def _sha256(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _ships_as(rel, path, bundled):
    """이 파일이 SAGE 가 배치한 그대로인가.

    현재 번들과 같거나, 지원 구버전이 배치한 바이트와 같으면 참이다. 그 밖에는 **왜** 다른지
    우리가 모른다 — 사용자가 고쳤을 수도 구버전으로 설치했을 수도 있고, 설치 시점 내용을 기록해
    두지 않았으므로 둘을 구별할 방법이 없다.
    """
    if _same_bytes(bundled, path):
        return True
    return _sha256(path) in _LEGACY_COMPAT_SHA256.get(rel, ())


def _legacy_removals(root):
    """(지울 것, 보존할 것). 둘 다 **정확한 상대경로**다. prefix 가 아니다.

    prefix 로 다루면 그 아래 무엇이 새로 생기든 함께 지워진다. 계획을 세운 시점에 본 파일만
    지우는 것이 계약이고, 그래서 목록은 계획 시점에 고정된다.
    """
    remove, preserve = [], []

    # **구 트리로 가는 길에 reparse 성분이 있으면 아무것도 계획하지 않는다.**
    #
    # 계획 단계에서 `escapes_root` blocker 로도 잡히지만, 그건 목록을 **만든 뒤** 거르는 방식이다.
    # 목록을 만드는 순간 walk 가 이미 링크를 따라 프로젝트 밖을 훑는다. 잔재 정리 분기를
    # 추가하면서 실제로 그 길이 다시 열렸다 — 거르는 자리를 늘리는 대신 **들어가지 않는다.**
    if _escapes_root(root, os.path.join(root, asset_paths.LEGACY_SAGE_TREE)):
        return [], []

    hooks_base = os.path.join(root, asset_paths.LEGACY_HOOKS_REL)
    owned = _bundle_hook_files()
    if os.path.isdir(hooks_base):
        for base, _dirs, files in os.walk(hooks_base):
            for name in files:
                path = os.path.join(base, name)
                rel_in_tree = os.path.relpath(path, hooks_base)
                rel = os.path.relpath(path, root)
                if asset_paths.is_reparse(path):
                    preserve.append((rel, "symlink"))
                elif rel_in_tree in owned:
                    remove.append(rel)
                else:
                    preserve.append((rel, "not_sage_asset"))

    # 공유 디렉터리의 낱개 파일은 **번들과 같을 때만** SAGE 소유로 증명된다. 다른 이유는 우리가
    # 모른다 — 사용자가 고쳤을 수도 구버전으로 설치했을 수도 있고, 설치 시점 내용을 기록해 두지
    # 않았으므로 둘을 구별할 방법이 없다. uninstall 이 쓰는 판단과 같은 규칙이다.
    bundle_schema = _resources.schema_dir()
    for name in _SCHEMA_FILES:
        path = os.path.join(root, asset_paths.LEGACY_SCHEMA_REL, name)
        if not os.path.isfile(path) or asset_paths.is_reparse(path):
            continue
        rel = os.path.relpath(path, root)
        if _ships_as(rel, path, os.path.join(bundle_schema, name)):
            remove.append(rel)
        else:
            preserve.append((rel, "content_differs"))

    verify = os.path.join(root, asset_paths.LEGACY_VERIFY_REL)
    if os.path.isfile(verify) and not asset_paths.is_reparse(verify):
        source = os.path.join(_resources.core_dir(), "framework", "scripts", "verify-changes.sh")
        rel = os.path.relpath(verify, root)
        if _ships_as(rel, verify, source):
            remove.append(rel)
        else:
            preserve.append((rel, "content_differs"))

    return sorted(set(remove)), sorted(set(preserve))


def _active_user_extensions(root, manifest):
    """자동 이행을 막는 사용자 확장 자산.

    **옮기지 않는 이유가 안전이 아니라 소유권이다.** 이 코드는 사용자가 썼고, 어느 자리로
    가야 하는지도 사용자가 정한다. 도구가 정하면 다음 사람이 그 자리를 규약으로 읽는다.
    """
    found = []
    assets = (manifest or {}).get("assets") or {}
    legacy_hooks = os.path.join(root, asset_paths.LEGACY_HOOKS_REL)
    for asset_id, entry in sorted(assets.items()):
        if not isinstance(entry, dict) or entry.get("origin") != "project":
            continue
        # **복구 절차가 다르므로 이유를 나눈다.** core 가 멀쩡한 경우는 "새 자리에 다시
        # 만들라" 가 성립하지만, core 가 없거나 링크인 경우는 먼저 그것부터 봐야 한다.
        hook_id = asset_id.split("/")[-1]
        core = os.path.join(legacy_hooks, f"{hook_id.replace('-', '_')}_core.py")
        if asset_paths.is_reparse(core):
            found.append(("project_hook_irregular", asset_id))
        elif not os.path.isfile(core):
            found.append(("project_hook_missing_core", asset_id))
        else:
            found.append(("project_hook", asset_id))
    return found


def _custom_strategy(profile):
    """profile 이 내장 목록 밖의 strategy 를 고르고 있는가."""
    risk = (profile or {}).get("risk") if isinstance(profile, dict) else None
    chosen = risk.get("l3_review_strategy") if isinstance(risk, dict) else None
    if not isinstance(chosen, str) or not chosen:
        return None
    builtin = os.path.join(_resources.hooks_src_dir(), "strategies", "pre_implementation_gate")
    if os.path.isfile(os.path.join(builtin, f"{chosen}.py")):
        return None
    return chosen


def _transition_integrity(root):
    """중단된 이행인가, 아니면 우리가 만들지 않은 신 트리인가.

    공존 상태에서 구 자산을 지우려면 **신 트리가 우리 것이라는 증거**가 있어야 한다. 증거는
    파일 자체다 — 신 트리가 현재 패키지가 배치하는 목록의 부분집합이고 바이트가 같으면, 그것은
    이 도구가 만들다 만 것이다.

    별도 마커를 두지 않는 이유는 마커와 트리가 어긋나는 상태가 새로 생기기 때문이다. 트리를
    보면 마커가 필요 없다.

    모르는 파일이나 다른 바이트가 있으면 **병합하지 않는다.** 그건 사용자가 그 자리에 무언가를
    두었다는 뜻이고, 어느 쪽이 정본인지는 도구가 정할 문제가 아니다.
    """
    source = _resources.hooks_src_dir()
    base = os.path.join(root, asset_paths._HOOKS_REL)
    unexpected = []
    for cursor, _dirs, files in os.walk(base):
        for name in files:
            path = os.path.join(cursor, name)
            rel = os.path.relpath(path, base)
            origin = os.path.join(source, rel)
            if not os.path.isfile(origin):
                unexpected.append(os.path.relpath(path, root))
            elif not _same_bytes(origin, path):
                unexpected.append(os.path.relpath(path, root))
    return unexpected


def current_namespace_occupants(root):
    """SAGE 소유 트리에 **우리 것이 아닌 내용**이 있는가.

    `sage_harness/` 는 "여기 있는 것은 SAGE 가 덮어쓴다" 는 뜻으로 만든 이름이다. 그 안에 사용자
    파일을 허용하면 그 선언이 거짓이 된다 — `uninstall` 은 이 트리를 관리 대상으로 다루므로,
    허용된 사용자 파일이 나중에 함께 지워진다.

    그래서 파일명을 보고 고르지 않는다. **비어 있지 않은 미확인 트리는 전부 차단한다.**
    이름으로 거르면 "겹치지 않으니 괜찮다" 가 성립하는 것처럼 보이고, 그 파일은 uninstall 날에
    사라진다.

    허용은 셋뿐이다 — 없거나 비었을 때, 정상 sentinel 이 있는 현재 레이아웃일 때, 그리고 이
    배포본이 배치한 것으로 증명되는 중단 이행일 때(`_transition_integrity`).
    """
    base = os.path.join(root, asset_paths.SAGE_TREE)
    if asset_paths.is_reparse(base):
        # **이름이 밖을 가리키면 그 자체가 점유다.** 빈 목록을 돌려주면 "아무도 없다" 는 뜻이
        # 되고, 차단 계약은 첫 mutation 전에 막는 것인데 진단이 그 사실을 감춘다. 실제 쓰기는
        # install transaction 이 따로 막았지만, 막힌 이유가 계획에 드러나지 않는 것은 결함이다.
        return [asset_paths.SAGE_TREE]
    if not os.path.isdir(base):
        return []
    found = []
    for cursor, dirs, files in os.walk(base):
        # `__pycache__` 는 **우리 코드를 실행한 부산물**이다. 사용자가 보존을 기대할 내용이
        # 아니고, install 도 배치하지 않는다(`_NOT_INSTALLED_DIRS`).
        #
        # 제외하지 않으면 교착이 생긴다 — 이행이 한 번 실패하면 그 시도가 남긴 캐시 때문에
        # 다음 실행이 영구 차단된다. 스냅샷이 `__pycache__` 를 제외하므로 복원도 지우지 못한다.
        # **우리가 만든 것을 사용자 파일로 읽고 그 때문에 막히는 셈이다.**
        #
        # 예외는 **실제 캐시 모양일 때만**이다. 이름이 `__pycache__` 인 reparse point 는
        # 그 안이 어디인지 모르므로 예외가 아니고, 그 바깥의 `.pyc` 는 사용자가 둔 파일이다.
        # 넓게 열면 이 예외가 그대로 우회로가 된다.
        keep = []
        for name in dirs:
            path = os.path.join(cursor, name)
            if asset_paths.is_reparse(path):
                # 이름이 `__pycache__` 여도 가리키는 곳을 모른다. 내려가지 않고 점유로 센다.
                found.append(os.path.relpath(path, root))
                continue
            keep.append(name)
        dirs[:] = keep
        in_cache = os.path.basename(cursor) == "__pycache__"
        for name in files:
            path = os.path.join(cursor, name)
            if (in_cache and name.endswith(".pyc")
                    and not asset_paths.is_reparse(path) and os.path.isfile(path)):
                continue
            found.append(os.path.relpath(path, root))
    return sorted(found)


def plan(root, manifest=None, profile=None):
    """이행 계획. **mutation 0.** `--check` 와 `--apply` 가 같은 계획을 본다.

    `needed` 가 거짓이면 나머지 필드는 비어 있다. 계획이 비어 있는 것과 이행이 불필요한 것을
    호출부가 구별하지 않아도 되게 한다.
    """
    layout = asset_paths.detect_layout(root)
    in_transition = layout == asset_paths.LAYOUT_CONFLICT
    if layout not in (asset_paths.LAYOUT_CONSUMER_LEGACY, asset_paths.LAYOUT_CONFLICT):
        # **전환은 끝났는데 구 자산이 남은 경우가 있다.** 정리 중 파일 하나를 못 지우면
        # (Windows 에서 잠겨 있는 등) sentinel 은 이미 없으므로 판정은 `consumer` 다. 여기서
        # 멈추면 그 파일은 **영영 남는다** — "다음 실행에서 정리가 완료된다" 는 안내가 거짓이 된다.
        #
        # 남은 것은 전부 sentinel 없는 구 트리의 잔재이므로, 활성 전환 없이 정리만 한다.
        if layout == asset_paths.LAYOUT_CONSUMER_CURRENT:
            leftover, kept = _legacy_removals(root)
            if leftover:
                from sage.uninstall_plan import root_fingerprint
                return {"needed": True, "layout": layout, "in_transition": False,
                        "cleanup_only": True, "remove": leftover, "preserve": kept,
                        "blockers": [(kind, rel) for kind, rel in
                                     (("escapes_root", rel) for rel in leftover
                                      if _escapes_root(root, os.path.join(root, rel)))],
                        "root_mark": root_fingerprint(root),
                        "digests": {rel: _sha256(os.path.join(root, rel)) for rel in leftover}}
        return {"needed": False, "layout": layout, "in_transition": False,
                "cleanup_only": False, "remove": [], "preserve": [], "blockers": []}

    remove, preserve = _legacy_removals(root)
    blockers = []

    # 삭제 계획이 프로젝트 밖에 닿는지 **첫 mutation 전에** 묻는다. 경로 기반 삭제는 조상
    # 하나가 링크면 그대로 밖으로 나간다.
    for rel in remove:
        if _escapes_root(root, os.path.join(root, rel)):
            blockers.append(("escapes_root", rel))

    if layout == asset_paths.LAYOUT_CONSUMER_LEGACY:
        for rel in current_namespace_occupants(root):
            blockers.append(("occupied_current", rel))

    if in_transition:
        # 공존은 이행 중 정상 상태일 수도, 사용자가 만든 별개 트리일 수도 있다. 증거 없이
        # 구 자산을 지우면 후자에서 **사용자 트리를 정본으로 승격**시키는 일이 된다.
        for rel in _transition_integrity(root):
            blockers.append(("unexpected_current", rel))
    blockers += list(_active_user_extensions(root, manifest))
    strategy = _custom_strategy(profile)
    if strategy:
        blockers.append(("custom_strategy", strategy))

    # **계획 시점의 증거를 계획에 싣는다.** apply 가 그때 다시 뜨면, 확인 화면이 열려 있는
    # 동안 사용자가 바꾼 것을 기준으로 지우게 된다. root 신원과 각 대상의 바이트를 함께 고정한다.
    from sage.uninstall_plan import root_fingerprint
    return {"needed": True, "layout": layout, "in_transition": in_transition,
            "cleanup_only": False,
            "remove": remove, "preserve": preserve, "blockers": blockers,
            "root_mark": root_fingerprint(root) if not blockers else None,
            "digests": {rel: _sha256(os.path.join(root, rel)) for rel in remove}
                       if not blockers else {}}


def empty_legacy_dirs(root):
    """이행 뒤 비어 있는 구 디렉터리. **지우지 않고 보고만 한다.**

    재귀 삭제로 정리하면 그 재귀가 링크를 만날 수 있고, 빈 디렉터리 하나를 치우려고 그 위험을
    지는 것은 값이 맞지 않는다. handle 결속 `rmdir_empty` seam 이 생기기 전까지는 남긴다 —
    남은 빈 폴더는 눈에 거슬릴 뿐 아무것도 깨뜨리지 않는다.

    **`apply()` 밖에 있다.** 한때 이 조회가 `apply()` 의 반환값을 만드는 마지막 단계였고,
    거기서 오른 예외가 호출부에 `migration_not_activated` 로 읽혔다 — 구 sentinel 은 이미
    지워진 뒤라 **전환이 끝났는데 끝나지 않았다고 보고**했다.

    원인은 예외를 안 잡은 것이 아니라 **실패해도 되는 코드가 실패하면 안 되는 코드의 반환
    경로에 있었던 것**이다. 그래서 호출부가 활성 전환 성공을 확정한 뒤에 따로 묻는다.
    여기서도 읽을 수 없는 경로는 건너뛴다 — 한 경로 때문에 나머지 안내까지 잃지 않는다.
    """
    found = []
    for rel in (asset_paths.LEGACY_HOOKS_REL, asset_paths.LEGACY_SAGE_TREE) + asset_paths.LEGACY_PARENTS:
        path = os.path.join(root, rel)
        try:
            if os.path.isdir(path) and not asset_paths.is_reparse(path) and not os.listdir(path):
                found.append(rel)
        except OSError:
            continue
    return found


def runtime_loads(root):
    """신 경로의 hook 런타임이 **엔진 없이 로드되는가.** 게이트는 돌리지 않는다.

    `validate` 는 해시와 스키마를 본다. 그것으로는 "이 트리로 hook 이 실제로 설 수 있는가" 를
    말하지 못한다 — 그런데 그 확인 없이 구 자산을 지우면 되돌아갈 자리가 사라진다.

    **판정을 실행하지는 않는다.** 프로젝트의 실제 정책이 돌면 차단이 나올 수 있고, 차단은
    정상 결과다. 그것을 이행 실패로 읽으면 게이트가 엄격한 프로젝트일수록 이행이 막힌다.
    감사 기록이 남는 것도 이행의 부작용으로는 옳지 않다.

    그래서 **로드와 dispatch 진입점의 존재까지만** 본다. 엔진을 가린 상태로 별도 프로세스에서
    확인한다 — 이 프로세스는 엔진이 import 돼 있어서, 여기서 import 하면 부재를 검사한다고
    주장하면서 실제로는 존재를 검사한다.
    """
    import subprocess
    import sys
    import tempfile

    core = os.path.join(root, asset_paths._HOOKS_REL)

    probe = (
        "import importlib.util, os, sys\n"
        "core = sys.argv[1]\n"
        "sys.path.insert(0, os.path.join(core, 'runtime'))\n"
        "sys.path.insert(0, core)\n"
        "spec = importlib.util.spec_from_file_location("
        "'probe_run_hook', os.path.join(core, 'runtime', 'run_hook.py'))\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "assert callable(getattr(module, 'dispatch', None)), 'dispatch missing'\n"
    )
    # stub 은 **실행마다 새로 만든다.** 고정 이름을 공유 temp 에 두면 그 이름을 남이 먼저
    # 만들어 둘 수 있고, 그 안의 `sage/` 가 프로젝트 밖을 가리키면 우리가 그리로 파일을 쓴다 —
    # 검사 하나가 남의 파일을 덮는 통로가 된다. 이름을 매번 바꾸면 선점할 대상이 없다.
    with tempfile.TemporaryDirectory(prefix="sage-migration-engine-absent-") as stub:
        package = os.path.join(stub, "sage")
        os.mkdir(package)
        with open(os.path.join(package, "__init__.py"), "w", encoding="utf-8") as handle:
            handle.write("raise ModuleNotFoundError(\"No module named 'sage'\")\n")

        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        env["PYTHONPATH"] = stub
        # **cwd 가 중요하다.** `-c` 는 현재 디렉터리를 `sys.path` 맨 앞에 넣는다. 엔진 저장소에서
        # 돌리면 `PYTHONPATH` 의 stub 을 보기도 전에 그 저장소의 `sage/` 가 이긴다 — 부재를
        # 검사한다고 주장하면서 실제로는 존재를 검사하게 된다.
        done = subprocess.run([sys.executable, "-c", probe, core], capture_output=True,
                              text=True, env=env, cwd=stub)
    return done.returncode == 0, (done.stderr or "").strip().splitlines()[-1:] or [""]


def apply(root, migration):
    """계획대로 구 자산을 지우고 활성 경로를 전환한다.

    **신 경로가 검증된 뒤에만 불린다.** 이 함수가 도는 시점에 신 트리는 이미 배치·재생성·검증을
    마쳤고, 남은 일은 구 sentinel 을 없애 정본을 넘기는 것뿐이다.

    계획은 **밖에서 받는다.** 여기서 다시 계산하면 `--check` 가 보여준 것과 실제로 지우는 것이
    갈릴 수 있다 — 사용자가 승인한 목록이 아닌 것을 지우게 된다.

    ## 왜 `os.unlink` 가 아니라 backend 인가

    첫 구현은 경로로 지웠다. 구 트리의 **조상 하나를 프로젝트 밖으로 향하는 symlink 로 바꾸면
    바깥 파일이 실제로 지워졌다.** 이 저장소가 부모 핸들 backend 를 따로 만든 이유가 그대로
    적용된다 — 검사와 변경 사이에 상위 디렉터리가 바뀌는 창을 경로는 막지 못한다.

    부모 결속을 얻을 수 없는 환경에서는 **아무것도 지우지 않는다.** 되돌릴 수 없는 쪽으로
    틀리는 동작이라 "알려진 한계" 로 넘길 성질이 아니다.

    `(활성화됐는가, 지운 것, 남은 것)` 을 돌려준다. **부가 진단은 섞지 않는다** — 실패해도
    되는 조회가 이 반환 경로에 있으면 그 실패가 이행 실패로 읽힌다. 빈 부모 안내는
    `empty_legacy_dirs()` 가 따로 답한다.
    """
    from sage import uninstall_fs as _fs
    from sage.uninstall_plan import root_fingerprint

    # sentinel 을 **가장 먼저** 지운다. 그 파일이 사라지는 순간이 활성 전환점이고, 그 시점에
    # 신 트리는 이미 배치·재생성·검증을 마쳤다.
    #
    # 순서를 뒤집으면 — 구 트리가 아직 활성인 채로 그 안의 파일이 하나씩 사라진다. 정리 도중에
    # hook 이 뜨면 **반쪽 남은 구 트리 위에서** 게이트가 돈다.
    sentinel_rel = os.path.join(asset_paths.LEGACY_HOOKS_REL, asset_paths.SENTINEL_REL)
    rest = [rel for rel in migration["remove"] if rel != sentinel_rel]
    # 정리 전용 실행에는 sentinel 이 없다 — 전환은 이미 끝났고 잔재만 남았다.
    has_sentinel = sentinel_rel in migration["remove"]

    backend = _fs.backend_for([root])
    removed, leftover = [], []
    digests = migration.get("digests") or {}
    try:
        # 계획 때 본 그 디렉터리인가. 여기서 다시 뜨면 대조가 아니라 **현재 상태 확인**이 되고,
        # root 가 통째로 바뀐 경우를 잡지 못한다 — 상대 경로는 새 root 안에서도 성립한다.
        mark = migration.get("root_mark")
        backend.open_roots({root: mark if mark is not None else root_fingerprint(root)})

        def drop(rel):
            path = os.path.join(root, rel)
            if not os.path.lexists(path):
                return True               # 이미 지워졌다 — 재실행이 이어받는 경우다
            # **결속한 뒤 대조한다.** 순서가 뒤집히면 대조는 경로로 열고 삭제는 handle 로 하는
            # 셈이고, 그 사이가 그대로 경쟁 구간이다 — 우리가 읽어 증명한 바이트와 실제로
            # 지우는 대상이 다른 파일일 수 있다.
            #
            # 계획 뒤에 내용이 바뀐 파일은 우리가 증명한 그 파일이 아니다. backend 를 쓴다고
            # uninstall 의 안전 계약 전체가 따라오지는 않는다.
            backend.pin(root, path)
            expected = digests.get(rel)
            if expected is not None:
                digest = hashlib.sha256(backend.read_bytes(path)).hexdigest()
                if digest != expected:
                    raise ValueError(f"migration.target_changed:{rel}")
            backend.remove_tree(path)
            removed.append(rel)
            return True

        if has_sentinel:
            try:
                drop(sentinel_rel)
            except (OSError, ValueError, _fs.MutationBackendError):
                # **활성 전환에 실패하면 하나도 더 지우지 않는다.** 계속 지우면 구 트리가
                # 아직 정본인 채로 반쪽이 되고, 그 위에서 게이트가 돈다.
                return False, removed, [sentinel_rel]

        for rel in rest:
            try:
                drop(rel)
            except (OSError, ValueError, _fs.MutationBackendError):
                leftover.append(rel)
    finally:
        backend.close()

    return True, removed, leftover
