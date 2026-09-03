"""승인된 계획만 실행하는 층.

## 왜 자기 프리미티브를 갖지 않는가

이 층은 lock 도 backup 도 지문도 **직접 만들지 않는다.** 전부 `install_transaction` 의 것을
쓴다. 처음에는 uninstall 전용으로 따로 만들었는데, 그것이 바로 이 사이클이 roster 에서 고쳤던
실수와 같은 모양이었다 — 같은 일을 하는 것이 두 벌이면 언젠가 갈라지고, 갈라진 뒤에는 아무도
모른다.

lock 에서는 갈라짐이 즉시 위험이다. `install` 이 `DestinationLock` 을 잡고 uninstall 이 자기
lock 파일을 잡으면, 둘은 서로를 **전혀 막지 못한 채** 각자 "잠갔다" 고 믿는다. 같은 destination
을 한쪽이 배치하는 동안 다른 쪽이 지운다. 그래서 공식 writer 는 모두 같은 권위를 통과한다.

## 왜 계획을 다시 읽지 않는가

이 층은 무엇을 지울지 **정하지 않는다.** 계획의 기준(`plan.baseline`) 에 없는 경로는 어떤
이유로도 열지 않는다. 실행 중에 대상을 추가할 수 있으면 "계획을 보여 주고 동의를 받는다" 는
계약이 무의미해진다 — 사용자가 동의한 것과 실제로 지운 것이 달라진다.

## 왜 옮기고 나서 지우는가

삭제는 되돌릴 수 없다. 그래서 실제로 하는 일은 **같은 부모 안의 사설 backup 으로 이동**이고,
마지막 검증까지 통과한 뒤에야 backup 을 버린다. 중간 어디서 실패해도 되돌릴 것이 디스크에
남아 있다.

`STRIP` 도 같은 방식이다. 원본을 먼저 옆으로 **치우고** 빈 자리에 새로 만든다. 경로에 대고
덮어쓰면 검사와 쓰기 사이에 leaf 가 링크로 바뀌었을 때 남의 파일을 고치게 되는데, 원본이 이미
치워진 자리에 **배타 생성**으로 만들면 그 창 자체가 없다 — 무엇이든 이미 있으면 만들기가
실패하기 때문이다. 그 배타 생성을 어느 호출로 얻는지는 backend 가 알고, 이 층은 모른다.

## 왜 한 단위로 되돌리는가

`--all` 은 project 와 global 을 하나의 명령으로 다룬다. 한쪽만 커밋하면 사용자는 "절반 지워진"
상태를 손으로 수습해야 하고, 그 상태가 어떤 모양인지 문서에 적을 수도 없다. 그래서 journal 이
하나이고, 어느 scope 에서 실패하든 **양쪽을 함께** 되돌린다. 그 journal 은 첫 mutation 전에
양쪽 scope 를 모두 알고 있어야 한다 — 나중에 알게 되면 그때는 이미 한쪽을 건드린 뒤다.

## commit 과 cleanup 은 다른 일이다

`commit` 은 **되돌리지 않기로 정하는 순간**이다. 여기까지 오면 요청한 변경은 전부 적용되었고
검증도 끝났다. `cleanup` 은 그 뒤에 보관소를 치우는 뒷정리다.

둘을 한 단계로 묶으면 뒷정리 실패가 "명령 실패" 로 보고되는데, 그때 실제 디스크는 **요청대로
지워진 상태**다. 사용자는 실패했다고 듣고 다시 실행하고, 두 번째 실행은 이미 없는 것을 찾는다.
그래서 cleanup 실패는 결과를 바꾸지 않고 **남은 경로를 보고**한다.

## OS 를 모르는 층

파일을 **어떻게** 안전하게 만지는가는 이 파일에 없다. `uninstall_fs` 뒤의 backend 가 안다.
둘이 한 파일에 있으면 두 번째 OS 를 더하는 순간 단계 순서 코드 안에 분기가 흩어지고, 그 분기
하나가 빠진 자리가 곧 경로 기반 fallback 이 된다.

## lock 은 왜 실행 층에만 있는가

lock 을 잡는 것은 **쓰기**다. `--check` 가 잠그면 읽기 전용 계약이 깨진다. 그래서 계획 층은
어떤 root 를 잠가야 하는지만 말하고(`plan.lock_roots()`), 실제로 잠그는 일은 여기서 한다.
"""
import os
import stat

