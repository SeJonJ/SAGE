"""sage cycle — 지금 작업 중인 사이클을 게이트에 알려주는 선언 통로.

게이트는 편집마다 "이 편집이 어느 사이클인가"를 판정한다. phase 문서 편집은 파일명과
`Cycle-Stem:` 줄에서 정확히 얻지만, 소스 편집은 **git 브랜치 이름의 마지막 조각**에서 추론한다.
사이클마다 브랜치를 따는 흐름에서는 맞고, 장수 브랜치 하나로 여러 달을 도는 프로젝트에서는
영영 맞지 않는다 — 모든 소스 편집이 존재하지 않는 사이클에 결속돼 00~03 을 다 써도 막힌다.

    sage cycle use <stem>     선언
    sage cycle show           조회
    sage cycle clear          해제

선언은 `<root>/.sage/cycle.json` 하나다. env 와 달리 자식 프로세스로 새지 않고, 조회할 수 있고,
`sage install` 이 host `.gitignore` 에 쓰는 `/.sage/*` 관리 블록이 덮어 커밋되지 않는다.

`SAGE_CYCLE_STEM` 은 폐기하지 않는다 — 프로세스 1회용이라 범위가 더 좁고 CI 에서 정당하다.
둘이 함께 있으면 env 가 이기고, 이 명령은 그 사실을 화면에 적는다.
"""
import os
import subprocess
import sys

from sage import _resources

_ACTIONS = ("use", "show", "clear")


def register(sub):
    p = sub.add_parser("cycle", help="지금 작업 중인 사이클을 게이트에 알려줍니다")
    p.add_argument("action", choices=_ACTIONS, help="use <stem> | show | clear")
    p.add_argument("stem", nargs="?", default=None, help="use 할 때의 Cycle-Stem")
    p.add_argument("--root", default=None,
                   help="대상 프로젝트 루트 (기본: cwd 에서 가장 가까운 SAGE 설치본)")
    p.set_defaults(func=run)


def _load_cycle_state():
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    import cycle_state
    return cycle_state


def _resolve_root(cs, explicit):
    """--root 는 그대로 쓰고(명시 지정은 사용자 책임), 없으면 SAGE 표식을 거슬러 찾는다.

    표식이 없으면 **거부**한다. 여기서 cwd 로 떨어지면 게이트가 영영 읽지 않는 자리에 파일이
    놓이고, 사용자는 선언했다고 믿는다 — 조용한 무동작이 이 기능의 가장 나쁜 실패다.
    """
    if explicit:
        return os.path.abspath(explicit)
    root = cs.find_project_root(os.getcwd())
    if root is None:
        raise cs.DeclarationRootError(
            f"여기는 SAGE 프로젝트가 아닙니다 — '{cs.MARKER_REL}' 를 가진 상위 디렉터리를 "
            f"찾지 못했습니다 (cwd: {os.getcwd()}).\n"
            f"→ SAGE 설치본 안에서 실행하거나 `--root <경로>` 로 지정하세요.")
    return root


