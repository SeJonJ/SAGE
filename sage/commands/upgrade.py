"""sage upgrade — 설치본을 현재 엔진에 맞추는 읽기 전용 진단과 트랜잭션 적용.

이 명령이 다른 명령과 다른 점은 **version 이 어긋난 상태에서도 반드시 불릴 수 있어야 한다**는
것이다. 버전 불일치를 고치는 유일한 통로가 버전 불일치 때문에 막히면 사용자는 빠져나갈 방법이
없다. 그래서 여기서는 부트스트랩 게이트도, profile 검증 실패도 실행 자체를 막지 않는다 —
읽을 수 있는 만큼 읽고 못 읽은 축은 `unknown` 으로 보고한다.

upgrade 는 **소비 프로젝트를 현재 엔진 상태로 끌어올린다.** 신규 managed CORE 자산 배포,
manifest·receipt 갱신, hook 재생성, overlay 재적용, 전체 검증까지가 한 단위다. 선언 값만 고치면
사용자는 "upgrade 했다"고 믿는데 새 CORE 파일은 없는 상태로 남는다 — 그 상태가 조용히 통과하는
것이 이 명령의 가장 위험한 실패다.

**각 단계의 바이트는 원래 주인이 만든다.** CORE 배포는 `install`, hook 산출물은 `generate`,
overlay 물리화는 `sync-overlays` 가 소유한다. upgrade 는 그것들을 **순서대로 부르고 하나의
트랜잭션으로 감싼다** — 여기서 배치 로직을 다시 구현하면 같은 바이트의 주인이 둘이 되고,
그 뒤로는 drift 의 원인을 아무도 역추적할 수 없다.

upgrade 자신이 직접 쓰는 것은 선언 값 둘뿐이다:

  · `sage/project-profile.yaml` 의 `sage.required_version` scalar 한 개
  · `.sage/cycle.json` 의 schema 1 → 2 미러 이행

local profile·policy·overlay 원본·authored asset·plan/evidence/audit/vault·프로젝트 코드·검증
스크립트는 **어느 단계에서도 write target 이 아니다.**

**실패하면 일괄 되돌린다.** 각 단계가 자기 트랜잭션을 갖고 있어도 단계 사이에서 실패하면 앞
단계는 이미 커밋돼 있다. 그래서 upgrade 는 시작 전에 프로젝트 트리 전체를 스냅샷하고, 어느
단계에서 실패하든 그 스냅샷으로 복원한다 — 부분 적용 상태는 사용자가 무엇을 믿어야 할지 알 수
없게 만든다.

`--force` 는 "남의 파일을 덮어라"가 아니라 **"내가 소유하지 않은 drift 가 있어도 진행하라"**다.

자동 downgrade 는 없다. 되돌리려면 apply 가 남긴 backup 으로 복구한다(보고서에 경로가 있다).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid

from sage.i18n import exception_text, language_of, render_issue, tr

# 이 값만 바꾼다. 공유 YAML 전체를 재직렬화하면 주석·순서·따옴표 스타일이 통째로 바뀌어
# 사용자가 upgrade 한 번에 자기 파일이 다시 쓰였다고 읽는다 — diff 가 계약을 넘어선다.
_REQUIRED_VERSION_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<key>required_version[ \t]*:[ \t]*)"
    r"(?P<quote>[\"']?)(?P<value>[^\"'\n#]*)(?P<close>[\"']?)(?P<trail>[ \t]*(?:#.*)?)$",
    re.M,
)
_SAGE_SECTION_RE = re.compile(r"^sage[ \t]*:[ \t]*(?:#.*)?$", re.M)

REPORT_REL = os.path.join(".sage", "upgrades")

EXIT_OK = 0
EXIT_BLOCKED = 1        # blocker 가 있거나, apply 가 실패했지만 rollback 은 완료됨
EXIT_UNSAFE = 2         # usage·손상·내부 안전 실패·rollback 불완전


def _exception_text(language, exc):
    """`sage.i18n.exception_text` 의 이 모듈용 이름. 문장 조립 규칙은 한 곳에만 둔다."""
    return exception_text(language, exc)


def register(sub, context):
    parser = sub.add_parser("upgrade", help=tr(context, "cli.upgrade.upgrade"))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help=tr(context, "cli.upgrade.check"))
    mode.add_argument("--apply", action="store_true", help=tr(context, "cli.upgrade.apply"))
    parser.add_argument("--root", default=None, help=tr(context, "cli.upgrade.root"))
    parser.add_argument("--force", action="store_true", help=tr(context, "cli.upgrade.force"))
    parser.set_defaults(func=run)


# --- 읽기 -------------------------------------------------------------------

def _find_root(explicit):
    """소비 프로젝트 root. 못 찾으면 None — 추측해서 남의 디렉터리를 고치지 않는다."""
    if explicit:
        return os.path.abspath(explicit)
    cursor = os.path.abspath(os.getcwd())
    while True:
        if os.path.isfile(os.path.join(cursor, "docs", "sage_harness", ".manifest.json")):
            return cursor
        parent = os.path.dirname(cursor)
        if parent == cursor:
            return None
        cursor = parent


def _read_json(path):
    """(data, error). 손상과 부재를 갈라서 돌려준다 — 둘이 같으면 손상이 조용히 통과한다."""
    if not os.path.isfile(path):
        return None, ""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle), ""
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}"


def _read_profile(root):
    """(profile, raw_text, error). pyyaml 이 없어도 upgrade 는 서야 한다."""
    path = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.isfile(path):
        return None, "", ""
    try:
        with open(path, encoding="utf-8") as handle:
            raw = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        return None, "", f"{type(exc).__name__}"
    try:
        import yaml
    except ImportError:
        return None, raw, "no_yaml"
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:
        return None, raw, f"{type(exc).__name__}"
    return (data if isinstance(data, dict) else None), raw, ("" if isinstance(data, dict) else "not_mapping")


# --- 판정 -------------------------------------------------------------------

def _plan(root, language):
    """읽기 전용 판정. (plan, blockers) — plan 은 apply 가 그대로 쓰는 선언 write set 이다."""
    from sage import __version__
    from sage.version_contract import UNKNOWN, version_axes

    manifest, manifest_error = _read_json(os.path.join(root, "docs", "sage_harness", ".manifest.json"))
    profile, profile_raw, profile_error = _read_profile(root)
    axes = version_axes(profile, manifest, __version__)

    blockers, notes, writes = [], [], []

    if manifest_error:
        blockers.append(tr(language, "cli.upgrade.blocker_manifest", error=manifest_error))
    elif manifest is None:
        blockers.append(tr(language, "cli.upgrade.blocker_no_manifest"))
    if profile_error == "no_yaml":
        blockers.append(tr(language, "cli.upgrade.blocker_no_yaml"))
    elif profile_error:
        blockers.append(tr(language, "cli.upgrade.blocker_profile", error=profile_error))

    # required_version scalar. 없으면 upgrade 가 만들지 않는다 — `sage` section 자체가 없는
    # profile 은 부트스트랩 이전 상태이고, 그건 install/init 이 소유한다.
    if profile_raw and not profile_error:
        current = axes.required
        if current == UNKNOWN:
            notes.append(tr(language, "cli.upgrade.note_no_required_version"))
        elif current != __version__:
            occurrences = _required_version_sites(profile_raw)
            if len(occurrences) != 1:
                blockers.append(tr(language, "cli.upgrade.blocker_required_version_sites",
                                   count=len(occurrences)))
            else:
                writes.append({"kind": "required_version",
                               "path": os.path.join("sage", "project-profile.yaml"),
                               "from": current, "to": __version__})

    # cycle 선언 schema 1 → 2. 미러가 낡으면 문서 언어 게이트가 legacy 로만 읽는다.
    migration = _cycle_migration(root)
    if migration is not None:
        writes.append(migration)

    # upgrade 가 소유하지 않는 drift. 정상 apply 를 막고, --force 는 "그래도 내 write set 은
    # 진행하라"는 뜻이지 이걸 덮으라는 뜻이 아니다.
    unowned = _unowned_drift(axes, __version__, language)

    # 위임 단계에 넘길 설치 형태. **추측하지 않는다** — scope 를 잘못 고르면 CORE skill 이
    # 사용자가 고르지 않은 자리에 깔리고, 그건 upgrade 가 만든 새 drift 다.
    receipts = (manifest or {}).get("core_skill_receipts")
    host = (manifest or {}).get("host_runtime") or UNKNOWN
    scope = None
    if isinstance(receipts, dict) and isinstance(receipts.get(host), dict):
        scope = receipts[host].get("scope")
    if host == "codex" and scope not in ("global", "project-local", "disabled"):
        blockers.append(tr(language, "cli.upgrade.blocker_no_scope_receipt"))

    project = (profile or {}).get("project") if isinstance(profile, dict) else None
    prefix = project.get("prefix") if isinstance(project, dict) else None

    # 부트스트랩 미완이면 CORE 배포가 의미를 갖지 못한다(risk glob 0 → 게이트 무력). 그렇다고
    # upgrade 자체를 막으면 버전 불일치의 탈출 통로가 사라지므로(FR-U03), 선언 값만 맞추고
    # 무엇을 건너뛰었는지 화면에 남긴다.
    from sage.commands._common import is_bootstrapped
    bootstrapped = bool(profile) and is_bootstrapped(profile)
    if profile_raw and not profile_error and not bootstrapped:
        # **성공으로 끝내지 않는다.** CORE 배포를 건너뛰고 exit 0 을 내면 사용자는 업그레이드가
        # 됐다고 믿는데 새 자산은 없다 — 이 명령에서 가장 위험한 실패다. 명령은 여전히 서고
        # (FR-U03) 무엇이 왜 안 됐는지 말하되, 상태는 blocker 다.
        blockers.append(tr(language, "cli.upgrade.blocker_unbootstrapped"))

    return {
        "axes": {"required": axes.required, "installed": axes.installed,
                 "generated": axes.generated, "runtime": axes.runtime},
        "host_runtime": host,
        "bootstrapped": bootstrapped,
        "skill_scope": scope,
        "prefix": prefix if isinstance(prefix, str) and prefix else None,
        "writes": writes,
        "unowned_drift": unowned,
        "notes": notes,
    }, blockers


def _required_version_sites(raw):
    """`sage:` 아래의 required_version 위치. 다른 section 의 동명 키를 고치지 않기 위해 센다."""
    section = _SAGE_SECTION_RE.search(raw)
    if section is None:
        return []
    tail = raw[section.end():]
    # 다음 최상위 key 까지가 `sage:` block 이다.
    end = re.search(r"^\S", tail, re.M)
    block = tail[:end.start()] if end else tail
    return [(section.end() + m.start(), section.end() + m.end(), m)
            for m in _REQUIRED_VERSION_RE.finditer(block)]


def _cycle_migration(root):
    """schema 1 선언이 있으면 v2 이행을 write set 에 넣는다. 없거나 이미 v2 면 None."""
    path = os.path.join(root, ".sage", "cycle.json")
    data, error = _read_json(path)
    if error or not isinstance(data, dict):
        return None
    if data.get("version") == 2 and data.get("document_language") in ("ko", "en"):
        return None
    stem = data.get("cycle_stem")
    if not isinstance(stem, str) or not stem:
        return None
    # 언어를 지어내지 않는다. marker 이전 사이클은 한국어로 시작했고(호환 기본값), 그걸
    # 명시로 적어 두는 것이 이행이다 — 비워 두면 다음 upgrade 가 같은 일을 다시 한다.
    return {"kind": "cycle_schema", "path": os.path.join(".sage", "cycle.json"),
            "from": str(data.get("version")), "to": "2", "document_language": "ko",
            "cycle_stem": stem}


def _unowned_drift(axes, runtime, language):
    """upgrade 가 바이트를 소유하지 않는 축. 각 항목은 어느 명령이 주인인지 함께 말한다."""
    from sage.version_contract import UNKNOWN
    items = []
    if axes.installed != UNKNOWN and axes.installed != runtime:
        items.append({"axis": "installed", "current": axes.installed, "expected": runtime,
                      "owner": "sage install --force",
                      "detail": tr(language, "cli.upgrade.drift_installed")})
    if axes.generated != UNKNOWN and axes.generated != runtime:
        items.append({"axis": "generated", "current": axes.generated, "expected": runtime,
                      "owner": "sage generate --kind hook --write",
                      "detail": tr(language, "cli.upgrade.drift_generated")})
    return items


# --- 보고 -------------------------------------------------------------------

def _write_report(root, payload):
    """`.sage/upgrades/<run-id>.json`. 절대 경로·secret·local 언어 값을 담지 않는다.

    보고서는 사용자가 붙여 넣어 공유하는 물건이다. 절대 경로 하나가 사용자 이름과 디렉터리
    구조를 노출하므로 root 상대 경로만 남긴다.
    """
    directory = os.path.join(root, REPORT_REL)
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{payload['run_id']}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        return os.path.relpath(path, root), ""
    except OSError as exc:
        return "", f"{type(exc).__name__}"


def _print_report(plan, blockers, language, applied):
    print(tr(language, "cli.upgrade.header"))
    axes = plan["axes"]
    print(tr(language, "cli.upgrade.axes", runtime=axes["runtime"], required=axes["required"],
             installed=axes["installed"], generated=axes["generated"]))
    print(tr(language, "cli.upgrade.host", host=plan["host_runtime"]))
    for note in plan["notes"]:
        print(note)
    if plan["writes"]:
        print(tr(language, "cli.upgrade.writes_header", count=len(plan["writes"])))
        for item in plan["writes"]:
            print(tr(language, "cli.upgrade.write_item", path=item["path"],
                     from_=item["from"], to=item["to"]))
    else:
        print(tr(language, "cli.upgrade.no_writes"))
    for item in plan["unowned_drift"]:
        print(tr(language, "cli.upgrade.unowned", axis=item["axis"], current=item["current"],
                 expected=item["expected"], owner=item["owner"]))
    for blocker in blockers:
        print(blocker, file=sys.stderr)
    if applied:
        print(tr(language, "cli.upgrade.applied", count=applied))


# --- 전체 트랜잭션 -----------------------------------------------------------

# 스냅샷에서 뺄 것. `.git` 은 크고 upgrade 가 건드리지 않는다. 나머지는 재생성 가능한 캐시다.
_SNAPSHOT_SKIP = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}


def _snapshot_tree(root):
    """(경로 → (mode, bytes)). 단계 사이 실패에서 되돌릴 유일한 근거다.

    각 단계(install·generate·sync-overlays)는 자기 트랜잭션을 갖지만, **단계와 단계 사이**에서
    실패하면 앞 단계는 이미 커밋돼 있다. 부분 적용 상태는 사용자가 무엇을 믿어야 할지 알 수
    없게 만들므로, 전체를 한 단위로 되돌린다.
    """
    captured = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SNAPSHOT_SKIP]
        for name in files:
            path = os.path.join(base, name)
            try:
                if os.path.islink(path):
                    continue          # 심링크는 대상이 바깥일 수 있어 되돌리기 대상이 아니다
                with open(path, "rb") as handle:
                    captured[os.path.relpath(path, root)] = (
                        os.stat(path).st_mode & 0o777, handle.read())
            except OSError:
                continue
    return captured


def _restore_tree(root, captured, language=None):
    """스냅샷 상태로 되돌린다. (복원 성공 여부, 남은 문제)."""
    problems = []
    current = _snapshot_tree(root)
    for rel in sorted(set(current) - set(captured)):
        try:
            os.unlink(os.path.join(root, rel))
        except OSError as exc:
            problems.append(tr(language, "cli.upgrade.delete_failed",
                               rel=rel, exc_type=type(exc).__name__))
    for rel, (mode, body) in sorted(captured.items()):
        if current.get(rel) == (mode, body):
            continue
        path = os.path.join(root, rel)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(body)
            os.chmod(path, mode)
        except OSError as exc:
            problems.append(tr(language, "cli.upgrade.restore_failed",
                               rel=rel, exc_type=type(exc).__name__))
    return (not problems), problems


# --- 적용 -------------------------------------------------------------------

def _apply_required_version(raw, item):
    """scalar 한 개만 바꾼 새 본문. 따옴표 스타일과 주석을 보존한다."""
    sites = _required_version_sites(raw)
    if len(sites) != 1:
        return None
    start, end, match = sites[0]
    replacement = (f"{match.group('indent')}{match.group('key')}"
                   f"{match.group('quote')}{item['to']}{match.group('close')}"
                   f"{match.group('trail')}")
    return raw[:start] + replacement + raw[end:]


class _StepArgs:
    """위임 대상 명령이 기대하는 최소 인자 묶음."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def _managed_steps(root, plan, language):
    """위임할 단계들. 각 단계는 (이름, 호출) 이며 바이트의 주인은 그 명령이다.

    upgrade 는 순서와 트랜잭션만 소유한다 — 배치 로직을 여기서 다시 구현하면 같은 바이트의
    주인이 둘이 되고, 그 뒤로는 drift 의 원인을 역추적할 수 없다.
    """
    host = plan["host_runtime"]
    scope = plan.get("skill_scope")
    steps = []

    def install_core():
        from sage.commands import install
        # `--skill-scope` 는 codex 전용이다. claude 에 넘기면 install 이 usage 오류로 끝나고,
        # upgrade 는 "CORE 배포 실패" 로 읽어 전체를 되돌린다 — 원인이 두 단계 떨어져 보인다.
        args = _StepArgs(host=host, dest=root, prefix=plan.get("prefix") or "sage",
                         force=True, no_global_skill=False,
                         skill_scope=(scope if host == "codex" else None))
        return install.run(args)

    def regenerate_hooks():
        from sage.commands import generate
        args = _StepArgs(kind="hook", id=None, write=True, target="both",
                         dest=root, root=root, deploy_codex=False)
        return generate.run(args)

    def rematerialize_overlays():
        from sage.commands import sync_overlays
        return sync_overlays.run(_StepArgs(root=root))

    def validate_all():
        from sage.commands import validate
        return validate.run(_StepArgs(check=False, schema=True, strict=False,
                                      kind="all", id=None, root=root))

    if host in ("claude", "codex") and plan.get("bootstrapped"):
        steps.append(("core-assets", install_core))
        steps.append(("hooks", regenerate_hooks))
        steps.append(("overlays", rematerialize_overlays))
        steps.append(("validate", validate_all))
    return steps