from sage import install_transaction as _tx
from sage import uninstall_fs as _fs
from sage import uninstall_plan as _plan
from sage import uninstall_shared as _shared

# 기준을 뜨는 일은 **읽기**라 계획 층이 한다. 여기서는 이름만 다시 내보내 기존 호출자가 같은
# 함수를 보게 한다 — 구현이 두 벌이 되면 두 기준이 생긴다.
fingerprint = _plan.fingerprint


class RollbackFailed(Exception):
    """되돌리기까지 실패했다. 보존한 경로를 사용자에게 넘겨야 하는 유일한 경우."""

    def __init__(self, message, preserved_paths, reasons=()):
        super().__init__(message)
        self.preserved_paths = tuple(preserved_paths)
        # 왜 되돌리지 못했는지도 함께 든다. 경로만 주고 이유를 감추면, 사용자는 무엇을 어떻게
        # 수습해야 하는지 모른 채 디렉터리 하나를 받는다.
        self.reasons = tuple(reasons)


class ExecutionResult:
    """실행이 끝나고 남은 사실. 무엇을 처리했고 무엇을 못 치웠는가.

    `leftover_backups` 가 비어 있지 않아도 명령은 성공이다. 요청한 변경은 전부 적용되었고,
    남은 것은 우리가 만든 임시 보관소뿐이다 — 그 사실을 숨기지 않고 경로로 넘긴다.
    """

    __slots__ = ("processed", "leftover_backups")

    def __init__(self, processed, leftover_backups=()):
        self.processed = tuple(processed)
        self.leftover_backups = tuple(leftover_backups)

    def __iter__(self):
        """예전 호출자가 처리된 action 묶음으로 읽던 자리를 그대로 둔다."""
        return iter(self.processed)

    def __len__(self):
        return len(self.processed)


# --- 열린 부모에 결속하기 -----------------------------------------------------
#
# 결속을 **어떻게** 얻는지는 OS 의 일이라 이 파일에 없다. `uninstall_fs` 뒤의 backend 가
# 안다. 여기 있는 것은 journal 의 seam 을 그 backend 로 넘기는 얇은 층뿐이다.
#
# 이 파일에 OS 분기가 남으면 두 번째 OS 를 더할 때마다 분기가 늘고, 늘어난 분기 중 하나가
# 빠진 자리가 곧 경로 기반 fallback 이 된다. 그 fallback 이 이 명령이 막으려는 사고다.

