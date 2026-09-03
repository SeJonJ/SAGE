"""`sage uninstall [--global|--all]` — 설치한 SAGE 자산을 되돌린다.

## 무엇을 하지 않는가

자기 자신을 지우지 않고 `pipx`·`pip` 를 부르지 않는다. `plan_docs`·Obsidian vault·프로젝트
소스·테스트·Git 이력을 지우지 않는다. 소유권을 증명하지 못한 파일은 **보존하고 보고한다** —
완전히 지워 주는 편의보다 남의 파일을 지우지 않는 쪽이 언제나 낫다.

## 순서가 계약이다

```
불변 계획(기준 확보)  →  확인 또는 --yes  →  lock  →  지문 대조  →  경계 재확인
                     →  backup  →  실행  →  검증  →  commit  →  cleanup  →  unlock
```

기준(fingerprint)은 **계획과 같은 시점**에 뜬다. 확인 뒤에 뜨면 prompt 가 열려 있는 동안
사용자가 고친 파일이 기준이 되어, 방금 고친 파일을 그대로 지운다. 사용자가 동의한 것은 화면에
본 그 상태이므로 기준도 그 순간의 것이어야 한다.

`--check` 는 첫 단계 뒤 끝난다 — lock 도 잡지 않는다. 취소하면 두 번째에서 끝나고 byte 하나
바뀌지 않는다. 지문이 어긋나면 지우지 않는다.

## scope 는 읽기까지 가른다

기본(project) 범위는 `$CODEX_HOME` 을 읽지도 쓰지도 않는다. 그래서 전역에 무엇이 남았는지
**주장하지 않고**, 검사하지 않았다는 사실과 `--all` 을 안내한다. 보지 않은 것을 봤다고 말하지
않는 것이 이 고지의 전부다.
"""
import json
import os
import sys

from sage import uninstall_cleanup as _manual
from sage import uninstall_executor as _exec
from sage import uninstall_plan as _plan
from sage.diagnostic_contract import render_recovery
from sage.i18n import language_of, tr


def register(sub, context):
    parser = sub.add_parser("uninstall", help=tr(context, "cli.uninstall.uninstall"))
    parser.add_argument("--dest", default=None, help=tr(context, "cli.uninstall.dest"))
    parser.add_argument("--global", dest="global_scope", action="store_true",
                        help=tr(context, "cli.uninstall.global"))
    parser.add_argument("--all", dest="all_scope", action="store_true",
                        help=tr(context, "cli.uninstall.all"))
    parser.add_argument("--check", action="store_true", help=tr(context, "cli.uninstall.check"))
    parser.add_argument("--yes", action="store_true", help=tr(context, "cli.uninstall.yes"))
    parser.add_argument("--verbose", action="store_true", help=tr(context, "cli.uninstall.verbose"))
    parser.add_argument("--json", action="store_true", help=tr(context, "cli.uninstall.json"))
    parser.set_defaults(func=run)


def _usage_error(language, key):
    print(tr(language, key), file=sys.stderr)
    return 2


def _scope_of(args):
    if args.global_scope:
        return _plan.SCOPE_GLOBAL
    if args.all_scope:
        return _plan.SCOPE_ALL
    return _plan.SCOPE_PROJECT