# FR-U05 보호 집합. **위임 단계가 이걸 건드려도 upgrade 는 되돌린다.**
#
# `install --force` 는 profile 이 선언하지 않은 `verify-changes.sh` 를 자기 자산으로 보고 덮는다.
# install 단독 실행에서는 사용자가 `--force` 를 직접 친 것이라 그 계약이 성립하지만, upgrade 는
# 사용자가 "버전을 맞춰라" 라고 한 것이지 "내 검증 스크립트를 버려라" 라고 한 것이 아니다.
# 위임한다고 해서 위임처의 계약이 이쪽 계약을 덮어쓰지는 않는다.
_USER_OWNED_PREFIXES = (
    os.path.join("sage", "project-profile.local.yaml"),
    os.path.join("sage", "asset_overrides") + os.sep,
    "plan_docs" + os.sep,
    os.path.join(".sage", "override.jsonl"),
    os.path.join(".sage", "acceptance-waivers.jsonl"),
    os.path.join(".sage", "loop_audit.jsonl"),
    os.path.join(".sage", "retro_audit.jsonl"),
    os.path.join(".sage", "fast_cycle.jsonl"),
    os.path.join("scripts", "verify-changes.sh"),
)


def _is_user_owned(rel):
    normalized = rel.replace("/", os.sep)
    return any(normalized == prefix or normalized.startswith(prefix)
               for prefix in _USER_OWNED_PREFIXES)


