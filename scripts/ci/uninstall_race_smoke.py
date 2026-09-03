#!/usr/bin/env python3
"""제거 도중의 실패와 경쟁을 **실제로 주입**하고, 그때마다 계약이 서는지 본다.

## 왜 별도 스크립트인가

`test_uninstall.py` 의 실패·경쟁 반례는 hook 회귀 job 에서만 돌고, 그 job 은 ubuntu 하나다.
그래서 Windows 에서는 이 방어들이 **한 번도 실행된 적이 없었다.** 실행된 적 없는 방어는 있다고
말할 수 없다.

이 스크립트는 순수 Python 이라 세 OS 어디서나 돈다. `uninstall_matrix` 가 소비자 smoke 뒤에
이어서 돌린다.

## 목록이 권위다

승인 설계 §9.2 가 요구한 주입 자리가 `REQUIRED_INJECTIONS` 다. 각 반례는 그중 하나에 대응하고,
끝에서 **요구 목록과 실행 목록을 대조한다.** 기대 건수를 따로 적지 않는 이유는 두 벌이 되는
순간 한쪽만 늘기 때문이다 — 반례가 조용히 빠져도 남은 것들은 여전히 통과하므로, 수를 세지
않으면 "전부 통과" 가 "아무것도 주입하지 않음" 과 구별되지 않는다.

## 무엇을 단언하는가

각 반례는 같은 네 가지를 본다.

- 프로젝트·global root **밖**의 sentinel 이 그대로일 것
- 계획에 없던 파일이 살아남을 것
- commit 전 실패는 **모든 root** 의 상태를 원래대로 되돌릴 것
- 판정이 계약된 code 이거나, 계약된 성공일 것

## 주입은 제품의 seam 으로만 한다

`execute(trace=...)` 는 검사가 단계 순서를 읽으라고 열어 둔 자리이고, journal 의 method 는
이미 test 가 감싸던 자리다. 검사 전용 갈고리를 제품에 새로 뚫지 않는다 — 그렇게 뚫은 구멍은
검사가 사라진 뒤에도 남는다.
"""
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from sage import install_transaction as _tx        # noqa: E402
from sage import uninstall_executor as _exec       # noqa: E402
from sage import uninstall_fs as _fs               # noqa: E402
from sage import uninstall_plan as _plan           # noqa: E402

# fixture 자리는 **소비자 smoke 와 같은 규칙**을 쓴다. 공유 temp 로 내려가는 fallback 을 두면
# 아무도 환경변수를 지정하지 않으므로 그 fallback 이 사실상 유일한 경로가 되고, 남이 이름을
# 먼저 만들어 둘 수 있는 자리에서 경계 검사를 돌리게 된다. 정의를 가져다 쓴다 — 두 벌이면
# 한쪽만 고쳐지는 날이 온다.
from uninstall_smoke import fixture_base           # noqa: E402

# 이 값이 참이면 "지원 범위 밖이라 아무것도 주입하지 못했다" 는 **실패**다. CI 가 실제
# mutation 0건으로 초록이 되는 것을 막는 유일한 장치다.
REQUIRE_MUTATION = bool(os.environ.get("SAGE_UNINSTALL_REQUIRE_MUTATION"))

# 승인 설계 §9.2 의 주입 자리. **이 목록이 권위다.**
REQUIRED_INJECTIONS = (
    "root-swap-after-fingerprint",      # P0 회귀 — 지문 통과 뒤 root 이름 교체
    "ancestor-swap-before-execution",   # §9.2-1
    "ancestor-swap-after-root-pin",     # §9.2-2
    "ancestor-swap-after-first-backup", # §9.2-3
    "strip-leaf-replaced-by-link",      # §9.2-4
    "backup-name-collision",            # §9.2-5
    "partial-write-then-io-failure",    # §9.2-6
    "base-exception-during-mutation",   # §9.2-7
    "global-fails-after-project",       # §9.2-8
    "output-verification-failure",      # §9.2-9
    "cleanup-failure-after-commit",     # §9.2-10
)

FAILURES = []
EXECUTED = []


# --- 도구 ---------------------------------------------------------------------