def run(args):
    language = language_of(args)

    # 조합 검사가 먼저다. 계획을 만든 뒤에 usage 오류를 내면 사용자는 실행되지 않을 계획을
    # 읽게 되고, 그 화면은 "이렇게 지워진다" 로 읽힌다.
    if args.global_scope and args.all_scope:
        return _usage_error(language, "cli.uninstall.err_global_all")
    if args.check and args.yes:
        return _usage_error(language, "cli.uninstall.err_check_yes")
    if args.global_scope and args.dest:
        return _usage_error(language, "cli.uninstall.err_global_dest")
    # 확인 prompt 와 JSON 을 같은 stream 에 섞지 않는다. 섞으면 기계가 읽는 출력에 사람에게
    # 묻는 문장이 들어가고, 둘 다 못 쓰게 된다.
    if args.json and not args.check and not args.yes:
        return _usage_error(language, "cli.uninstall.err_json_needs_yes")

    scope = _scope_of(args)
    dest = os.path.abspath(args.dest or os.getcwd())
    try:
        plan = _plan.build(dest, scope)
    except Exception as exc:
        # 계획은 **읽기만** 하는 층인데도 손상된 입력 하나로 죽을 수 있다 — 비 UTF-8 설정,
        # 권한 없는 디렉터리, 기대 밖의 파일 종류. 그때 traceback 을 올리면 아무것도 바꾸지
        # 않는 `--check` 조차 결과를 못 내고 `--json` 소비자는 깨진 출력을 받는다. 이 명령의
        # 결과는 어떤 입력에서도 네 상태 중 하나여야 한다.
        blocked = _plan.UninstallPlan(scope, dest, (), _plan.BLOCKED, "uninstall.plan_failed")
        _render(blocked, args, language, executed=False,
                extra={"detail": [{"kind": "exception", "type": exc.__class__.__name__}]})
        if not args.json:
            print(f"  {exc.__class__.__name__}", file=sys.stderr)
        return blocked.exit_code

    if args.check:
        _render(plan, args, language, executed=False)
        return plan.exit_code

    if plan.status == _plan.BLOCKED:
        # 안전한 계획을 만들 수 없었다. 자동 제거는 없으므로 손으로 무엇을 해야 하는지 낸다.
        _render(plan, args, language, executed=False, basis=_manual.BASIS_VERIFIED)
        return plan.exit_code

    if not plan.write_targets():
        _render(plan, args, language, executed=True)
        return plan.exit_code

    if not args.yes:
        if not sys.stdin.isatty():
            # 비대화형에서 기다리면 CI 가 멈추고, 동의를 추정하면 지우면 안 되는 것을 지운다.
            blocked = _plan.UninstallPlan(scope, dest, plan.actions, _plan.BLOCKED,
                                          "uninstall.confirmation_required", plan.notices,
                                          baseline=plan.baseline,
                                          global_root=plan.global_root)
            _render(blocked, args, language, executed=False)
            return blocked.exit_code
        _render(plan, args, language, executed=False)
        answer = input(tr(language, "cli.uninstall.confirm_prompt")).strip().lower()
        if answer not in ("y", "yes"):
            cancelled = _plan.UninstallPlan(scope, dest, plan.actions, _plan.CANCELLED,
                                            None, plan.notices, baseline=plan.baseline,
                                            global_root=plan.global_root)
            print(tr(language, "cli.uninstall.cancelled"))
            return cancelled.exit_code

    def blocked_plan(code, notices=None):
        return _plan.UninstallPlan(scope, dest, plan.actions, _plan.BLOCKED, code,
                                   plan.notices if notices is None else notices,
                                   baseline=plan.baseline, global_root=plan.global_root,
                                   root_baseline=plan.root_baseline)

    # 단계 이름을 받아 두는 이유는 실패한 뒤 **무엇을 손으로 정리해야 하는가** 의 근거가
    # 달라지기 때문이다. 아무것도 바꾸지 않고 멈춘 실패와, 바꿨다가 되돌린 실패는 사용자가
    # 보아야 할 목록이 다르다 — 그 둘을 code 이름만으로는 구분할 수 없다.
    trace = []
    try:
        # 기준은 넘기지 않는다. plan 이 자기 시점의 기준을 들고 있고, 실행 층은 그것만 본다.
        result = _exec.execute(plan, trace=trace)
    except _exec.RollbackFailed as failure:
        # `--json` 이라도 **여기서 JSON 을 낸다.** 자동화가 가장 알아야 하는 상태가 실패이고,
        # 그 하나만 사람용 문장으로 내보내면 기계는 결과를 읽지 못한 채 exit code 만 본다.
        preserved = _shown(failure.preserved_paths, plan)
        # 되돌리기까지 실패했다. 다시 읽을 수 있으면 읽되 근거는 언제나 `uncertain` 이다 —
        # 읽어서 보이는 것이 곧 확정된 상태라는 뜻은 아니다.
        actions, basis = _after_failure(dest, scope, plan, trace, uncertain=True)
        blocked = _plan.UninstallPlan(scope, dest, actions, _plan.BLOCKED,
                                      "uninstall.rollback_failed", plan.notices,
                                      baseline=plan.baseline, global_root=plan.global_root,
                                      root_baseline=plan.root_baseline)
        _render(blocked, args, language, executed=False,
                extra={"preserved_paths": preserved,
                       "rollback_reasons": list(getattr(failure, "reasons", ()))},
                basis=basis, unknown=preserved)
        if not args.json:
            for path in preserved:
                print(f"  {path}", file=sys.stderr)
        return blocked.exit_code
    except ValueError as exc:
        code = str(exc) if str(exc).startswith("uninstall.") else "uninstall.fingerprint_changed"
        actions, basis = _after_failure(dest, scope, plan, trace)
        blocked = _plan.UninstallPlan(scope, dest, actions, _plan.BLOCKED, code,
                                      plan.notices, baseline=plan.baseline,
                                      global_root=plan.global_root,
                                      root_baseline=plan.root_baseline)
        # native 실패였다면 **어느 호출이 어떤 code 로** 실패했는지 함께 낸다. 진단 이름
        # 하나만 남으면 원격에서만 나는 실패의 원인이 그 머신 안에 갇힌다. 싣는 것은 API
        # 이름과 정수뿐이라 경로도 OS 원문도 새지 않는다.
        native = getattr(exc, "native", None)
        _render(blocked, args, language, executed=False, basis=basis,
                extra={"native": native} if native else None)
        return blocked.exit_code
    except Exception as exc:
        # 여기까지 온 것은 **우리가 이름 붙이지 않은 실패**다. traceback 을 그대로 올리면
        # 사용자는 exit 1 과 스택을 받고, `--json` 소비자는 깨진 출력을 받으며, 계약된 복구
        # 안내도 나오지 않는다. 어떤 실패든 이 명령의 결과는 네 상태 중 하나여야 한다.
        # 이름 없는 실패도 **같은 helper 를 지난다.** 여기만 계획을 그대로 쓰면, 가장 알 수
        # 없는 실패에서 가장 확신에 찬 목록이 나온다.
        actions, basis = _after_failure(dest, scope, plan, trace)
        blocked = _plan.UninstallPlan(scope, dest, actions, _plan.BLOCKED,
                                      "uninstall.execution_failed", plan.notices,
                                      baseline=plan.baseline, global_root=plan.global_root,
                                      root_baseline=plan.root_baseline)
        # 예외 **종류**만 싣는다. 메시지에는 경로·설정값·OS 원문이 붙고, 그것은 로그와 CI
        # 출력으로 그대로 흘러간다.
        _render(blocked, args, language, executed=False,
                extra={"detail": [{"kind": "exception", "type": exc.__class__.__name__}]},
                basis=basis)
        if not args.json:
            print(f"  {exc.__class__.__name__}", file=sys.stderr)
        return blocked.exit_code

    if result.leftover_backups:
        # 요청한 변경은 전부 끝났다. 못 치운 것은 우리가 만든 임시 보관소뿐이므로 결과를
        # 바꾸지 않고 경로만 알린다.
        plan = _plan.UninstallPlan(plan.scope, plan.dest, plan.actions, plan.status, None,
                                   plan.notices + ("uninstall.notice.backup_left",),
                                   baseline=plan.baseline, global_root=plan.global_root)
    # **같은 정화 경로 한 벌**을 `leftover_backups` 와 수동 안내가 함께 쓴다. 두 자리에서
    # 따로 만들면 둘이 다른 말을 하게 되고, 그때 사용자는 어느 쪽을 믿어야 하는지 모른다.
    shown = _shown(result.leftover_backups, plan) if result.leftover_backups else []
    _render(plan, args, language, executed=True,
            extra={"leftover_backups": shown} if shown else None,
            basis=_manual.BASIS_COMMITTED if shown else None,
            leftovers=result.leftover_backups, shown_leftovers=shown)
    if shown and not args.json:
        for path in shown:
            print(f"  {path}", file=sys.stderr)
    return plan.exit_code