def _capture_times(root, snapshot):
    """사용자 소유 경로의 mtime. 복원이 흔적을 남기면 그것도 사용자 파일을 건드린 것이다."""
    times = {}
    for rel in snapshot:
        if not _is_user_owned(rel):
            continue
        try:
            stat_result = os.stat(os.path.join(root, rel))
            times[rel] = (stat_result.st_atime_ns, stat_result.st_mtime_ns)
        except OSError:
            continue
    return times


def _restore_user_owned(root, snapshot, times=None):
    """위임 단계가 건드린 사용자 소유 경로를 원래대로 되돌린다. 되돌린 경로 목록을 준다."""
    reverted = []
    current = _snapshot_tree(root)
    for rel in sorted(set(snapshot) | set(current)):
        if not _is_user_owned(rel):
            continue
        was, now = snapshot.get(rel), current.get(rel)
        if was == now:
            continue
        path = os.path.join(root, rel)
        if was is None:
            try:
                os.unlink(path)
                reverted.append(rel)
            except OSError:
                pass
            continue
        mode, body = was
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(body)
        os.chmod(path, mode)
        stamp = (times or {}).get(rel)
        if stamp:
            try:
                os.utime(path, ns=stamp)
            except OSError:
                pass
        reverted.append(rel)
    return reverted