class _PinnedTransaction(_tx.InstallTransaction):
    """모든 변경을 **첫 mutation 전에 고정한 부모** 기준으로 수행하는 journal.

    backup 은 원본과 같은 부모에 만들어지므로 rename·생성·삭제가 전부 한 디렉터리 안에서
    일어난다. 그래서 부모 하나만 붙들면 이 명령의 모든 변경이 결속된다.

    되돌리기도 같은 부모를 쓴다. 되돌릴 때만 경로로 돌아가면, 실패한 순간이 곧 공격이
    성립하는 순간이 된다 — 되돌리기는 이미 무언가 잘못된 뒤에 도는 코드다.
    """

    def __init__(self, *args, backend=None, **kwargs):
        super().__init__(*args, **kwargs)
        # 결속 없이 만들어진 journal 은 어떤 변경도 거부한다. 조용히 경로로 떨어뜨리면
        # 결속이 없다는 사실이 결과에 드러나지 않는다.
        self.backend = backend if backend is not None else _fs.NullBackend()

    def pin(self, root, path):
        self.backend.pin(root, path)

    def close(self):
        self.backend.close()

    def _replace(self, source, target):
        self.backend.replace(source, target)

    def _remove(self, path):
        return self.backend.remove_tree(path)

    def _probe(self, path):
        if not self.backend.pinned(path):
            return super()._probe(path)
        return self.backend.probe(path)

    def _measure(self, path, form):
        if not self.backend.pinned(path):
            return super()._measure(path, form)
        return self.backend.measure(path, form)

    def read_bytes(self, path):
        if not self.backend.pinned(path):
            return super().read_bytes(path)
        return self.backend.read_bytes(path)

    def write_new(self, path, body, mode):
        if not self.backend.pinned(path):
            return super().write_new(path, body, mode)
        return self.backend.write_new(path, body, mode)

    def listdir(self, path):
        if not self.backend.pinned(path):
            return super().listdir(path)
        return self.backend.listdir(path)

    def _guard_ancestors(self, root, path):
        """조상 판정을 **결속으로 대신한다.** 붙든 뒤에는 경로로 다시 묻지 않는다.

        `pin()` 은 root 부터 성분을 하나씩 **링크를 따라가지 않는 방식으로** 열어 내려간다.
        그 하강이 성공했다는 것이 곧 "그 순간 조상에 링크가 없었다" 는 증명이고, 얻은
        handle 은 그 디렉터리를 **붙든다** — 이후 이름이 어떻게 바뀌어도 우리의 작업은 원래
        디렉터리로 간다.

        여기서 다시 `os.lstat` 로 조상을 훑으면 그 증명을 버리고 경로로 되돌아가는 것이다.
        상위가 그 사이 바뀌었다면 그 답은 다른 디렉터리에 대한 답이고, 그 답으로 통과시키면
        붙든 결속이 아무 일도 하지 않은 것이 된다.

        결속이 없는 경로는 원래 판정을 그대로 쓴다.
        """
        if self.backend.pinned(path):
            return
        return super()._guard_ancestors(root, path)

    def _ensure_parents(self, path):
        """**제거는 부모를 만들지 않는다.**

        install 은 없는 부모를 만들며 배치하지만, 이 층이 여는 것은 계획이 승인한 대상뿐이고
        그 부모는 이미 붙들려 있다. 여기서 경로로 `mkdir` 하면 상위가 바뀐 뒤 프로젝트 밖에
        디렉터리를 만들 수 있다 — 이 명령이 절대 하면 안 되는 일이다.
        """
        if self.backend.pinned(path):
            return
        return super()._ensure_parents(path)


def _acquire_all(roots):
    """정렬된 순서로 전부 잡거나, 하나도 잡지 않는다.

    `install`·`generate` 와 **같은** `DestinationLock` 을 쓴다. 다른 lock 을 쓰면 두 명령이
    서로를 막지 못한 채 각자 잠갔다고 믿는다.

    중간에 실패하면 그때까지 잡은 것을 **역순으로** 놓는다. 절반 잡은 채 올라가면 그 lock 은
    아무도 놓지 않는다. 순서를 값으로 고정하는 것은 교착을 없애기 위해서다 — 두 실행이 서로
    다른 순서로 집으면 상대의 첫 lock 을 물고 영원히 기다린다.
    """
    held = []
    for root in sorted(roots):
        lock = _tx.DestinationLock(root)
        try:
            lock.acquire()
        except (_tx.InstallBusyError, _tx.InstallDriftError, OSError):
            for earlier in reversed(held):
                earlier.release()
            raise ValueError("uninstall.lock_busy")
        held.append(lock)
    return held


def _strip_outcome(path, raw, sage_commands, host=None):
    """공유 파일 bytes 하나의 판정. **계획 층과 글자 그대로 같은 함수를 부른다.**

    실행 층이 자기 파서를 들면 계획이 "뺄 수 있다" 고 판정한 문서를 실행이 다르게 읽는 날이
    오고, 그날 화면은 "제거했다" 고 말하는데 파일은 그대로다.
    """
    if path.endswith(".gitignore"):
        return _shared.classify_gitignore_bytes(raw)
    return _shared.classify_host_bytes(raw, sage_commands, host)


def _host_of(path):
    return "codex" if path.endswith("hooks.json") else "claude"


