"""OS 별 안전한 파일 조작의 경계.

## 왜 경계가 필요한가

`uninstall_executor` 는 두 가지를 알고 있었다 — **무슨 순서로 제거하는가**와 **파일을 어떻게
안전하게 만지는가**. 첫 번째는 OS 와 무관하고 두 번째는 전적으로 OS 의 것이다.

둘이 한 파일에 있으면 두 번째 OS 를 더하는 순간 단계 순서 코드 안에 `if os.name == "nt"` 가
흩어진다. 그 분기 하나가 빠진 자리가 곧 경로 기반 fallback 이고, 경로 기반 fallback 은 이
명령이 막으려던 바로 그 사고다.

## 이 층이 판단하지 않는 것

backend 는 "이 경로를 지워도 되는가" 를 **묻지 않는다.** 그 답은 `uninstall_plan` 하나가
갖는다. backend 가 아는 것은 이미 승인된 상대 이름을 고정된 부모 아래에서 조작하는 방법뿐이다.
정책이 backend 로 새면 OS 마다 정책이 두 벌이 되고, 두 벌은 언젠가 갈라진다.

## capability 는 왜 불리언 하나가 아닌가

"안 된다" 만 남으면 사용자는 다음에 무엇을 고쳐야 하는지 모른다. 그래서 어느 기능이 없는지를
들고 다닌다. 이 값은 화면과 `--json` 에 그대로 실릴 수 있어야 하므로 절대 경로도 OS 원문
오류 메시지도 담지 않는다.
"""
import os

BACKEND_POSIX = "posix"
BACKEND_WINDOWS = "windows"
BACKEND_NONE = "none"

# probe 가 묻는 기능들. 이름을 값으로 고정해 두는 이유는 화면·`--json`·검사가 같은 이름을
# 보게 하기 위해서다. 어느 하나가 거짓이면 `supported` 는 거짓이다.
PRIMITIVES = ("relative_open", "reparse_no_follow", "handle_rename", "handle_delete",
              "directory_enumeration", "identity_match")


class NativeFailure(ValueError):
    """실행 층이 올리는 계약 진단 + **그 진단이 접어 버린 native 사실**.

    진단 하나만 올리면 어느 API 가 어떤 code 로 실패했는지가 사라진다. 그 정보는 예외가
    이미 들고 있고 경로도 OS 원문도 없는데, 옮기는 자리에서 버려져 왔다 — 그래서 CI 로그에
    "지원되지 않는 플랫폼" 만 남고 원인은 원격 머신 안에 갇혔다.

    싣는 것은 API 이름·code 종류·정수 code 뿐이다. 경로와 OS 메시지는 여기에도 오지 않는다.
    """

    def __init__(self, diagnostic, native=None):
        super().__init__(diagnostic)
        self.native = native


class MutationBackendError(OSError):
    """backend 가 낸 실패 하나. `diagnostic` 에 **기존 uninstall code** 를 들고 다닌다.

    ## 왜 예외가 code 를 들고 다니는가

    변환을 호출 지점마다 하면 같은 상황이 자리마다 다른 이름으로 나온다. 한 곳에서 변환하면
    그 한 곳이 빠졌을 때 전부 `execution_failed` 로 접힌다 — 실제로 그렇게 접혀서, backup
    이름 충돌도 경계 변화도 화면에서는 "실행 실패" 하나로 보였다.

    그래서 **낼 때 이름을 붙이고**, 실행 층은 그 이름을 옮기기만 한다. `OSError` 를 상속하는
    것은 journal 의 rollback 이 `OSError` 를 모아 보고하기 때문이다 — 되돌리는 중의 실패가
    이름 없는 예외로 새면 rollback 루프가 거기서 끊긴다.
    """

    @property
    def native(self):
        """경로 없는 사실만. `operation` 은 API 이름, `error_code` 는 정수다."""
        return {"operation": getattr(self, "op", None),
                "error_kind": "nt" if getattr(self, "ntstatus", False) else "win32",
                "error_code": getattr(self, "code", None)}


    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


class MutationCapability:
    """지금 이 프로세스에서 안전한 변경이 가능한가, 안 된다면 무엇이 없는가."""

    __slots__ = ("backend", "os_supported", "local_volume", "filesystem", "primitives",
                 "failure_code", "identity_source")

    def __init__(self, backend, *, os_supported=True, local_volume=True, filesystem=None,
                 primitives=None, failure_code=None, identity_source=None):
        self.backend = backend
        self.os_supported = bool(os_supported)
        self.local_volume = bool(local_volume)
        self.filesystem = filesystem
        self.primitives = dict(primitives or {name: False for name in PRIMITIVES})
        self.failure_code = failure_code
        # 어느 호출로 만든 `(dev, ino)` 가 이 환경의 `os.lstat` 과 같은지. 추측이 아니라
        # probe 가 실제로 대조해서 정한 값이다. POSIX 에서는 의미가 없어 `None` 이다.
        self.identity_source = identity_source

    @property
    def supported(self):
        if self.backend == BACKEND_NONE or self.failure_code:
            return False
        if not (self.os_supported and self.local_volume):
            return False
        return all(self.primitives.get(name, False) for name in PRIMITIVES)

    def as_json(self):
        """`--json` 에 실을 수 있는 형태. 경로도 OS 원문 메시지도 들어가지 않는다."""
        return {
            "backend": self.backend,
            "supported": self.supported,
            "os_supported": self.os_supported,
            "local_volume": self.local_volume,
            "filesystem": self.filesystem,
            "primitives": {name: bool(self.primitives.get(name, False))
                           for name in PRIMITIVES},
            "failure_code": self.failure_code,
        }


