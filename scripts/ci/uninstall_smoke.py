#!/usr/bin/env python3
"""`sage uninstall` 소비자 계약을 **세 OS · 세 Python** 에서 검증하는 smoke.

## 검사 내용은 OS 마다 다르다

Linux·macOS 는 실제로 설치하고 제거한다. Windows 는 상위 디렉터리 교체 경쟁을 막을 수단
(`dir_fd`)이 없어 제품이 mutation 을 **거부**하므로, 거기서는 계획이 도는 것과 실행이 거부되고
아무것도 바뀌지 않는 것을 검사한다.

"세 OS 에서 같은 검사를 돌린다" 고 적으면 Windows 에서 제거가 검증된 것처럼 읽힌다. 검사가
무엇을 증명했는지를 정확히 적는 것이 이 스크립트가 지는 책임의 절반이다. 안전 구현은 EH-30 이다.

## 왜 bash 를 쓰지 않는가

`wheel_smoke.sh` 가 이미 소비자 matrix 를 돌지만 bash 스크립트라 Windows 러너에서 돌지 않는다.
검사 도구가 검사 대상보다 요구사항이 많으면 그 환경은 영원히 미검증으로 남는다 — 그래서 이
스크립트는 순수 Python 이고, 표준 라이브러리 밖을 쓰지 않는다.

## 무엇을 보는가

지워졌는지가 아니라 **말하지 않은 것이 남았는가** 를 본다. 조용히 남는 자산이 이 명령의 가장
흔한 실패 방식이고, OS 마다 다르게 틀리는 것도 대개 경로·권한이라 그 자리에서 드러난다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

# 이 플랫폼에서 안전한 mutation 이 가능한가. 불가능하면 제품이 **실행을 거부**하는 것이
# 정상이고, smoke 는 그 거부를 검사한다 — 거부를 실패로 세면 올바른 동작이 빨간불이 된다.
from sage.uninstall_executor import _PINNING as SAFE_MUTATION  # noqa: E402


def inherited_import_paths():
    """HOME 을 바꿔도 잃으면 안 되는 부모의 import 경로.

    ## 왜 필요한가

    `$CODEX_HOME` 기본값(`~/.codex`)을 밟으려면 `HOME` 을 fixture 로 돌려야 한다. 그런데 의존성이
    **user-site**(`~/.local/lib/...`)에만 설치돼 있으면, HOME 을 돌리는 순간 자식 프로세스가 그
    경로를 잃고 `ModuleNotFoundError` 로 죽는다. 검사가 검사 대상이 아니라 **자기 격리 방식**
    때문에 실패하는 것이고, 그 실패는 제품 결함처럼 보인다.

    homebrew·시스템 site-packages 에 설치된 머신에서는 이 문제가 보이지 않는다. 그래서 "내
    머신에서는 된다" 가 정확히 여기서 생긴다.

    저장소 자신은 넣지 않는다 — wheel 단독 여부를 흐리기 때문이다. 넘기는 것은 HOME 아래
    또는 이미 `PYTHONPATH` 에 있던 경로뿐이다.
    """
    home = os.path.realpath(os.path.expanduser("~"))
    repo = os.path.realpath(REPO)
    kept = []

    def keep(entry):
        if not entry:
            return
        full = os.path.realpath(entry)
        if full == repo or full.startswith(repo + os.sep):
            return
        if not os.path.isdir(full) or full in kept:
            return
        kept.append(full)

    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        keep(entry)
    for entry in sys.path:
        if not entry:
            continue
        full = os.path.realpath(entry)
        if full == home or full.startswith(home + os.sep):
            keep(entry)
    return kept


IMPORT_PATHS = inherited_import_paths()


def run(*args, cwd=None, env=None):
    return subprocess.run([sys.executable, "-m", "sage", *args], cwd=cwd or REPO,
                          env=env or os.environ.copy(), capture_output=True, text=True)


def fail(message, result=None):
    print(f"FAIL: {message}")
    if result is not None:
        print(result.stdout)
        print(result.stderr)
    sys.exit(1)


def fixture_base():
    """fixture 전용 private root. **공유 temp 로 되돌아가지 않는다.**

    `/tmp` 는 누구나 쓸 수 있어 남이 이름을 먼저 만들어 둘 수 있고, macOS 의 `$TMPDIR` 은
    symlink 아래에 있다. 경계를 보는 검사가 symlink 아래에서 돌면 통과의 의미가 흐려진다.

    `tempfile.gettempdir()` 로 내려가는 fallback 을 두지 않는 이유는, 아무도 환경변수를
    지정하지 않으므로 그 fallback 이 사실상 유일한 경로가 되기 때문이다. 규칙이 문서에만
    남는다. 지정이 없으면 저장소 옆의 정해진 자리를 쓴다.
    """
    override = os.environ.get("SAGE_TEST_TMPDIR")
    base = os.path.realpath(override or os.path.join(os.path.dirname(REPO), ".sage-fixtures"))
    os.makedirs(base, exist_ok=True)
    if os.name == "posix":
        os.chmod(base, 0o700)
    shared = os.path.realpath(tempfile.gettempdir())
    if not override and (base == shared or base.startswith(shared + os.sep)):
        fail(f"default fixture base is under the shared temp: {base}")
    return base


def tree(root):
    found = set()
    for folder, dirs, files in os.walk(root):
        for name in dirs + files:
            found.add(os.path.relpath(os.path.join(folder, name), root))
    return found


# 경로 변형. 되돌릴 수 없는 명령에서 경로 처리는 OS 마다 다르게 틀리므로, 정상 사용 조건인
# 공백과 비ASCII 를 검사 대상으로 둔다. "우리 CI 경로에서는 된다" 는 증거가 아니다.
PATH_SHAPES = (
    ("plain", "proj", "codex"),
    ("spaces", "my project dir", "codex home dir"),
    ("unicode", "프로젝트-테스트", "코덱스-홈"),
    ("mixed", "프로 젝트 dir", "코덱스 home"),
)

# `CODEX_HOME` 의 두 경로. 기본값(unset → `~/.codex`)과 명시 지정은 서로 다른 코드 경로다.
CODEX_MODES = ("custom", "default")


def main():
    failures = 0
    for label, project_name, codex_name in PATH_SHAPES:
        for mode in CODEX_MODES:
            print(f"--- {label} / CODEX_HOME={mode} ---")
            run_case(label, project_name, codex_name, mode)
    print(f"OK  ({sys.platform}, python {sys.version.split()[0]}) "
          f"-- {len(PATH_SHAPES) * len(CODEX_MODES)} path/CODEX_HOME combinations")
    return failures


def run_case(label, project_name, codex_name, codex_mode):
    root = os.path.realpath(tempfile.mkdtemp(prefix=f"uninstall-smoke-{label}-",
                                             dir=fixture_base()))
    project = os.path.join(root, project_name)
    codex_home = os.path.join(root, codex_name)
    os.makedirs(project)
    os.makedirs(codex_home)
    env = os.environ.copy()
    if codex_mode == "custom":
        env["CODEX_HOME"] = codex_home
    else:
        # 기본 경로(`~/.codex`)를 밟되 사용자 홈을 건드리지 않도록 HOME 을 fixture 로 돌린다.
        # HOME 을 돌리면 user-site 가 사라지므로, 부모가 쓰던 import 경로를 명시로 넘긴다 —
        # 그러지 않으면 검사가 제품이 아니라 자기 격리 방식 때문에 죽는다.
        env.pop("CODEX_HOME", None)
        env["HOME"] = root
        env["USERPROFILE"] = root
        if IMPORT_PATHS:
            existing = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
            env["PYTHONPATH"] = os.pathsep.join(
                existing + [p for p in IMPORT_PATHS if p not in existing])
    steps = 0
    total = 8 if SAFE_MUTATION else 4

    def step(label_text):
        nonlocal steps
        steps += 1
        print(f"  [{steps}/{total}] {label_text}")

    try:
        step("install a consumer")
        installed = run("install", "--host", "claude", "--dest", project, env=env)
        if installed.returncode != 0:
            fail("install failed", installed)

        step("--check --json is machine readable and read-only")
        before = tree(project)
        checked = run("uninstall", "--dest", project, "--check", "--json", env=env)
        if checked.returncode not in (0, 1):
            fail("--check exit code", checked)
        try:
            payload = json.loads(checked.stdout)
        except ValueError:
            fail("--check --json did not emit JSON", checked)
        for key in ("scope", "status", "exit_code", "deleted", "preserved", "notices"):
            if key not in payload:
                fail(f"--check --json missing {key}", checked)
        if payload.get("executed") is not False:
            fail("--check reported itself as executed", checked)
        if tree(project) != before:
            fail("--check changed the project")
        sys.path.insert(0, REPO)
        from sage.install_transaction import DestinationLock
        probe = DestinationLock(project)
        probe.acquire()   # --check 가 잠갔다면 여기서 막힌다
        probe.release()

        step("executing --json without --yes is a usage error")
        mixed = run("uninstall", "--dest", project, "--json", env=env)
        if mixed.returncode != 2:
            fail("prompt and JSON were mixed", mixed)

        step("non-interactive without --yes refuses and changes nothing")
        refused = run("uninstall", "--dest", project, env=env)
        if refused.returncode != 2:
            fail("non-interactive run did not block", refused)
        if tree(project) != before:
            fail("blocked run still changed the project")

        if not SAFE_MUTATION:
            # 이 플랫폼은 상위 디렉터리 교체 경쟁을 막을 수단이 없다. 실행은 **거부**되어야
            # 하고, 거부는 아무것도 바꾸지 않아야 한다. 계획은 읽기라 위에서 이미 확인했다.
            refusal = run("uninstall", "--dest", project, "--yes", env=env)
            if refusal.returncode != 2:
                fail("unsafe platform did not refuse to mutate", refusal)
            if tree(project) != before:
                fail("a refused run still changed the project")
            print("  refused to mutate on this platform (expected) -- "
                  "Windows mutation-refusal contract verified")
            return

        step("a held lock blocks the run")
        # install·generate 와 **같은** lock 권위를 쓴다. 다른 lock 이면 두 명령이 서로를
        # 막지 못한 채 각자 잠갔다고 믿는다.
        sys.path.insert(0, REPO)
        from sage.install_transaction import DestinationLock
        held = DestinationLock(project)
        held.acquire()
        try:
            busy = run("uninstall", "--dest", project, "--yes", env=env)
            if busy.returncode != 2:
                fail("a held install lock did not block uninstall", busy)
        finally:
            held.release()

        step("plan is recorded, then executed")
        planned = run("uninstall", "--dest", project, "--check", "--json", env=env)
        plan = json.loads(planned.stdout)
        reported = set()
        for entry in plan["preserved"] + plan["stripped"]:
            # `path` 는 이미 **정화된 project 상대 경로**다(FR-H11). 여기서 다시 relpath 를
            # 걸면 상대 경로를 절대 경로 기준으로 잘라 `../../..` 가 나오고, 그 값은 어떤
            # 생존 파일과도 맞지 않는다 — 첫 조합부터 실패했다.
            rel = entry["path"]
            if os.path.isabs(rel):
                fail(f"plan reported an absolute path: {rel}", planned)
            reported.add(rel)
            parent = os.path.dirname(rel)
            while parent:
                reported.add(parent)
                parent = os.path.dirname(parent)
        removed = run("uninstall", "--dest", project, "--yes", env=env)
        if removed.returncode not in (0, 1):
            fail("uninstall failed", removed)

        step("nothing survives that was not reported")
        survivors = tree(project)
        unreported = sorted(survivors - reported)
        if unreported:
            fail(f"unreported residue: {unreported}", removed)
        released = DestinationLock(project)
        released.acquire()   # 끝난 뒤 lock 이 남아 있으면 여기서 막힌다
        released.release()
        if any(name.startswith(".sage-install-backup-") for name in survivors):
            fail("a backup store was left behind")

        step("a second run is not an error")
        again = run("uninstall", "--dest", project, "--yes", env=env)
        if again.returncode not in (0, 1):
            fail("second run was not idempotent", again)

    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