def execute(plan, environ=None, trace=None):
    """계획을 실행하고 `ExecutionResult` 를 돌려준다.

    실패하면 되돌린 뒤 예외를 올린다. 되돌리기까지 실패하면 `RollbackFailed` 로 보존 경로를
    함께 넘긴다 — 그때 사용자에게 줄 수 있는 유일하게 정직한 것은 "여기 있다" 는 사실이다.

    ## 단계 순서가 계약이다

    ```
    capability → lock → fingerprint → prepare → recheck → backup → verify
               → commit → cleanup → unlock
    ```

    `capability` 가 맨 앞인 이유는 지원하지 않는 환경에서 lock 을 잡으면 아무것도 바꾸지 않을
    명령이 다른 실행을 막기 때문이다. `lock` 이 그다음인 이유는 그 뒤 모든 검사가 **잠긴 상태에서** 이뤄져야 의미가 있기 때문이다.
    잠그기 전에 확인하면 확인과 쓰기 사이가 그대로 경쟁 구간으로 남는다. `prepare` 는 첫
    mutation 전에 **양쪽 scope** 의 journal 과 경계를 세우는 자리다. `recheck` 는 계획을 잠그기
    전에 세웠기 때문에 있다 — 후보를 열기 직전에 경계를 다시 본다.

    `trace` 는 검사가 단계 **순서**를 읽기 위한 자리다. 순서가 계약인데 그 순서를 밖에서
    확인할 수 없으면, 구현이 순서를 바꿔도 아무도 모른다.
    """
    def step(name):
        if trace is not None:
            trace.append(name)

    # 부모 결속이 없는 환경에서는 **아무것도 바꾸지 않는다.** 이 명령은 상위 디렉터리 교체
    # 만으로 프로젝트 밖 파일을 만들 수 있고, 그 위험은 "알려진 한계" 로 넘길 성질이 아니다 —
    # 되돌릴 수 없는 쪽으로 틀리는 명령이기 때문이다. 계획(`--check`)은 읽기라 그대로
    # 동작하므로 사용자는 무엇이 지워질지 볼 수 있다.
    #
    # 결속을 **어떻게** 얻는지는 backend 가 안다. 이 층은 얻었는지만 묻는다.
    step("capability")
    backend = _fs.backend_for(plan.lock_roots())

    # 같은 경로를 두 번 주장하는 계획은 실행하지 않는다. 계획 층이 이미 막지만, 그 검사가
    # 언젠가 다른 분기를 놓치면 여기서 잡혀야 한다 — **lock 도 잡기 전, mutation 전**이다.
    # 중복은 "지운다" 와 "보존한다" 가 같은 파일에 대해 동시에 참이라는 뜻이고, 그 상태에서
    # 실행하면 보존한다고 보고한 파일을 지운다.
    if _plan.conflicting_actions(plan.actions):
        backend.close()
        raise ValueError("uninstall.action_conflict")

    step("lock")
    try:
        locks = _acquire_all(plan.lock_roots())
    except BaseException:
        backend.close()
        raise
    try:
        return _execute_locked(plan, step, backend)
    except _fs.MutationBackendError as exc:
        # **native 실패를 계약된 이름으로 옮기는 단 하나의 자리.** 여기가 없으면 backup 이름
        # 충돌도 경계 변화도 화면에서는 "실행 실패" 하나로 접힌다. 이름은 예외가 이미 들고
        # 있으므로 이 층은 OS 를 알 필요가 없다.
        raise ValueError(exc.diagnostic) from None
    finally:
        step("unlock")
        for lock in reversed(locks):
            lock.release()