def link_directory(link, target):
    """디렉터리 링크 하나. 만들지 못하면 `False` — 주입 없이 통과로 세지 않는다."""
    try:
        if os.name == "nt":
            done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                                  capture_output=True, text=True)
            return done.returncode == 0
        os.symlink(target, link)
        return True
    except (OSError, NotImplementedError):
        return False


def link_file(link, target):
    try:
        if os.name == "nt":
            done = subprocess.run(["cmd", "/c", "mklink", link, target],
                                  capture_output=True, text=True)
            return done.returncode == 0
        os.symlink(target, link)
        return True
    except (OSError, NotImplementedError):
        return False


def snapshot(root):
    """되돌아왔는지 볼 오라클. 이름·종류·내용·쓰기 가능 여부까지 본다.

    보관소(`.sage-install-backup-*`)는 뺀다 — 그것이 남았는지는 따로 단언한다.
    """
    found = {}
    if not os.path.isdir(root):
        return found
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".sage-install-backup-")]
        for name in list(dirs) + [f for f in files
                                  if not f.startswith(".sage-install-backup-")]:
            full = os.path.join(folder, name)
            rel = os.path.relpath(full, root)
            info = os.lstat(full)
            if stat.S_ISDIR(info.st_mode):
                found[rel] = ("dir", None, None)
            elif stat.S_ISLNK(info.st_mode):
                found[rel] = ("link", None, os.readlink(full))
            else:
                with open(full, "rb") as handle:
                    digest = hashlib.sha256(handle.read()).hexdigest()
                # Windows 에서 의미 있는 권한 비트는 쓰기 가능 여부다. POSIX 전용으로 두면
                # 이 단언이 Windows 에서 통째로 사라진다.
                found[rel] = ("file", bool(info.st_mode & stat.S_IWRITE), digest)
    return found


def backups_left(root):
    left = []
    for folder, _dirs, files in os.walk(root):
        for name in files + _dirs:
            if name.startswith(".sage-install-backup-"):
                left.append(os.path.relpath(os.path.join(folder, name), root))
    return sorted(left)


def check(condition, message):
    if not condition:
        FAILURES.append(message)
    return condition


def run_plan(plan, trace=None):
    """실행하고 **판정 문자열 하나**로 돌려준다. 어떤 실패든 이름을 남긴다.

    이름 없는 예외로 새면 반례가 "무언가 터졌다" 로만 남고, 그것으로는 계약을 확인할 수 없다.
    """
    try:
        _exec.execute(plan, trace=trace)
    except ValueError as exc:
        return str(exc)
    except _exec.RollbackFailed as exc:
        return f"uninstall.rollback_failed:{exc}"
    except KeyboardInterrupt:
        return "KeyboardInterrupt"
    except Exception as exc:
        return f"unnamed:{exc.__class__.__name__}"
    return None


class patched:
    """journal 의 한 단계를 감싼다. 끝나면 **저장한 원래 함수**로 되돌린다."""

    def __init__(self, name, replacement, owner=None):
        self.owner = owner or _tx.InstallTransaction
        self.name = name
        self.replacement = replacement

    def __enter__(self):
        self.original = getattr(self.owner, self.name)
        setattr(self.owner, self.name, self.replacement(self.original))
        return self.original

    def __exit__(self, *_exc):
        setattr(self.owner, self.name, self.original)
        return False


class backend_patched:
    """만들어진 backend 의 method 하나를 감싼다.

    journal 이 아니라 backend 를 감싸는 이유는, 결속된 구현이 그 뒤에 있기 때문이다 —
    journal 쪽을 감싸면 실제로 파일을 만지는 코드는 건드리지 못한 채 통과한다.
    """

    def __init__(self, name, replacement):
        self.name = name
        self.replacement = replacement

    def __enter__(self):
        self.original = _fs.backend_for
        name, replacement = self.name, self.replacement

        def wrapped(roots):
            backend = self.original(roots)
            setattr(backend, name, replacement(getattr(backend, name)))
            return backend

        _fs.backend_for = wrapped
        # 실행 층은 import 시점에 이름을 붙잡아 두므로 그쪽도 함께 바꾼다.
        _exec._fs.backend_for = wrapped
        return self

    def __exit__(self, *_exc):
        _fs.backend_for = self.original
        _exec._fs.backend_for = self.original
        return False