# 각 단계가 성공으로 인정하는 exit code. validate 의 STALE(3) 은 여기서 실패다 — upgrade 가
# 끝난 뒤에도 STALE 이면 그건 hook 재생성이 제 일을 못 했다는 뜻이다.
_STEP_OK = {"core-assets": {0}, "hooks": {0}, "overlays": {0}, "validate": {0}}


def _apply(root, plan, language):
    """(applied_count, error, rollback_complete).

    선언 write 와 위임 단계를 **하나의 단위**로 다룬다. 단계 사이에서 실패하면 앞 단계는 이미
    자기 트랜잭션을 커밋했으므로, 시작 전 스냅샷으로 전체를 되돌리는 것이 유일한 방법이다.
    """
    from sage.install_transaction import DestinationLock, InstallBusyError

    # **install 과 같은 lock 을 쥐면 안 된다.** upgrade 는 install 을 위임 단계로 부르는데,
    # 같은 destination lock 을 이미 들고 있으면 그 단계가 "다른 install 이 실행 중" 으로 실패한다.
    # 그래서 upgrade 는 `.sage` 를 identity 로 하는 별도 lock 을 쥔다 — upgrade 끼리는 상호
    # 배타이고, 각 단계는 자기 lock 을 정상적으로 얻는다.
    upgrade_lock_root = os.path.join(root, ".sage")
    os.makedirs(upgrade_lock_root, exist_ok=True)
    try:
        lock = DestinationLock(upgrade_lock_root)
    except InstallBusyError as exc:
        return 0, tr(language, "cli.upgrade.lock_failed",
                     error=_exception_text(language, exc)), True

    lock.acquire()
    snapshot = _snapshot_tree(root)
    user_times = _capture_times(root, snapshot)
    applied = 0
    try:
        # required_version 을 쓰면 뒤이은 core-assets 단계가 project-profile.json 도 같은
        # 값으로 요구한다. 이미 어긋난 pair 를 upgrade 가 조용히 덮어 고치면 사용자가 만든(또는
        # 다른 도구가 남긴) drift 가 사라진다 — 그건 upgrade 의 write target 이 아니므로, 쓰기
        # 시작 전에 기존 pair 부터 fail-closed 로 검증한다.
        needs_profile_refresh = any(item["kind"] == "required_version" for item in plan["writes"])
        if needs_profile_refresh:
            from sage import overlay_materialize
            _existing_profile, profile_issue = overlay_materialize.load_profile(root)
            if profile_issue is not None:
                raise RuntimeError(render_issue(language, profile_issue))
        for item in plan["writes"]:
            _write_declaration(root, item, language)
            applied += 1
        if needs_profile_refresh:
            _refresh_compiled_profile_json(root, language)
        for name, run_step in _managed_steps(root, plan, language):
            code = run_step()
            if code not in _STEP_OK[name]:
                raise RuntimeError(tr(language, "cli.upgrade.step_exit_nonzero", name=name, code=code))
            applied += 1
        reverted = _restore_user_owned(root, snapshot, user_times)
        for rel in reverted:
            print(tr(language, "cli.upgrade.user_owned_restored", path=rel))
        return applied, "", True
    except BaseException as exc:
        restored, problems = _restore_tree(root, snapshot, language)
        detail = f"{type(exc).__name__}: {exc}"
        if not restored:
            return 0, tr(language, "cli.upgrade.rollback_failed",
                         error=detail, rollback="; ".join(problems[:3])), False
        return 0, tr(language, "cli.upgrade.apply_failed", error=detail), True
    finally:
        lock.release()