_DAMAGE_KEYS = {
    "type": "cli.uninstall.damage.type",
    "json_syntax": "cli.uninstall.damage.json_syntax",
    "encoding": "cli.uninstall.damage.encoding",
    "io": "cli.uninstall.damage.io",
    "marker": "cli.uninstall.damage.marker",
    "manifest": "cli.uninstall.damage.manifest",
    "missing": "cli.uninstall.damage.missing",
    "unknown_kind": "cli.uninstall.damage.unknown_kind",
    "unsupported_kind": "cli.uninstall.damage.unsupported_kind",
    "unknown_event": "cli.uninstall.damage.unknown_event",
    "conflict": "cli.uninstall.damage.conflict",
    "json_duplicate_key": "cli.uninstall.damage.json_duplicate_key",
    "json_constant": "cli.uninstall.damage.json_constant",
    "exception": "cli.uninstall.damage.exception",
}


def _damage_text(entry, language):
    """구조화된 손상 사실 하나를 문장으로.

    화면과 `--json` 이 **같은 dict** 를 소비한다. 문장을 따로 만들면 둘이 다른 말을 하게 되고,
    그때 사용자는 어느 쪽을 믿어야 하는지 알 수 없다. 모르는 종류는 문장을 지어내지 않고
    이름만 낸다 — 없는 사실을 채워 넣는 것보다 빈 자리를 보이는 편이 정직하다.
    """
    key = _DAMAGE_KEYS.get(entry.get("kind"))
    if key is None:
        return f"{entry.get('kind')}"
    values = {name: ("?" if value is None else value) for name, value in entry.items()}
    return tr(language, key, **values)