class MutationBackend:
    """고정된 부모 아래에서만 파일을 만지는 방법. 무엇을 만질지는 모른다.

    구현은 `pin()` 이 성공한 경로에 대해서만 조작을 허용해야 한다. 결속이 없을 때 경로로
    되돌아가는 길을 남기면, 조건 하나가 어긋나는 날 조용히 그쪽으로 떨어진다.
    """

    name = BACKEND_NONE

    def open_roots(self, marks):
        """write root 를 **한 번 열고 계획의 기준과 대조한 뒤 그 handle 을 끝까지 유지한다.**

        capability probe 가 확인한 handle 과 실제로 변경에 쓰는 handle 이 다르면, 그 둘
        사이가 그대로 경쟁 구간이다. probe 가 "이 root 는 안전하다" 고 말한 순간과 첫 변경
        사이에 root 이름이 junction 으로 바뀌면, 확인은 옛 디렉터리에 대해 이뤄지고 변경은
        새 디렉터리에서 일어난다.

        그래서 확인과 사용은 **같은 handle** 이어야 하고, 그 handle 은 lock 을 잡은 뒤에
        열려야 하며(잠그기 전에 열면 확인과 변경 사이가 다시 열린다), rollback·cleanup 이
        끝날 때까지 살아 있어야 한다.

        `marks` 는 `{root: 계획이 뜬 기준}` 이다. 대조에 실패하면 어떤 변경도 하지 않는다.
        """
        raise NotImplementedError

    def pin(self, root, path):
        raise NotImplementedError

    def pinned(self, path):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def replace(self, source, target):
        raise NotImplementedError

    def remove_tree(self, path):
        raise NotImplementedError

    def probe(self, path):
        raise NotImplementedError

    def measure(self, path, form):
        raise NotImplementedError

    def read_bytes(self, path):
        raise NotImplementedError

    def write_new(self, path, body, mode):
        raise NotImplementedError

    def listdir(self, path):
        raise NotImplementedError


class NullBackend(MutationBackend):
    """결속을 하나도 갖지 않은 backend. 어떤 변경도 거부한다.

    journal 을 결속 없이 만드는 자리(주로 검사)를 위한 것이다. 여기서 조작을 조용히 경로로
    떨어뜨리면, 결속이 없다는 사실이 결과에 드러나지 않는다.
    """

    name = BACKEND_NONE

    def open_roots(self, marks):
        raise ValueError("uninstall.unsafe_platform")

    def pin(self, root, path):
        raise ValueError("uninstall.unsafe_platform")

    def pinned(self, path):
        return False

    def close(self):
        return None

    def _refuse(self, what, path):
        from sage import install_transaction as _tx
        raise _tx.InstallDriftError(f"unpinned parent for {what}: {path}")

    def replace(self, source, target):
        self._refuse("rename", source)

    def remove_tree(self, path):
        self._refuse("remove", path)


def _posix_module():
    from sage import uninstall_posix_fs
    return uninstall_posix_fs


def _windows_module():
    from sage import uninstall_windows_fs
    return uninstall_windows_fs


def capability(roots=()):
    """이 환경에서 쓸 수 있는 backend 를 조사한다. **아무것도 바꾸지 않는다.**

    `roots` 를 받는 이유는 Windows 의 판정이 볼륨에 달려 있기 때문이다 — 같은 머신에서도
    프로젝트가 NTFS 이고 `$CODEX_HOME` 이 네트워크 드라이브일 수 있다. 하나라도 지원 범위
    밖이면 전체가 미지원이다. 절반만 지울 수 있다는 것은 이 명령에서 지원이 아니다.
    """
    if os.name == "nt":
        return _windows_module().probe_capability(roots)
    return _posix_module().probe_capability(roots)


def backend_for(roots):
    """write root 묶음에 대한 backend 를 만든다. 지원 불가면 진단 code 로 올린다.

    선택이 **한 곳**인 것이 요점이다. 호출자가 스스로 OS 를 묻기 시작하면 그 물음이 늘어나고,
    늘어난 물음 중 하나가 빠진 날 그 자리가 fallback 이 된다.
    """
    cap = capability(roots)
    if not cap.supported:
        raise ValueError(cap.failure_code or "uninstall.unsafe_platform")
    if cap.backend == BACKEND_WINDOWS:
        return _windows_module().WindowsBackend(cap)
    return _posix_module().PosixBackend(cap)