def _refresh_compiled_profile_json(root, language):
    """required_version write 직후 compiled `project-profile.json` 을 같은 값으로 재동기화한다.

    yaml 의 required_version 만 바뀐 순간 json 은 아직 이전 값이다 — 그 갭에서 위임 단계
    `core-assets`(`install --force`)가 내부에서 부르는 `overlay_materialize.load_profile` 의
    yaml/json 일치 검사가 막힌다. json 본문은 `generate` 가 소유하므로, 여기서는 그 컴파일
    규칙(`generate._compile_profile`)을 그대로 불러 다시 만들 뿐 직렬화를 복제하지 않는다.
    """
    json_path = os.path.join(root, "sage", "project-profile.json")
    if not os.path.isfile(json_path):
        # generate 가 아직 만든 적 없는 profile 이면 upgrade 가 새로 만들지 않는다 — install
        # 은 yaml 단독으로도 읽을 수 있고, 뒤이은 hooks 단계(generate)가 json 을 만든다.
        return
    from sage.commands.generate import _compile_profile
    status, _data, body, output_path = _compile_profile(root, root, language)
    if status != "ok":
        raise RuntimeError(tr(language, "cli.upgrade.profile_json_refresh_failed", status=status))
    if os.path.abspath(output_path) != os.path.abspath(json_path):
        raise RuntimeError(tr(language, "cli.upgrade.profile_json_unexpected_path", path=output_path))
    mode = os.stat(json_path).st_mode & 0o777
    with open(json_path, "wb") as handle:
        handle.write(body.encode("utf-8"))
    os.chmod(json_path, mode)


