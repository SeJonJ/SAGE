"""sage upgrade — 설치본을 현재 엔진에 맞추는 읽기 전용 진단과 트랜잭션 적용.

이 명령이 다른 명령과 다른 점은 **version 이 어긋난 상태에서도 반드시 불릴 수 있어야 한다**는
것이다. 버전 불일치를 고치는 유일한 통로가 버전 불일치 때문에 막히면 사용자는 빠져나갈 방법이
없다. 그래서 여기서는 부트스트랩 게이트도, profile 검증 실패도 실행 자체를 막지 않는다 —
읽을 수 있는 만큼 읽고 못 읽은 축은 `unknown` 으로 보고한다.

쓰는 것과 안 쓰는 것을 좁고 명시적으로 가른다. upgrade 가 소유하는 것은 **선언 값**뿐이다:

  · `sage/project-profile.yaml` 의 `sage.required_version` scalar 한 개
  · `.sage/cycle.json` 의 schema 1 → 2 미러 이행

local profile·policy·overlay·authored asset·plan/evidence/audit/vault·프로젝트 코드·검증
스크립트는 **write target 이 아니다**. 렌더 바이트도 아니다 — 그건 `sage install --force` 가
소유하고, upgrade 가 남의 소유물을 대신 덮으면 어느 명령이 그 파일을 만들었는지 알 수 없게 된다.

`--force` 는 "남의 파일을 덮어라"가 아니라 **"내가 소유하지 않은 drift 가 있어도 내 write set 은
진행하라"**다. 덮는 범위를 넓히는 플래그로 만들면 이름과 동작이 어긋나고, 사용자는 그 차이를
사고가 난 뒤에 알게 된다.

자동 downgrade 는 없다. 되돌리려면 apply 가 남긴 backup 으로 복구한다(보고서에 경로가 있다).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid

from sage.i18n import language_of, tr

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

    return {
        "axes": {"required": axes.required, "installed": axes.installed,
                 "generated": axes.generated, "runtime": axes.runtime},
        "host_runtime": (manifest or {}).get("host_runtime") or UNKNOWN,
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


def _apply(root, plan, language):
    """(applied_count, error, rollback_complete). 실패하면 전부 되돌린다."""
    from sage.install_transaction import (DestinationLock, InstallBusyError, InstallDriftError,
                                          InstallTransaction, capture_paths, verify_captured)

    targets = [os.path.join(root, item["path"]) for item in plan["writes"]]
    if not targets:
        return 0, "", True

    try:
        lock = DestinationLock(root)
    except InstallBusyError as exc:
        return 0, tr(language, "cli.upgrade.lock_failed", error=str(exc)), True

    lock.acquire()
    try:
        captured = capture_paths(targets)
        transaction = InstallTransaction(expected=captured, write_roots=(root,))
        try:
            for item in plan["writes"]:
                absolute = os.path.join(root, item["path"])
                if item["kind"] == "required_version":
                    with open(absolute, encoding="utf-8") as handle:
                        raw = handle.read()
                    updated = _apply_required_version(raw, item)
                    if updated is None:
                        raise InstallDriftError("required_version 위치가 판정 시점과 다름")
                    body = updated.encode("utf-8")
                elif item["kind"] == "cycle_schema":
                    body = (json.dumps({"version": 2, "cycle_stem": item["cycle_stem"],
                                        "document_language": item["document_language"],
                                        "declared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                     time.gmtime())},
                                       ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                else:
                    raise InstallDriftError(f"알 수 없는 write kind: {item['kind']}")
                mode = os.stat(absolute).st_mode & 0o777
                transaction.declare_file_output(absolute, body, mode)
                transaction.stage_write(absolute)
                with open(absolute, "wb") as handle:
                    handle.write(body)
                os.chmod(absolute, mode)
                transaction.record_output(absolute)
            transaction.verify_outputs()
            verify_captured({k: v for k, v in captured.items() if k not in set(targets)})
            transaction.commit()
            return len(plan["writes"]), "", True
        except BaseException as exc:
            try:
                transaction.rollback()
            except BaseException as rollback_error:
                return 0, tr(language, "cli.upgrade.rollback_failed",
                             error=f"{type(exc).__name__}: {exc}",
                             rollback=f"{type(rollback_error).__name__}"), False
            return 0, tr(language, "cli.upgrade.apply_failed",
                         error=f"{type(exc).__name__}: {exc}"), True
    finally:
        lock.release()


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