def _shown(paths, plan):
    """계획 밖에서 생긴 경로들(backup·복구 실패 잔여)도 같은 표기로 낸다.

    **scope 를 경로마다 고른다.** 전부 project 기준으로 보면 `--global`·`--all` 이 남긴
    전역 보관소가 `<outside-project>` 하나로 접히고, 사용자는 치워야 할 자리를 잃는다.
    그 경로들은 write root 아래에 우리가 만든 것이라 어느 root 아래인지 알 수 있다.
    """
    shown = []
    for path in paths:
        if plan.global_root and _plan.within_root(plan.global_root, path):
            scope = _plan.SCOPE_GLOBAL
        else:
            scope = _plan.SCOPE_PROJECT
        shown.append(_plan.display_path(path, scope, plan.dest, plan.global_root))
    return shown


def _after_failure(dest, scope, plan, trace, uncertain=False):
    """실패 뒤 화면에 쓸 `(actions, basis)`. **의도했던 계획을 남은 목록이라고 부르지 않는다.**

    실행이 중간에 실패했다면 일부 action 은 이미 적용됐다. 그때 계획을 그대로 "남은 것" 이라고
    내면 이미 지워진 것을 다시 지우라고 말하거나, 되돌아온 것을 아직 남았다고 말한다. 그래서
    **다시 읽는다.**

    다시 읽지 못하면 확정된 것이 없다. 그때는 순서를 비우고 정화된 경로만 낸다 — 추측을
    목록으로 파는 것보다 빈 자리를 보이는 편이 정직하다.

    아무것도 바꾸지 않고 멈춘 실패는 다시 읽지 않는다. 방금 만든 계획이 곧 지금 상태이고,
    거기서 한 번 더 읽으면 그 사이의 변화를 근거로 삼게 된다.
    """
    if not uncertain and "rollback" not in trace:
        return plan.actions, _manual.BASIS_VERIFIED
    try:
        reread = _plan.build(dest, scope)
    except Exception:
        return (), _manual.BASIS_UNCERTAIN
    return reread.actions, (_manual.BASIS_UNCERTAIN if uncertain
                            else _manual.BASIS_POST_ROLLBACK)


def _print_recovery(code, language):
    for line in render_recovery(code, lambda key: tr(language, key), "cli."):
        print(line, file=sys.stderr)