def _write_declaration(root, item, language=None):
    """upgrade 가 직접 소유하는 두 선언 값. 나머지 바이트는 위임 단계가 만든다."""
    absolute = os.path.join(root, item["path"])
    if item["kind"] == "required_version":
        with open(absolute, encoding="utf-8") as handle:
            raw = handle.read()
        updated = _apply_required_version(raw, item)
        if updated is None:
            raise RuntimeError(tr(language, "cli.upgrade.required_version_position_changed"))
        body = updated.encode("utf-8")
    elif item["kind"] == "cycle_schema":
        body = (json.dumps({"version": 2, "cycle_stem": item["cycle_stem"],
                            "document_language": item["document_language"],
                            "declared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                           ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    else:
        raise RuntimeError(tr(language, "cli.upgrade.unknown_write_kind", kind=item["kind"]))
    mode = os.stat(absolute).st_mode & 0o777
    with open(absolute, "wb") as handle:
        handle.write(body)
    os.chmod(absolute, mode)


# --- 진입점 -----------------------------------------------------------------

def run(args):
    language = language_of(args)
    root = _find_root(args.root)
    if root is None:
        print(tr(language, "cli.upgrade.no_root"), file=sys.stderr)
        return EXIT_UNSAFE
    if args.force and not args.apply:
        print(tr(language, "cli.upgrade.force_requires_apply"), file=sys.stderr)
        return EXIT_UNSAFE

    plan, blockers = _plan(root, language)
    applied, apply_error, rollback_complete = 0, "", True

    if args.apply:
        if blockers:
            _print_report(plan, blockers, language, 0)
            print(tr(language, "cli.upgrade.blocked_no_mutation"), file=sys.stderr)
            _finish_report(root, plan, blockers, language, applied=0, mode="apply",
                           outcome="blocked")
            return EXIT_BLOCKED
        if plan["unowned_drift"] and not args.force:
            _print_report(plan, blockers, language, 0)
            print(tr(language, "cli.upgrade.unowned_blocks_apply"), file=sys.stderr)
            _finish_report(root, plan, blockers, language, applied=0, mode="apply",
                           outcome="blocked_unowned")
            return EXIT_BLOCKED
        applied, apply_error, rollback_complete = _apply(root, plan, language)

    _print_report(plan, blockers if not args.apply else [], language, applied)
    if apply_error:
        print(apply_error, file=sys.stderr)
    outcome = ("applied" if applied else
               "failed" if apply_error else
               "blocked" if blockers else "ready" if plan["writes"] else "no_op")
    report_rel, report_error = _finish_report(root, plan, blockers, language, applied,
                                              "apply" if args.apply else "check", outcome)
    if report_error:
        print(tr(language, "cli.upgrade.report_failed", error=report_error), file=sys.stderr)
    elif report_rel:
        print(tr(language, "cli.upgrade.report", path=report_rel))

    if not rollback_complete:
        return EXIT_UNSAFE
    if apply_error or blockers:
        return EXIT_BLOCKED
    return EXIT_OK


def _finish_report(root, plan, blockers, language, applied, mode, outcome):
    from sage import __version__
    payload = {
        "run_id": uuid.uuid4().hex[:16],
        "schema_version": 1,
        "mode": mode,
        "outcome": outcome,
        "engine_version": __version__,
        "axes": plan["axes"],
        "host_runtime": plan["host_runtime"],
        # 경로는 root 상대만 남긴다 — 절대 경로는 사용자 이름과 디렉터리 구조를 노출한다.
        "writes": [{k: v for k, v in item.items() if k != "cycle_stem"}
                   for item in plan["writes"]],
        "unowned_drift": plan["unowned_drift"],
        "blockers": list(blockers),
        "applied": applied,
    }
    return _write_report(root, payload)