def _execute_locked(plan, step, backend):
    # 승인된 대상은 **계획이 만들어질 때 뜬 기준**이다. 실행 직전에 다시 뜨면 그 사이에 바뀐
    # 것을 기준으로 삼게 되어, 확인 화면이 열려 있는 동안 사용자가 고친 파일이 그대로 지워진다.
    step("fingerprint")
    expected = plan.baseline
    approved = set(expected)
    findings = _tx.verify_captured(expected)
    if findings:
        raise ValueError("uninstall.fingerprint_changed")

    # journal 하나가 양쪽 scope 를 다룬다. write root 를 **첫 mutation 전에** 모두 넘기는 것이
    # 요점이다 — 나중에 알려 주면 그때는 이미 한쪽을 건드린 뒤라, 되돌릴 범위가 반쪽이다.
    # write root 를 **여기서 한 번 열고 계획의 기준과 대조한다.** capability probe 가 확인한
    # handle 은 이미 닫혔고, 확인과 사용이 다른 handle 이면 그 사이가 경쟁 구간이다 — root
    # 이름이 junction 으로 바뀌면 확인은 옛 디렉터리에, 변경은 새 디렉터리에 일어난다.
    # 이 handle 은 rollback·cleanup 이 끝날 때까지 살아 있다.
    step("roots")
    roots = plan.lock_roots()
    try:
        backend.open_roots({root: plan.root_baseline[root] for root in roots})
    except KeyError as exc:
        # 계획이 기준을 뜨지 않은 root 는 승인된 root 가 아니다.
        backend.close()
        raise ValueError("uninstall.target_outside_plan") from exc
    except _fs.MutationBackendError as exc:
        backend.close()
        raise ValueError(exc.diagnostic) from None
    except OSError as exc:
        backend.close()
        raise ValueError("uninstall.boundary_changed") from exc
    except BaseException:
        backend.close()
        raise

    step("prepare")
    pending = [action for action in plan.actions
               if action.kind in (_plan.DELETE, _plan.STRIP)]
    # journal 의 단계별 재검증에서 **빈 부모 정리 대상은 뺀다.** 그 디렉터리들은 우리가
    # 자식을 지우면서 스스로 바뀌므로, 넣어 두면 매 단계 "계획 이후 바뀌었다" 고 스스로를
    # 고발한다. 이들의 기준은 위 `fingerprint` 단계에서 이미 한 번 대조했고, 실제로 비었는지는
    # 지우기 직전에 다시 본다 — 그 둘이 이 대상에 필요한 전부다.
    prune_paths = {a.path for a in pending if a.group == "prune"}
    journal = _PinnedTransaction(
        expected={path: mark for path, mark in expected.items() if path not in prune_paths},
        write_roots=roots, backend=backend)
    try:
        for action in pending:
            if action.path not in approved:
                # 계획 밖 경로. 여기 오면 실행 층이 스스로 대상을 늘린 것이다.
                raise ValueError("uninstall.target_outside_plan")
            journal._guard_path(action.path)
            # 부모를 **먼저** 붙든다. 첫 mutation 전에 전부 열어 두므로, 그 뒤 상위 이름이
            # 어떻게 바뀌든 우리의 모든 작업은 지금 확인한 그 디렉터리로 간다.
            journal.pin(plan.root_for(action), action.path)
            # 보관소 자리 확인도 **붙든 뒤** 결속된 눈으로 본다. 경로로 보면 상위가 바뀐
            # 순간 "비어 있다" 는 답이 다른 디렉터리에서 나온다.
            if journal._probe(journal._backup_path(action.path)):
                raise ValueError("uninstall.backup_collision")
    except _fs.MutationBackendError as exc:
        journal.close()
        raise ValueError(exc.diagnostic) from None
    except OSError as exc:
        journal.close()
        raise ValueError("uninstall.boundary_changed") from exc
    except BaseException:
        # `Exception` 만 잡으면 Ctrl-C 가 여기를 그냥 지나간다. 사용자가 취소한 것뿐인데
        # 열어 둔 fd 가 남는다.
        journal.close()
        raise

    processed = []
    committed = False
    try:
      try:
        for action in pending:
            # 계획은 잠그기 **전에** 세웠다. 그 사이에 경계가 바뀌었으면 지금 여는 경로는
            # 우리가 판정한 그 경로가 아니다. 열기 직전에 다시 본다.
            #
            # 계획 층의 `candidate_block` 을 여기서 부르지 않는다. 그 관문은 **경로로**
            # 조상과 leaf 를 훑고, 이 시점의 우리는 이미 부모를 붙들었다 — 붙든 뒤에 경로로
            # 다시 물으면 상위가 바뀐 순간 그 답이 다른 디렉터리에 대해 나온다.
            #
            # 그래서 같은 질문을 둘로 나눠 각각 옳은 도구로 묻는다.
            #   소속  — `within_root` 는 문자열만 본다. 파일시스템과 무관하므로 안전하다
            #   경계  — leaf 의 종류는 journal 의 결속된 지문으로 본다
            #
            # 조상이 그 사이 바뀌었는지는 **묻지 않는다.** 붙든 뒤에는 그 질문의 답을 경로로
            # 밖에 얻을 수 없고, 경로로 얻은 답은 이미 다른 디렉터리에 대한 답이다. 대신
            # 결속이 그 질문을 무의미하게 만든다 — 이름이 어떻게 바뀌든 우리가 여는 것은
            # 승인 시점에 확인한 그 객체이고, 승인되지 않은 객체는 어떤 경우에도 열리지 않는다.
            step("recheck")
            if not _plan.within_root(plan.root_for(action), action.path):
                raise ValueError("uninstall.boundary_changed")
            observed = journal._measure(action.path, "path")
            if action.kind == _plan.STRIP and observed[0] != "file":
                # `STRIP` 은 파일 **내용**을 다시 쓴다. leaf 가 링크로 바뀌었으면 그 링크가
                # 가리키는 남의 파일을 고치게 된다. `DELETE` 는 링크 자체만 옮기므로
                # leaf 가 링크인 것이 위반이 아니다.
                raise ValueError("uninstall.boundary_changed")

            step("backup")
            if action.kind == _plan.DELETE:
                if action.group == "prune":
                    # 계획은 예상이었다. 실행 시점에 무엇이 남아 있으면 정리하지 않는다 —
                    # 그 사이에 사용자가 파일을 놓았을 수 있고, 그건 우리 것이 아니다.
                    if not _effectively_empty(journal, action.path):
                        journal._expected.pop(action.path, None)
                        continue
                if not journal.stage_remove_tree(action.path):
                    journal._expected.pop(action.path, None)
                    continue
            else:
                host = _host_of(action.path)
                outcome = _strip_outcome(action.path, journal.read_bytes(action.path),
                                         _plan.canonical_commands(host), host)
                if not outcome.strippable:
                    # 계획은 뺄 수 있다고 판정했는데 지금은 아니다. 조용히 넘기면 화면은
                    # "제거했다" 고 말하고 파일은 그대로다 — 하지 않은 일을 했다고 보고하는 것이
                    # 이 명령이 절대 하면 안 되는 일이다. 계획과 디스크가 어긋났으니 멈추고,
                    # 여기까지 한 것을 **전부 되돌린다.**
                    raise ValueError("uninstall.strip_not_applicable")
                body = outcome.body
                # 권한도 **결속된 눈으로** 읽는다. 경로로 읽으면 상위가 바뀐 순간 남의 파일
                # 권한을 우리 파일에 씌운다.
                current = journal._measure(action.path, "path")
                if current[0] != "file":
                    raise ValueError("uninstall.boundary_changed")
                mode = current[1]
                # 원본을 먼저 치우고 빈 자리에 만든다. 경로에 덮어쓰지 않으므로 leaf 가
                # 그 사이 symlink 로 바뀌어도 따라갈 대상이 없다.
                journal.stage_write(action.path)
                journal.write_new(action.path, body, mode)
                journal.record_output(action.path)
            processed.append(action)

        step("verify")
        for action in processed:
            # 결과 확인도 결속된 눈으로 본다. 경로로 보면 상위가 바뀐 뒤 "없다" 는 답이
            # 다른 디렉터리에서 나오고, 그 답으로 "지웠다" 고 보고하게 된다.
            if action.kind == _plan.DELETE and journal._probe(action.path):
                raise ValueError("uninstall.delete_not_effective")
            if action.kind == _plan.STRIP:
                # STRIP 은 파일이 남는 것이 정상이라 존재만으로는 아무것도 확인되지 않는다.
                # 우리가 뺀 것이 정말 빠졌는지 다시 읽는다 — 쓰고 나서 확인하지 않으면
                # "썼다" 와 "의도대로 됐다" 가 같은 말이 된다.
                host = _host_of(action.path)
                leftover = _strip_outcome(action.path, journal.read_bytes(action.path),
                                          _plan.canonical_commands(host), host)
                if leftover.strippable or leftover.damage:
                    raise ValueError("uninstall.strip_not_effective")
        journal.verify_outputs()

        # 여기가 되돌리지 않기로 정하는 지점이다. 이 뒤에 무엇이 실패해도 사용자가 요청한
        # 변경은 이미 전부 적용되었고 검증도 끝났다.
        step("commit")
        committed = True
      except BaseException:
        # **`BaseException` 이어야 한다.** `Exception` 만 잡으면 Ctrl-C(`KeyboardInterrupt`)가
        # rollback 을 통째로 건너뛴다. 그때 디스크에는 원본이 사라진 자리와 숨은 backup 만
        # 남는다 — 취소는 정상적인 사용자 행동이고, 정상적인 행동이 원자성을 깨면 그 계약은
        # 없는 것이다.
        if committed:
            raise
        step("rollback")
        errors = journal.rollback()
        if errors:
            raise RollbackFailed("uninstall.rollback_failed",
                                 [journal._backup_path(a.path) for a in pending],
                                 errors) from None
        raise
    except BaseException:
        journal.close()
        raise

    step("cleanup")
    try:
        return ExecutionResult(processed, _cleanup(journal))
    finally:
        journal.close()