class StepHook(list):
    """단계 이름이 나오는 **바로 그 순간** 무언가를 한다.

    `execute(trace=...)` 는 검사가 단계 순서를 읽으라고 열어 둔 자리다. 주입도 같은 자리에서
    한다 — 제품에 검사용 갈고리를 새로 뚫지 않아도 되고, 주입 시점이 계약된 단계 이름으로
    남아 "어디에 넣었는지" 가 문서가 아니라 코드에 있다.
    """

    def __init__(self, at, action, occurrence=1):
        super().__init__()
        self.at = at
        self.action = action
        self.occurrence = occurrence
        self.seen = 0
        self.fired = False

    def append(self, name):
        list.append(self, name)
        if name != self.at or self.fired:
            return
        self.seen += 1
        if self.seen >= self.occurrence:
            self.fired = True
            self.action()


class Consumer:
    """실제 `sage install` 로 만든 소비 프로젝트 하나.

    `--host codex --skill-scope global` 은 `$CODEX_HOME/skills` 를 두 번째 write root 로
    만든다. global·all 반례에는 그 root 가 있어야 한다 — 없으면 그 scope 의 주입은 대상이
    없어 조용히 통과한다.
    """

    def __init__(self, label, host="claude", skill_scope=None):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix=f"uninstall-race-{label}-",
                                                      dir=fixture_base()))
        self.project = os.path.join(self.root, "proj")
        self.codex_home = os.path.join(self.root, "codex")
        os.makedirs(self.project)
        os.makedirs(self.codex_home)
        self.env = dict(os.environ, PYTHONPATH=REPO, CODEX_HOME=self.codex_home)
        scope_args = ["--skill-scope", skill_scope] if skill_scope else []
        self.install = subprocess.run(
            [sys.executable, "-m", "sage", "install", "--host", host,
             *scope_args, "--dest", self.project],
            cwd=REPO, env=self.env, capture_output=True, text=True)

    @property
    def global_root(self):
        return os.path.join(self.codex_home, "skills")

    @property
    def environ(self):
        return {"CODEX_HOME": self.codex_home}

    def outside(self, name="outside"):
        """프로젝트·global root **밖**의 sentinel 디렉터리."""
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "victim.txt"), "w", encoding="utf-8") as handle:
            handle.write("someone else's file\n")
        return path

    def unapproved(self, where, name="not-in-plan.txt"):
        """계획에 없는 파일. 살아남아야 "승인한 것만 지웠다" 가 증명된다."""
        path = os.path.join(where, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("untouched\n")
        return path

    def seed_registration(self):
        """`.claude/settings.json` 을 STRIP 대상으로 만든다."""
        path = os.path.join(self.project, ".claude", "settings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        command = sorted(_plan.canonical_commands("claude"))[0]
        document = {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": command}]}]}, "mine": True}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        return path

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


def assert_outside_untouched(label, outside):
    check(sorted(os.listdir(outside)) == ["victim.txt"],
          f"{label}: 프로젝트 밖이 변했다: {sorted(os.listdir(outside))}")


def assert_restored(label, roots_before):
    """commit 전 실패는 **모든 root** 를 원래대로 되돌린다."""
    for root, before in roots_before.items():
        after = snapshot(root)
        if before != after:
            missing = sorted(set(before) - set(after))[:4]
            added = sorted(set(after) - set(before))[:4]
            changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])[:4]
            FAILURES.append(f"{label}: {os.path.basename(root)} 가 복구되지 않았다 "
                            f"(사라짐={missing} 생김={added} 달라짐={changed})")
        left = backups_left(root)
        check(left == [], f"{label}: 보관소가 남았다: {left}")


# --- 반례 ---------------------------------------------------------------------

def case_root_swap(consumer, scope):
    """지문 대조가 끝난 **뒤**, root 를 붙들기 직전에 root 이름을 바꿔치기한다.

    이 자리가 위험한 이유는 대상 지문이 이미 통과했기 때문이다. 바꿔치기된 root 아래에서
    상대 경로는 새 디렉터리 안에서 다시 성립하거나 전부 없어진다 — 어느 쪽도 대상 지문으로는
    보이지 않는다. root 를 여는 쪽이 계획의 기준과 대조해야만 잡힌다.
    """
    label = f"root-swap({scope})"
    plan = _plan.build(consumer.project, scope, environ=consumer.environ)
    if not check(plan.write_targets(), f"{label}: 쓰기 대상이 없어 주입이 성립하지 않는다"):
        return
    swap_target = consumer.global_root if scope == _plan.SCOPE_GLOBAL else consumer.project
    if not check(swap_target in plan.root_baseline, f"{label}: 바꿔칠 root 가 기준에 없다"):
        return
    outside = consumer.outside()
    moved = os.path.join(consumer.root, f"real-root-{scope}")
    before = {root: snapshot(root) for root in plan.root_baseline}
    linked = []

    def swap():
        shutil.move(swap_target, moved)
        linked.append(link_directory(swap_target, outside))

    hook = StepHook("roots", swap)
    outcome = run_plan(plan, trace=hook)
    if not check(hook.fired, f"{label}: 주입 자리(roots)에 도달하지 못했다"):
        return
    if not check(linked and linked[0], f"{label}: 디렉터리 링크를 만들지 못했다"):
        return
    check(outcome == "uninstall.boundary_changed",
          f"{label}: 바꿔치기된 root 를 그 이름으로 판정하지 않았다: {outcome}")
    assert_outside_untouched(label, outside)
    check(snapshot(moved) == before[swap_target],
          f"{label}: 옮겨 둔 원래 root 가 변했다")
    for root, mark in before.items():
        if root != swap_target:
            check(snapshot(root) == mark, f"{label}: 다른 scope 의 root 가 변했다")


def case_ancestor_before_execution(consumer):
    """실행 **전에** 상위 이름을 바꿔 둔다. 계획 층이 경계를 보는 자리다."""
    label = "ancestor-before-execution"
    consumer.seed_registration()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    outside = consumer.outside()
    claude = os.path.join(consumer.project, ".claude")
    moved = os.path.join(consumer.root, "real-claude")
    shutil.move(claude, moved)
    if not check(link_directory(claude, outside), f"{label}: 링크를 만들지 못했다"):
        return
    outcome = run_plan(plan)
    check(outcome in ("uninstall.boundary_changed", "uninstall.fingerprint_changed"),
          f"{label}: 바꿔치기된 경계에서 멈추지 않았다: {outcome}")
    assert_outside_untouched(label, outside)
    check(os.path.isfile(os.path.join(moved, "settings.json")), f"{label}: 원본이 사라졌다")


def _ancestor_swap_case(consumer, label, at, occurrence=1):
    """상위 디렉터리 이름을 지정한 단계에서 바깥 링크로 바꿔치기한다.

    ## 무엇을 단언하는가

    예전에는 이 주입을 **탐지해서** 멈췄다. 그 탐지는 경로로 조상을 훑는 것이었고, 부모를
    이미 붙든 뒤에 경로로 묻는 것은 그 자체가 위험하다 — 상위가 바뀐 순간 그 답은 이미 다른
    디렉터리에 대한 답이다.

    지금은 **결속이 그 질문을 무의미하게 만든다.** 이름이 어떻게 바뀌든 우리가 여는 것은
    승인 시점에 확인한 그 객체이고, 공격자가 바꿔 놓은 이름이 가리키는 곳은 열리지 않는다.
    그래서 "멈췄는가" 가 아니라 **"엉뚱한 것을 건드렸는가"** 를 본다.
    """
    settings = consumer.seed_registration()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    if not check(settings in plan.write_targets(), f"{label}: STRIP 대상이 잡히지 않았다"):
        return
    outside = consumer.outside()
    claude = os.path.dirname(settings)
    moved = os.path.join(consumer.root, "real-claude")
    linked = []

    def swap():
        shutil.move(claude, moved)
        linked.append(link_directory(claude, outside))
        consumer.unapproved(moved)

    hook = StepHook(at, swap, occurrence=occurrence)
    outcome = run_plan(plan, trace=hook)
    if not check(hook.fired, f"{label}: 주입 자리({at})에 도달하지 못했다"):
        return
    if not check(linked and linked[0], f"{label}: 디렉터리 링크를 만들지 못했다"):
        return
    check(outcome != f"uninstall.rollback_failed", f"{label}: 되돌리기까지 실패했다")
    assert_outside_untouched(label, outside)
    check(os.path.isfile(os.path.join(moved, "not-in-plan.txt")),
          f"{label}: 계획에 없던 파일을 지웠다")
    check(backups_left(moved) == [], f"{label}: 보관소가 남았다: {backups_left(moved)}")


def case_ancestor_after_root_pin(consumer):
    """root 를 붙든 **뒤**, 대상을 붙들기 전에 상위 이름을 바꾼다."""
    _ancestor_swap_case(consumer, "ancestor-after-root-pin", "prepare")


def case_ancestor_after_first_backup(consumer):
    """첫 backup **직후** 상위 이름을 바꾼다."""
    _ancestor_swap_case(consumer, "ancestor-after-first-backup", "backup", occurrence=2)


def case_strip_leaf_replaced_by_link(consumer):
    """`STRIP` 대상 leaf 를 링크로 바꾼다.

    `STRIP` 은 파일 **내용**을 다시 쓴다. leaf 가 링크로 바뀌었는데 따라가면 그 링크가
    가리키는 남의 파일을 고치게 된다. `DELETE` 는 링크 자체만 옮기므로 이 위반이 아니다.
    """
    label = "strip-leaf-replaced-by-link"
    settings = consumer.seed_registration()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    if not check(settings in plan.write_targets(), f"{label}: STRIP 대상이 잡히지 않았다"):
        return
    outside = consumer.outside()
    victim = os.path.join(outside, "victim.txt")
    before = snapshot(consumer.project)
    linked = []

    def swap():
        os.unlink(settings)
        linked.append(link_file(settings, victim))

    hook = StepHook("prepare", swap)
    outcome = run_plan(plan, trace=hook)
    if not check(hook.fired, f"{label}: 주입 자리에 도달하지 못했다"):
        return
    if not check(linked and linked[0], f"{label}: 파일 링크를 만들지 못했다"):
        return
    check(outcome == "uninstall.boundary_changed",
          f"{label}: 링크로 바뀐 leaf 를 그 이름으로 판정하지 않았다: {outcome}")
    with open(victim, encoding="utf-8") as handle:
        check(handle.read() == "someone else's file\n", f"{label}: 남의 파일을 고쳤다")
    check(backups_left(consumer.project) == [], f"{label}: 보관소가 남았다")
    # 주입으로 만든 링크만 다르고 나머지는 그대로여야 한다.
    after = snapshot(consumer.project)
    rel = os.path.relpath(settings, consumer.project)
    check({k: v for k, v in after.items() if k != rel}
          == {k: v for k, v in before.items() if k != rel},
          f"{label}: 링크 교체 외의 변화가 남았다")


def case_backup_name_collision(consumer):
    """보관소 이름을 미리 선점해 둔다. 덮어쓰면 그 파일의 주인은 그것을 잃는다."""
    label = "backup-name-collision"
    settings = consumer.seed_registration()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    before = {consumer.project: snapshot(consumer.project)}
    planted = []

    def plant(original):
        def hook(journal, path):
            if path == settings and not planted:
                target = journal._backup_path(path)
                with open(target, "w", encoding="utf-8") as handle:
                    handle.write("someone else was here\n")
                planted.append(target)
            return original(journal, path)
        return hook

    with patched("stage_write", plant):
        outcome = run_plan(plan)
    if not check(planted, f"{label}: 선점할 자리에 도달하지 못했다"):
        return
    check(outcome is not None, f"{label}: 선점된 보관소 이름 위에 그대로 진행했다")
    with open(planted[0], encoding="utf-8") as handle:
        check(handle.read() == "someone else was here\n", f"{label}: 선점된 파일을 덮어썼다")
    os.unlink(planted[0])
    assert_restored(label, before)


def case_truncated_write_is_detected(consumer):
    """새 파일이 **잘려 쓰인 채 성공**한 것처럼 만든다. 검증이 잡고 되돌려야 한다.

    쓰기가 성공했다고 보고하는 것과 의도대로 됐다는 것은 다른 말이다. 잘린 채 통과하면 그
    파일이 사용자의 host 설정일 때 우리가 남긴 것은 남의 데이터를 자른 결과다.
    """
    label = "truncated-write-detected"
    settings = consumer.seed_registration()
    with open(settings, "rb") as handle:
        original_bytes = handle.read()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    before = {consumer.project: snapshot(consumer.project)}
    fired = []

    def truncate(original):
        def writing(path, body, mode):
            if path == settings and not fired:
                fired.append(True)
                return original(path, body[: max(1, len(body) // 2)], mode)
            return original(path, body, mode)
        return writing

    with backend_patched("write_new", truncate):
        outcome = run_plan(plan)
    if not check(fired, f"{label}: 주입 자리에 도달하지 못했다"):
        return
    check(outcome is not None, f"{label}: 잘린 결과를 성공으로 통과시켰다")
    check(not str(outcome).startswith("uninstall.rollback_failed"),
          f"{label}: 되돌리기까지 실패했다: {outcome}")
    assert_restored(label, before)
    with open(settings, "rb") as handle:
        check(handle.read() == original_bytes, f"{label}: 원본 bytes 가 다르다")


def case_partial_write_then_io_failure(consumer):
    """파일을 만든 **뒤** I/O 실패를 낸다.

    ## 허용되는 결과가 둘이다

    되돌리기는 대상 자리에 자기가 모르는 파일이 있으면 복원을 멈춘다 — 안전한 기본값이다.
    그래서 계약이 요구하는 것은 "언제나 완전 복구" 가 아니라 **둘 중 하나**다.

    - 완전 복구: 원본 bytes·권한이 그대로 돌아오고 보관소가 남지 않는다
    - 정확한 미확정 보고: `uninstall.rollback_failed` 로 끝나되, 원본이 보고된 보관소에
      **손상 없이** 남아 있어 사용자가 되찾을 수 있다

    조용히 성공하거나, 원본을 잃거나, 어디 있는지 말하지 않는 것만이 위반이다.
    """
    label = "partial-write-then-io-failure"
    settings = consumer.seed_registration()
    with open(settings, "rb") as handle:
        original_bytes = handle.read()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    before = {consumer.project: snapshot(consumer.project)}
    fired = []

    def truncate(original):
        def failing(path, body, mode):
            if path == settings and not fired:
                fired.append(True)
                original(path, body[: max(1, len(body) // 2)], mode)
                raise OSError("injected I/O failure after the new file was created")
            return original(path, body, mode)
        return failing

    with backend_patched("write_new", truncate):
        outcome = run_plan(plan)
    if not check(fired, f"{label}: 주입 자리에 도달하지 못했다"):
        return
    check(outcome is not None, f"{label}: I/O 실패를 성공으로 통과시켰다")
    if str(outcome).startswith("uninstall.rollback_failed"):
        # 미확정 보고 경로. 원본이 보관소에 손상 없이 남아 있어야 한다.
        recovered = [os.path.join(folder, name)
                     for folder, _dirs, files in os.walk(consumer.project)
                     for name in files
                     if name.startswith(".sage-install-backup-")
                     and name.endswith("settings.json")]
        if not check(recovered, f"{label}: 되돌리지 못했는데 원본을 어디 뒀는지 말하지 않았다"):
            return
        with open(recovered[0], "rb") as handle:
            check(handle.read() == original_bytes,
                  f"{label}: 보관소의 원본이 손상됐다")
        return
    assert_restored(label, before)
    with open(settings, "rb") as handle:
        check(handle.read() == original_bytes, f"{label}: 원본 bytes 가 다르다")


def case_base_exception_during_mutation(consumer):
    """Ctrl-C 에 해당하는 `BaseException` 을 변경 도중에 낸다.

    `Exception` 만 잡으면 이것이 rollback 을 통째로 건너뛴다. 취소는 정상적인 사용자
    행동이고, 정상적인 행동이 원자성을 깨면 그 계약은 없는 것이다.
    """
    label = "base-exception-during-mutation"
    consumer.seed_registration()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    before = {consumer.project: snapshot(consumer.project)}
    state = {"n": 0}

    def interrupt(original):
        def hook(journal, path):
            state["n"] += 1
            if state["n"] > 2:
                raise KeyboardInterrupt()
            return original(journal, path)
        return hook

    with patched("stage_remove_tree", interrupt):
        outcome = run_plan(plan)
    check(state["n"] > 2, f"{label}: 주입 자리에 도달하지 못했다")
    check(outcome == "KeyboardInterrupt", f"{label}: 취소가 그대로 올라오지 않았다: {outcome}")
    assert_restored(label, before)


def case_global_fails_after_project(consumer):
    """project 를 성공적으로 바꾼 **뒤** global 에서 실패시킨다.

    `--all` 은 두 root 를 하나의 transaction 으로 다룬다. 한쪽만 커밋하면 사용자는 "절반
    지워진" 상태를 손으로 수습해야 하고, 그 상태가 어떤 모양인지 문서에 적을 수도 없다.
    """
    label = "global-fails-after-project"
    plan = _plan.build(consumer.project, _plan.SCOPE_ALL, environ=consumer.environ)
    roots = list(plan.root_baseline)
    if not check(len(roots) == 2, f"{label}: 두 root 가 잡히지 않았다: {roots}"):
        return
    before = {root: snapshot(root) for root in roots}
    touched = {"project": 0, "global": 0}

    def fail_on_global(original):
        def hook(journal, path):
            if _plan.within_root(consumer.global_root, path):
                touched["global"] += 1
                raise OSError("injected failure in the global scope")
            touched["project"] += 1
            return original(journal, path)
        return hook

    with patched("stage_remove_tree", fail_on_global):
        outcome = run_plan(plan)
    check(touched["project"] > 0, f"{label}: project 변경이 일어나기 전에 실패했다")
    check(touched["global"] > 0, f"{label}: global 주입 자리에 도달하지 못했다")
    check(outcome is not None and not outcome.startswith("uninstall.rollback_failed"),
          f"{label}: 판정이 계약 밖이다: {outcome}")
    assert_restored(label, before)


def case_output_verification_failure(consumer):
    """쓰기는 끝났지만 결과 검증이 실패한다. commit 전이므로 전부 되돌아와야 한다."""
    label = "output-verification-failure"
    consumer.seed_registration()
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    before = {consumer.project: snapshot(consumer.project)}
    fired = []

    def refuse(original):
        def hook(journal):
            fired.append(True)
            raise _tx.InstallDriftError("injected output verification failure")
        return hook

    with patched("verify_outputs", refuse):
        outcome = run_plan(plan)
    check(fired, f"{label}: 검증 자리에 도달하지 못했다")
    check(outcome is not None and not outcome.startswith("uninstall.rollback_failed"),
          f"{label}: 판정이 계약 밖이다: {outcome}")
    assert_restored(label, before)


def case_cleanup_failure_after_commit(consumer):
    """commit **뒤** 뒷정리가 실패한다. 명령은 성공이고, 남은 경로를 보고해야 한다.

    둘을 한 단계로 묶으면 뒷정리 실패가 "명령 실패" 로 보고되는데, 그때 실제 디스크는
    요청대로 지워진 상태다. 사용자는 실패했다고 듣고 다시 실행하고, 두 번째 실행은 이미
    없는 것을 찾는다.
    """
    label = "cleanup-failure-after-commit"
    plan = _plan.build(consumer.project, _plan.SCOPE_PROJECT)
    marker = os.path.join(consumer.project, "docs", "sage_harness")
    fired = []

    def refuse(original):
        def hook(journal):
            fired.append(True)
            journal._committed = True
            return [f"{path}: injected" for path, backup in journal._entries if backup]
        return hook

    with patched("commit", refuse):
        try:
            result = _exec.execute(plan)
        except BaseException as exc:
            FAILURES.append(f"{label}: 뒷정리 실패가 명령 실패로 올라왔다: {exc!r}")
            return
    check(fired, f"{label}: 뒷정리 자리에 도달하지 못했다")
    check(bool(result.leftover_backups), f"{label}: 못 치운 보관소를 보고하지 않았다")
    check(not os.path.isdir(marker), f"{label}: 뒷정리 실패가 제거를 되돌렸다")


CASES = (
    ("root-swap-after-fingerprint", "root swapped after fingerprint (project)",
     lambda c: case_root_swap(c, _plan.SCOPE_PROJECT), {"host": "codex",
                                                        "skill_scope": "global"}),
    ("root-swap-after-fingerprint", "root swapped after fingerprint (global)",
     lambda c: case_root_swap(c, _plan.SCOPE_GLOBAL), {"host": "codex",
                                                       "skill_scope": "global"}),
    ("root-swap-after-fingerprint", "root swapped after fingerprint (all)",
     lambda c: case_root_swap(c, _plan.SCOPE_ALL), {"host": "codex",
                                                    "skill_scope": "global"}),
    ("ancestor-swap-before-execution", "ancestor swapped before execution",
     case_ancestor_before_execution, {}),
    ("ancestor-swap-after-root-pin", "ancestor swapped after root pin",
     case_ancestor_after_root_pin, {}),
    ("ancestor-swap-after-first-backup", "ancestor swapped after first backup",
     case_ancestor_after_first_backup, {}),
    ("strip-leaf-replaced-by-link", "STRIP leaf replaced by a link",
     case_strip_leaf_replaced_by_link, {}),
    ("backup-name-collision", "backup name pre-empted",
     case_backup_name_collision, {}),
    ("partial-write-then-io-failure", "truncated write is detected",
     case_truncated_write_is_detected, {}),
    ("partial-write-then-io-failure", "partial write then I/O failure",
     case_partial_write_then_io_failure, {}),
    ("base-exception-during-mutation", "BaseException during mutation",
     case_base_exception_during_mutation, {}),
    ("global-fails-after-project", "global fails after project succeeded",
     case_global_fails_after_project, {"host": "codex", "skill_scope": "global"}),
    ("output-verification-failure", "output verification failure",
     case_output_verification_failure, {}),
    ("cleanup-failure-after-commit", "cleanup failure after commit",
     case_cleanup_failure_after_commit, {}),
)


def main():
    probe = Consumer("probe")
    try:
        if probe.install.returncode != 0:
            print("install failed:", probe.install.stderr[-2000:])
            return 1
        supported = _fs.capability((probe.project,)).supported
    finally:
        probe.cleanup()

    print("== uninstall race smoke ==")
    if not supported:
        # 지원 범위 밖이다. 주입할 자리가 없으므로 돌지 않았다고 **적는다** — 돌지 않은
        # 검사를 통과로 세면 그 방어는 있다고 말할 수 없다.
        print("  out of supported range: the product refuses to mutate here, "
              "so no injection is possible")
        print("  0 injections executed")
        if REQUIRE_MUTATION:
            print("FAIL: SAGE_UNINSTALL_REQUIRE_MUTATION is set but the backend refused; "
                  "this job must exercise real mutation")
            return 1
        return 0

    for index, (injection, label, case, options) in enumerate(CASES, start=1):
        before = len(FAILURES)
        consumer = Consumer(f"case{index}", **options)
        try:
            if consumer.install.returncode != 0:
                FAILURES.append(f"{label}: install failed")
            else:
                case(consumer)
                EXECUTED.append(injection)
        finally:
            consumer.cleanup()
        mark = "ok " if len(FAILURES) == before else "FAIL"
        print(f"  [{index:>2}/{len(CASES)}] {mark} {label}")

    # **요구 목록과 실행 목록을 대조한다.** 기대 건수를 따로 적으면 두 벌이 되고, 반례가
    # 조용히 빠져도 남은 것들은 여전히 통과한다.
    missing = [name for name in REQUIRED_INJECTIONS if name not in EXECUTED]
    if missing:
        FAILURES.append(f"요구된 주입이 실행되지 않았다: {missing}")
    unknown = [name for name in set(EXECUTED) if name not in REQUIRED_INJECTIONS]
    if unknown:
        FAILURES.append(f"요구 목록에 없는 주입 이름: {sorted(unknown)}")
    if not EXECUTED:
        FAILURES.append("주입이 한 건도 실행되지 않았다")

    if FAILURES:
        print()
        for note in FAILURES:
            print(f"  - {note}")
        return 1
    print(f"  {len(EXECUTED)} injections executed covering "
          f"{len(REQUIRED_INJECTIONS)} required seams, "
          f"0 mutations outside the project")
    return 0


if __name__ == "__main__":
    sys.exit(main())