def _ignored_by_git(root, path):
    """선언 파일이 실제로 무시되는가 → True / False / None(판정 불가).

    D2 의 안전 근거가 `install` 이 쓴 `.gitignore` 관리 블록이므로, 검증 없이 "무시됩니다" 라고
    적지 않는다. git 이 없거나 저장소가 아니면 판정 불가이지 '안 덮임' 이 아니다.
    """
    try:
        proc = subprocess.run(["git", "-C", root, "check-ignore", "-q", path],
                              capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    return None                      # 128 = 저장소 아님/실행 실패


def _profile_missing(root):
    """게이트의 실제 전제조건은 profile 쌍이다 — 표식과 다르다.

    표식만 보고 "게이트가 읽는다" 고 단정할 수 없어서, 어긋난 상태를 여기서 한 번 노출한다.
    """
    return not any(os.path.exists(os.path.join(root, "sage", f"project-profile.{ext}"))
                   for ext in ("yaml", "json"))


def _warnings(root, path):
    lines = []
    ignored = _ignored_by_git(root, path)
    if ignored is False:
        lines.append("⚠️  이 파일이 git 에 무시되지 않습니다 — 커밋되면 남의 clone 에서 "
                     "엉뚱한 사이클에 결속됩니다.")
        lines.append("    → `sage install --force` 로 .gitignore 관리 블록을 복구하세요.")
    elif ignored is None:
        lines.append("ℹ️  git 무시 여부를 확인하지 못했습니다 (저장소가 아니거나 git 부재).")
    if _profile_missing(root):
        lines.append("⚠️  sage/project-profile.{yaml,json} 이 없습니다 — 설치는 있으나 게이트가 "
                     "아직 이 선언을 읽지 않습니다.")
    return lines


def _env_stem():
    return (os.environ.get("SAGE_CYCLE_STEM") or "").strip()


def _location(root, path):
    return [f"   프로젝트 루트: {root}", f"   선언 파일:     {path}"]


def run(args):
    cs = _load_cycle_state()
    try:
        root = _resolve_root(cs, args.root)
    except cs.DeclarationRootError as exc:
        print(f"⛔ [sage cycle] {exc}", file=sys.stderr)
        return 2
    path = cs.declaration_path(root)
    if args.action == "use":
        return _use(cs, args, root, path)
    if args.action == "clear":
        return _clear(cs, root, path)
    return _show(cs, root, path)


def _use(cs, args, root, path):
    if not args.stem:
        print("[sage cycle] use 에는 stem 이 필요합니다 (예: sage cycle use my-cycle)",
              file=sys.stderr)
        return 2
    try:
        cs.write_declaration(root, args.stem)
    except ValueError as exc:
        print(f"⛔ [sage cycle] {exc} — 경로 구분자·제어문자 없이 160자 이하여야 합니다",
              file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"⛔ [sage cycle] 선언을 쓰지 못했습니다: {path} ({type(exc).__name__})",
              file=sys.stderr)
        return 2
    stem, origin, _error = cs.resolve_stem(root)
    print(f"✅ 사이클 선언 — {args.stem}")
    for line in _location(root, path):
        print(line)
    if origin == "env":
        print(f"⚠️  지금은 SAGE_CYCLE_STEM='{stem}' 이 이깁니다 — 파일 선언을 쓰려면 "
              f"`unset SAGE_CYCLE_STEM` 하세요.")
    for line in _warnings(root, path):
        print(line)
    print("   (해제: sage cycle clear)")
    return 0


def _clear(cs, root, path):
    existed = cs.clear_declaration(root)
    print(f"✅ 사이클 선언 해제 — {path}" if existed
          else f"[sage cycle] 선언이 없습니다 — {path}")
    env = _env_stem()
    if env:
        print(f"⚠️  SAGE_CYCLE_STEM='{env}' 은 그대로 남아 있습니다 — "
              f"`unset SAGE_CYCLE_STEM` 으로 지우세요.")
    return 0


def _show(cs, root, path):
    stem, origin, error = cs.resolve_stem(root)
    print("== sage cycle show ==")
    for line in _location(root, path):
        print(line)
    if error:
        print(f"⚠️  선언 파일을 읽지 못했습니다: {error}")
        print("    → 게이트는 선언 없음으로 진행합니다. `sage cycle use <stem>` 으로 다시 쓰세요.")
    if not stem:
        print("현재 선언: 없음 — 게이트는 브랜치 이름 마지막 조각에서 사이클을 추론합니다.")
    else:
        label = {"env": "SAGE_CYCLE_STEM", "cli": ".sage/cycle.json"}[origin]
        print(f"현재 선언: {stem}  ({label})")
        file_stem, _ = cs.read_declaration(root)
        if origin == "env" and file_stem:
            print(f"   (파일 선언 '{file_stem}' 은 env 에 밀려 쓰이지 않습니다)")
    for line in _warnings(root, path):
        print(line)
    return 0