def _effectively_empty(journal, path):
    """지금 비어 있는가. **우리가 방금 옆으로 치운 것은 없는 것으로 센다.**

    backup 은 원본과 **같은 부모**에 만들어진다(그래야 이동이 원자적이다). 그래서 자식을 치운
    직후의 부모에는 그 backup 이 남아 있고, 그것을 남의 파일로 세면 부모는 영원히 "비지 않은"
    상태가 된다 — 우리가 만든 흔적 때문에 우리가 정리를 못 한다.

    남이 놓은 것은 그대로 센다. 구별의 근거는 이 실행의 token 이고, 다른 실행의 backup 은
    다른 token 을 갖는다.
    """
    if journal._measure(path, "path")[0] != "dir":
        return False
    ours = f".sage-install-backup-{journal._token}-"
    return not [name for name in journal.listdir(path) if not name.startswith(ours)]


def _cleanup(journal):
    """보관소를 치우고, **못 치운 실제 경로**를 돌려준다.

    commit 뒤의 실패는 명령 실패가 아니다 — 요청한 변경은 이미 적용됐다. 그렇다고 예외를
    삼키고 빈 목록을 내면 안 된다. 그러면 디스크에는 backup 이 남았는데 화면에는 아무것도
    남지 않았다고 나오고, 사용자는 치울 것이 있다는 사실조차 모른다. **숨기는 것과 실패로
    올리는 것은 둘 다 틀렸고**, 옳은 것은 결과를 유지한 채 경로를 그대로 말하는 것뿐이다.
    """
    try:
        errors = list(journal.commit())
    except BaseException:
        # commit 자체가 터졌으면 journal 이 아는 backup 을 우리가 직접 센다.
        journal._committed = True
        errors = []
    leftover = []
    for path, backup in journal._entries:
        if backup is None:
            continue
        # **여기만 경로로 묻는다.** 이 목록은 사용자가 그 경로에 가서 치울 것들이고, 답해야
        # 하는 질문이 "붙든 객체가 아직 있는가" 가 아니라 **"그 경로에 아직 무언가 보이는가"**
        # 다. 부모째 옮겨진 보관소는 fd 로는 보이지만 사용자가 갈 수 있는 자리에는 없다 —
        # 그것을 보고하면 없는 경로를 치우라고 말하는 것이 된다. commit 뒤라 mutation 도 없다.
        if os.path.lexists(backup) and backup not in leftover:
            leftover.append(backup)
    for note in errors:
        # commit 이 문자열로 보고한 것 중 위에서 못 본 것도 함께 낸다.
        name = note.split(":", 1)[0]
        if name and name not in leftover and os.path.lexists(name):
            leftover.append(name)
    return tuple(leftover)