def _render(plan, args, language, executed, extra=None, basis=None, unknown=(),
            leftovers=(), shown_leftovers=()):
    """화면과 `--json` 이 **같은 값 한 벌**을 소비한다.

    수동 정리 안내도 같은 규칙을 따른다. `--json` 은 배열을 복제하지 않고 순서·근거만 싣고,
    화면은 그 순서대로 이미 찍은 구획을 가리킨다 — 두 출력이 서로 다른 목록을 갖는 순간
    사용자는 어느 쪽을 믿어야 하는지 알 수 없다.
    """
    manual = None
    if basis is not None and _manual.applies(plan, executed, leftovers):
        manual = _manual.guidance(plan, basis=basis, unknown=unknown,
                                  leftovers=shown_leftovers)

    if args.json:
        payload = plan.as_json()
        payload["executed"] = executed
        if manual is not None:
            payload["manual_cleanup"] = manual
        if extra:
            payload.update(extra)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return

    header = "cli.uninstall.header_result" if executed else "cli.uninstall.header_plan"
    print(tr(language, header, scope=plan.scope, status=plan.status))
    print()

    # 수동 정리를 안내하는 화면에서는 삭제 목록을 **접지 않는다.** 접힌 목록을 보고 손으로
    # 정리할 수는 없다.
    _section(plan, _plan.DELETE, "cli.uninstall.section_delete", language,
             args.verbose or manual is not None)
    _section(plan, _plan.STRIP, "cli.uninstall.section_strip", language, True)
    # 보존과 차단은 길어도 절대 줄이지 않는다. 줄이는 순간 사용자는 남은 것을 모른 채 끝난다.
    _section(plan, _plan.PRESERVE, "cli.uninstall.section_preserve", language, True)
    _section(plan, _plan.BLOCK, "cli.uninstall.section_block", language, True)

    if extra and isinstance(extra.get("detail"), list):
        for entry in extra["detail"]:
            print(f"  {_damage_text(entry, language)}", file=sys.stderr)

    if extra and isinstance(extra.get("native"), dict):
        native = extra["native"]
        code = native.get("error_code")
        print(tr(language, "cli.uninstall.native_failure",
                 operation=native.get("operation"), kind=native.get("error_kind"),
                 code=f"{code:#x}" if isinstance(code, int) else code),
              file=sys.stderr)

    for notice in plan.notices:
        print(tr(language, f"cli.{notice}"))

    if manual is not None and manual["available"]:
        _print_manual(manual, language)

    if plan.blocked_reason:
        print()
        print(tr(language, f"cli.{plan.blocked_reason}"), file=sys.stderr)
        _print_recovery(plan.blocked_reason, language)


_MANUAL_STEP_KEYS = {
    _plan.STRIP: "cli.uninstall.manual.step_strip",
    _plan.DELETE: "cli.uninstall.manual.step_delete",
    _plan.PRESERVE: "cli.uninstall.manual.step_preserve",
}


def _print_manual(manual, language):
    """무엇을 어떤 순서로 손대야 하는지. **파괴적 명령은 만들지 않는다.**

    `rm`·`rmdir`·PowerShell recursive delete·wildcard 를 복구 명령으로 주지 않는다. 그 명령
    하나가 잘못된 디렉터리에서 실행되면 이 명령이 지키려던 모든 것을 한 번에 지운다.
    """
    print()
    print(tr(language, "cli.uninstall.manual.header",
             basis=tr(language, f"cli.uninstall.manual.basis.{manual['basis']}")))
    for index, kind in enumerate(manual["order"], start=1):
        print(f"  {index}. {tr(language, _MANUAL_STEP_KEYS[kind])}")
    for code in manual["warning_codes"]:
        print(f"  {tr(language, f'cli.{code}')}")
    if manual["leftovers"]:
        print(f"  {tr(language, 'cli.uninstall.manual.leftovers')}")
        for path in manual["leftovers"]:
            print(f"    - {path}")
    if manual["unknown"]:
        print(f"  {tr(language, 'cli.uninstall.manual.unknown')}")
        for path in manual["unknown"]:
            print(f"    - {path}")
    print(f"  {tr(language, 'cli.uninstall.manual.recheck')}")


def _section(plan, kind, title_key, language, expand):
    entries = plan.of_kind(kind)
    if not entries:
        return
    print(tr(language, title_key, count=len(entries)))
    if kind == _plan.DELETE and not expand:
        # 묶어서 보여주되 건수는 숨기지 않는다. `--verbose` 가 펼친다.
        groups = {}
        for action in entries:
            groups.setdefault(action.reason, []).append(action)
        for reason in sorted(groups):
            print(f"  - {reason}: {len(groups[reason])}")
        print()
        return
    for action in entries:
        # 화면과 `--json` 이 **같은 formatter** 를 통과한 값 하나를 쓴다. 둘이 갈라지면
        # 사용자는 사람이 읽는 경로와 기계가 읽는 경로 중 어느 쪽이 진짜인지 알 수 없다.
        print(f"  - {action.display_path(plan.dest, plan.global_root)}")
        print(f"      {tr(language, f'cli.{action.reason}')}")
        if action.state is not None:
            print(f"      {tr(language, 'cli.uninstall.registration_state', state=tr(language, f'cli.uninstall.state.{action.state}'))}")
        for entry in action.detail or ():
            print(f"      {_damage_text(entry, language)}")
    print()
