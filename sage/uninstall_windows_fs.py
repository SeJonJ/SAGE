"""Windows 결속 구현 — 고정한 부모 **핸들** 아래에서만 파일을 열고 만든다.

## 왜 경로로 하지 않는가

POSIX 에서는 부모를 `dir_fd` 로 붙들면 이후 누가 상위 이름을 바꿔도 작업이 원래 디렉터리로
간다. Windows 의 Python `os` 표면에는 같은 조합이 없고, 그래서 지금까지 이 명령은 실제
변경을 **거부**해 왔다.

`CreateFileW`·`MoveFileExW` 를 경로로 부르고 작업 직전에 identity 를 다시 확인하는 방법은
기각했다. 확인과 변경이 서로 다른 호출이라 그 사이에 상위 디렉터리가 junction 으로 바뀔 수
있고, 그 창이 정확히 프로젝트 밖에 파일이 생기는 자리다. 재검사는 창을 좁힐 뿐 없애지 못한다.

`NtCreateFile` 은 `OBJECT_ATTRIBUTES.RootDirectory` 에 **연 핸들**을 주고 그 아래 상대 이름을
열거나 만들 수 있다. `FILE_OPEN_REPARSE_POINT` 를 함께 주면 reparse point 를 따라가지 않고 그
객체 자체를 연다. 이 둘이 POSIX 의 `dir_fd` + `O_NOFOLLOW` 와 같은 책임 경계를 만든다.

## 왜 성분을 하나씩 여는가

상대 경로 전체를 한 번에 넘기면 커널이 중간 성분을 알아서 따라가고, `FILE_OPEN_REPARSE_POINT`
는 **마지막 성분에만** 적용된다. `O_NOFOLLOW` 가 마지막 성분만 보는 것과 같은 함정이다.
그래서 성분마다 열고, 열 때마다 reparse 속성을 본다.

## 이 파일이 지지 않는 책임

무엇을 지울지 판단하지 않는다. 정책·roster·journal 은 전부 기존 층의 것이다. 여기 있는 것은
"이미 승인된 상대 이름을 고정된 부모 아래에서 어떻게 만지는가" 뿐이다.

## ctypes offset 을 상수로 적지 않는 이유

구조체 offset 이나 크기를 손으로 적으면 정상 경로는 통과하고 특정 이름 길이나 특정 필드에서만
틀린다. 그런 실패는 조용하다. 그래서 offset 은 언제나 `ctypes` 가 계산한 값을 쓰고, 그 값
자체를 검사 대상으로 둔다. `WCHAR` 를 `ctypes.c_wchar` 로 두지 않는 것도 같은 이유다 — 그
크기는 플랫폼마다 다르고(Windows 2, 그 외 4), 그러면 구조체 배치가 검사 환경에서만 맞는다.
"""
import ctypes
import hashlib
import os
import stat
import sys

from sage import install_transaction as _tx
from sage import uninstall_fs as _fs

# --- 기본 형 ------------------------------------------------------------------
#
# `ctypes.wintypes` 는 Windows 에서만 import 된다. 이 모듈은 구조체 배치를 어디서나 검사할 수
# 있어야 하므로 필요한 형을 직접 고정한다. 폭을 명시한 형만 쓴다 — `c_long` 은 Windows 에서
# 4바이트이고 LP64 에서 8바이트라, 그대로 쓰면 배치가 환경을 탄다.
HANDLE = ctypes.c_void_p
PVOID = ctypes.c_void_p
BOOLEAN = ctypes.c_ubyte
USHORT = ctypes.c_uint16
ULONG = ctypes.c_uint32
DWORD = ctypes.c_uint32
NTSTATUS = ctypes.c_int32
LARGE_INTEGER = ctypes.c_int64
ULONGLONG = ctypes.c_uint64
ULONG_PTR = ctypes.c_uint64
WCHAR = ctypes.c_uint16

INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class FILETIME(ctypes.Structure):
    # `FILETIME` 은 DWORD 둘이다. 8바이트 정수 하나로 두면 정렬이 4에서 8로 바뀌고, 그
    # 하나 때문에 뒤따르는 모든 필드의 offset 이 밀린다.
    _fields_ = [("dwLowDateTime", DWORD), ("dwHighDateTime", DWORD)]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", USHORT), ("MaximumLength", USHORT), ("Buffer", PVOID)]


class OBJECT_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Length", ULONG), ("RootDirectory", HANDLE), ("ObjectName", PVOID),
                ("Attributes", ULONG), ("SecurityDescriptor", PVOID),
                ("SecurityQualityOfService", PVOID)]


class IO_STATUS_BLOCK(ctypes.Structure):
    _fields_ = [("Pointer", PVOID), ("Information", ULONG_PTR)]


class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [("dwFileAttributes", DWORD), ("ftCreationTime", FILETIME),
                ("ftLastAccessTime", FILETIME), ("ftLastWriteTime", FILETIME),
                ("dwVolumeSerialNumber", DWORD), ("nFileSizeHigh", DWORD),
                ("nFileSizeLow", DWORD), ("nNumberOfLinks", DWORD),
                ("nFileIndexHigh", DWORD), ("nFileIndexLow", DWORD)]


class FILE_ID_INFO(ctypes.Structure):
    _fields_ = [("VolumeSerialNumber", ULONGLONG), ("FileId", ctypes.c_ubyte * 16)]


class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
    _fields_ = [("FileAttributes", DWORD), ("ReparseTag", DWORD)]


class FILE_BASIC_INFO(ctypes.Structure):
    _fields_ = [("CreationTime", LARGE_INTEGER), ("LastAccessTime", LARGE_INTEGER),
                ("LastWriteTime", LARGE_INTEGER), ("ChangeTime", LARGE_INTEGER),
                ("FileAttributes", DWORD)]


class FILE_DISPOSITION_INFO(ctypes.Structure):
    _fields_ = [("DeleteFile", BOOLEAN)]


class FILE_RENAME_INFO(ctypes.Structure):
    # 첫 필드는 `union { BOOLEAN ReplaceIfExists; DWORD Flags; }` 다. 넓은 쪽(DWORD)으로 두면
    # union 의 크기·정렬이 그대로 나오고, `ReplaceIfExists` 는 그 하위 바이트다.
    _fields_ = [("Flags", DWORD), ("RootDirectory", HANDLE),
                ("FileNameLength", DWORD), ("FileName", WCHAR * 1)]


class FILE_FULL_DIR_INFO(ctypes.Structure):
    _fields_ = [("NextEntryOffset", ULONG), ("FileIndex", ULONG),
                ("CreationTime", LARGE_INTEGER), ("LastAccessTime", LARGE_INTEGER),
                ("LastWriteTime", LARGE_INTEGER), ("ChangeTime", LARGE_INTEGER),
                ("EndOfFile", LARGE_INTEGER), ("AllocationSize", LARGE_INTEGER),
                ("FileAttributes", ULONG), ("FileNameLength", ULONG), ("EaSize", ULONG),
                ("FileName", WCHAR * 1)]


# --- 상수 ---------------------------------------------------------------------

DELETE = 0x00010000
SYNCHRONIZE = 0x00100000
FILE_READ_DATA = 0x0001
FILE_LIST_DIRECTORY = 0x0001
FILE_WRITE_DATA = 0x0002
FILE_TRAVERSE = 0x0020
FILE_READ_ATTRIBUTES = 0x0080
FILE_WRITE_ATTRIBUTES = 0x0100

FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
FILE_SHARE_DELETE = 0x00000004
SHARE_ALL = FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE

FILE_OPEN = 1
FILE_CREATE = 2

FILE_DIRECTORY_FILE = 0x00000001
FILE_SYNCHRONOUS_IO_NONALERT = 0x00000020
FILE_NON_DIRECTORY_FILE = 0x00000040
FILE_OPEN_FOR_BACKUP_INTENT = 0x00004000
FILE_OPEN_REPARSE_POINT = 0x00200000

OBJ_CASE_INSENSITIVE = 0x00000040

FILE_ATTRIBUTE_READONLY = 0x00000001
FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

# `FILE_INFO_BY_HANDLE_CLASS` 의 값들. 이름이 아니라 숫자가 계약이라 한자리에 모은다.
FileBasicInfo = 0
FileRenameInfo = 3
FileDispositionInfo = 4
FileAttributeTagInfo = 9
FileFullDirectoryInfo = 14
FileFullDirectoryRestartInfo = 15
FileIdInfo = 18

# **NT 쪽 class 번호는 Win32 와 다르다.** 같은 이름의 두 번호를 한자리에 두지 않으면 언젠가
# 한쪽 번호가 다른 쪽 API 로 간다.
FileRenameInformation = 10

STATUS_SUCCESS = 0x00000000
STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034
STATUS_OBJECT_NAME_COLLISION = 0xC0000035
STATUS_OBJECT_PATH_NOT_FOUND = 0xC000003A
STATUS_NOT_A_DIRECTORY = 0xC0000103
STATUS_FILE_IS_A_DIRECTORY = 0xC00000BA
STATUS_NOT_SUPPORTED = 0xC00000BB
STATUS_INVALID_PARAMETER = 0xC000000D
STATUS_ACCESS_DENIED = 0xC0000022
STATUS_SHARING_VIOLATION = 0xC0000043
STATUS_DELETE_PENDING = 0xC0000056

ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3
ERROR_ACCESS_DENIED = 5
ERROR_NO_MORE_FILES = 18
ERROR_SHARING_VIOLATION = 32
ERROR_FILE_EXISTS = 80
ERROR_INVALID_PARAMETER = 87
ERROR_ALREADY_EXISTS = 183
ERROR_NOT_SUPPORTED = 50

DRIVE_UNKNOWN = 0
DRIVE_NO_ROOT_DIR = 1
DRIVE_REMOVABLE = 2
DRIVE_FIXED = 3
DRIVE_REMOTE = 4
# 로컬로 인정하는 종류. `DRIVE_UNKNOWN` 을 여기 넣지 않는 것이 요점이다 — 확정하지 못한 것을
# 로컬로 세면 판정 실패가 곧 통과가 된다. 네트워크 매핑(`DRIVE_REMOTE`)과 CD/RAM 디스크는
# 이 사이클이 계약을 증명하지 않았다.
LOCAL_DRIVE_TYPES = frozenset({DRIVE_FIXED, DRIVE_REMOVABLE})

IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
IO_REPARSE_TAG_SYMLINK = 0xA000000C

_ABSENT_STATUS = (STATUS_OBJECT_NAME_NOT_FOUND, STATUS_OBJECT_PATH_NOT_FOUND,
                  STATUS_DELETE_PENDING)
_COLLISION_STATUS = (STATUS_OBJECT_NAME_COLLISION,)
# **`unsafe_platform` 으로 옮기는 status 집합은 없다.** capability 판정을 통과한 뒤의
# native 실패는 환경이 아니라 구현의 문제이고, 그 둘을 한 이름으로 접으면 고칠 수 있는
# 결함이 고칠 수 없는 한계처럼 보인다. 그 접힘이 이 사이클에서 실제로 일어났다.

_RESERVED_NAMES = frozenset(
    ["con", "prn", "aux", "nul"]
    + [f"com{n}" for n in range(1, 10)]
    + [f"lpt{n}" for n in range(1, 10)])


def to_diagnostic(error):
    """native 실패를 기존 uninstall 어휘로 옮긴다. 새 code 를 만들지 않는다.

    새 code 를 만들면 `diagnostic_contract`·i18n·복구 안내가 함께 늘고, 사용자는 OS 마다
    다른 이름의 같은 실패를 배우게 된다.

    ## `unsafe_platform` 은 여기서 나오지 않는다

    이 함수는 **capability 판정을 이미 통과한 뒤** 실행 중에 난 실패만 옮긴다. 그 실패를
    "이 플랫폼은 지원되지 않는다" 로 옮기면 구현 결함이 환경 한계의 옷을 입는다 — 사용자는
    고칠 수 있는 버그를 자기 환경 탓으로 읽고, 개발자는 초록이 아닌 화면을 환경 문제로
    넘긴다. 실제로 그 일이 일어났다. `INVALID_PARAMETER` 는 환경이 아니라 **호출자**가 틀린
    것이고, `NOT_SUPPORTED` 도 지원 판정 이후라면 같은 성격이다.

    `unsafe_platform` 은 `probe_capability` 가 **첫 mutation 전에** 환경 미지원을 확정한
    경우에만 쓴다. 그 경계는 지금 이 파일에서 딱 두 자리다 — probe 와 `nt_path()`.
    """
    code = error.code
    if error.ntstatus:
        if code in _COLLISION_STATUS:
            return "uninstall.backup_collision"
        if code in (STATUS_NOT_A_DIRECTORY, STATUS_FILE_IS_A_DIRECTORY):
            return "uninstall.boundary_changed"
        return "uninstall.execution_failed"
    if code in (ERROR_ALREADY_EXISTS, ERROR_FILE_EXISTS):
        return "uninstall.backup_collision"
    return "uninstall.execution_failed"


class WindowsMutationError(_fs.MutationBackendError):
    """native 실패 하나. **원문 메시지를 만들지 않는다.**

    Windows 오류 문자열에는 절대 경로가 붙고, 그것은 로그와 CI 출력으로 그대로 흘러간다.
    그래서 남기는 것은 API 이름과 정수 code 뿐이고, 사용자가 보는 것은 이 값이 옮겨진
    uninstall 진단 code 다.
    """

    def __init__(self, op, code, *, ntstatus=False):
        self.op = op
        self.code = code
        self.ntstatus = ntstatus
        # 이름을 **낼 때** 붙인다. 나중에 한 곳에서 붙이면 그 한 곳이 빠진 경로가 전부
        # `execution_failed` 로 접힌다.
        super().__init__(f"{op}:{'nt' if ntstatus else 'win32'}:{code:#x}",
                         to_diagnostic(self))


def validate_component(name):
    """상대 경로 성분 하나가 **성분인지** 본다. 아니면 거부한다.

    backend 에 닿기 전에 상위 층이 이미 걸러야 하지만, 여기서 한 번 더 거부한다. 이 값이
    커널에 그대로 가는 마지막 자리이고, 마지막 자리의 검사는 위층의 어떤 분기가 빠져도 남는다.
    """
    if not isinstance(name, str) or not name:
        raise ValueError("uninstall.boundary_changed")
    if name in (os.curdir, os.pardir):
        raise ValueError("uninstall.boundary_changed")
    if "\x00" in name or "/" in name or "\\" in name:
        raise ValueError("uninstall.boundary_changed")
    # `:` 는 드라이브 지정자이자 대체 데이터 스트림(ADS)의 구분자다. 이름 안에 있으면 우리가
    # 의도한 파일이 아니라 그 파일의 **다른 스트림**을 열게 된다.
    if ":" in name:
        raise ValueError("uninstall.boundary_changed")
    # 예약 device 이름은 파일이 아니라 장치를 연다. 확장자가 붙어도 마찬가지다.
    if name.split(".", 1)[0].strip().lower() in _RESERVED_NAMES:
        raise ValueError("uninstall.boundary_changed")
    # 끝의 공백·점은 Windows 가 조용히 잘라낸다. 잘린 뒤의 이름은 우리가 검사한 이름이 아니다.
    if name != name.rstrip(" ."):
        raise ValueError("uninstall.boundary_changed")
    return name


def nt_path(path):
    """로컬 드라이브 절대 경로를 NT object 경로로. 그 밖은 거부한다.

    UNC·네트워크 매핑을 여기서 막는 이유는 이 사이클이 그 환경에서 계약을 증명하지 않았기
    때문이다. 문서상 API 가 동작한다는 것만으로 열지 않는다.
    """
    full = os.path.abspath(path)
    if len(full) < 3 or full[1] != ":" or full[2] not in "\\/" or not full[0].isalpha():
        raise ValueError("uninstall.unsafe_platform")
    return "\\??\\" + full.replace("/", "\\")


# --- native 진입점 -------------------------------------------------------------

class _Api:
    """DLL 진입점 묶음. **import 시점이 아니라 처음 쓸 때** 연다.

    import 시점에 열면 이 모듈이 Windows 밖에서 import 조차 되지 않고, 그러면 구조체 배치
    검사를 개발 머신에서 돌릴 수 없다. 검사할 수 없는 구조체가 이 파일의 가장 큰 위험이다.
    """

    _instance = None

    def __init__(self):
        self.ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        self.NtCreateFile = self.ntdll.NtCreateFile
        self.NtCreateFile.restype = NTSTATUS
        self.NtCreateFile.argtypes = [ctypes.POINTER(HANDLE), ULONG,
                                      ctypes.POINTER(OBJECT_ATTRIBUTES),
                                      ctypes.POINTER(IO_STATUS_BLOCK),
                                      ctypes.POINTER(LARGE_INTEGER), ULONG, ULONG,
                                      ULONG, ULONG, PVOID, ULONG]
        self.NtSetInformationFile = self.ntdll.NtSetInformationFile
        self.NtSetInformationFile.restype = NTSTATUS
        self.NtSetInformationFile.argtypes = [HANDLE,
                                              ctypes.POINTER(IO_STATUS_BLOCK),
                                              PVOID, ULONG, ctypes.c_int]

        self.CloseHandle = self.kernel32.CloseHandle
        self.CloseHandle.argtypes = [HANDLE]
        self.CloseHandle.restype = ctypes.c_int

        self.GetFileInformationByHandle = self.kernel32.GetFileInformationByHandle
        self.GetFileInformationByHandle.argtypes = [
            HANDLE, ctypes.POINTER(BY_HANDLE_FILE_INFORMATION)]
        self.GetFileInformationByHandle.restype = ctypes.c_int

        self.GetFileInformationByHandleEx = self.kernel32.GetFileInformationByHandleEx
        self.GetFileInformationByHandleEx.argtypes = [HANDLE, ctypes.c_int, PVOID, DWORD]
        self.GetFileInformationByHandleEx.restype = ctypes.c_int

        self.SetFileInformationByHandle = self.kernel32.SetFileInformationByHandle
        self.SetFileInformationByHandle.argtypes = [HANDLE, ctypes.c_int, PVOID, DWORD]
        self.SetFileInformationByHandle.restype = ctypes.c_int

        self.GetVolumeInformationByHandleW = self.kernel32.GetVolumeInformationByHandleW
        self.GetVolumeInformationByHandleW.restype = ctypes.c_int

        self.GetFinalPathNameByHandleW = self.kernel32.GetFinalPathNameByHandleW
        self.GetFinalPathNameByHandleW.restype = DWORD

        self.GetVolumePathNameW = self.kernel32.GetVolumePathNameW
        self.GetVolumePathNameW.restype = ctypes.c_int

        self.GetDriveTypeW = self.kernel32.GetDriveTypeW
        self.GetDriveTypeW.restype = ctypes.c_uint

        self.ReadFile = self.kernel32.ReadFile
        self.ReadFile.argtypes = [HANDLE, PVOID, DWORD, ctypes.POINTER(DWORD), PVOID]
        self.ReadFile.restype = ctypes.c_int

        self.WriteFile = self.kernel32.WriteFile
        self.WriteFile.argtypes = [HANDLE, PVOID, DWORD, ctypes.POINTER(DWORD), PVOID]
        self.WriteFile.restype = ctypes.c_int

        self.FlushFileBuffers = self.kernel32.FlushFileBuffers
        self.FlushFileBuffers.argtypes = [HANDLE]
        self.FlushFileBuffers.restype = ctypes.c_int

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def _last_error():
    return ctypes.get_last_error()


def _check(ok, op):
    if not ok:
        raise WindowsMutationError(op, _last_error())


def _wide(name):
    """UTF-16LE 바이트 버퍼. `c_wchar` 를 쓰지 않는 이유는 파일 상단에 적었다."""
    return ctypes.create_string_buffer(name.encode("utf-16-le") + b"\x00\x00")


# --- 핸들 ---------------------------------------------------------------------

def _open(parent, name, *, access, disposition, options, attributes=FILE_ATTRIBUTE_NORMAL):
    """`parent` 핸들 아래 상대 이름 하나를 연다. `parent` 가 None 이면 NT 절대 경로다."""
    api = _Api.get()
    if parent is None:
        target = name
    else:
        validate_component(name)
        target = name
    buffer = _wide(target)
    byte_length = len(target.encode("utf-16-le"))
    unicode_name = UNICODE_STRING(Length=byte_length, MaximumLength=byte_length,
                                  Buffer=ctypes.cast(buffer, PVOID))
    attrs = OBJECT_ATTRIBUTES(
        Length=ctypes.sizeof(OBJECT_ATTRIBUTES),
        RootDirectory=(None if parent is None else HANDLE(parent)),
        ObjectName=ctypes.cast(ctypes.byref(unicode_name), PVOID),
        Attributes=OBJ_CASE_INSENSITIVE,
        SecurityDescriptor=None, SecurityQualityOfService=None)
    handle = HANDLE()
    iosb = IO_STATUS_BLOCK()
    status = api.NtCreateFile(ctypes.byref(handle), access, ctypes.byref(attrs),
                              ctypes.byref(iosb), None, attributes, SHARE_ALL,
                              disposition, options, None, 0)
    if status != STATUS_SUCCESS:
        raise WindowsMutationError("NtCreateFile", status & 0xFFFFFFFF, ntstatus=True)
    return handle.value


def _close(handle):
    if handle:
        _Api.get().CloseHandle(HANDLE(handle))


def _tag_info(handle):
    info = FILE_ATTRIBUTE_TAG_INFO()
    ok = _Api.get().GetFileInformationByHandleEx(
        HANDLE(handle), FileAttributeTagInfo, ctypes.byref(info), ctypes.sizeof(info))
    _check(ok, "GetFileInformationByHandleEx/FileAttributeTagInfo")
    return info.FileAttributes, info.ReparseTag


def _by_handle(handle):
    info = BY_HANDLE_FILE_INFORMATION()
    ok = _Api.get().GetFileInformationByHandle(HANDLE(handle), ctypes.byref(info))
    _check(ok, "GetFileInformationByHandle")
    return info


def _id_info(handle):
    info = FILE_ID_INFO()
    ok = _Api.get().GetFileInformationByHandleEx(
        HANDLE(handle), FileIdInfo, ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        return None
    return (info.VolumeSerialNumber, int.from_bytes(bytes(info.FileId), "little"))


# `os.lstat` 의 `(st_dev, st_ino)` 를 만들 수 있는 후보들. 순서가 우선순위다.
IDENTITY_SOURCES = ("id", "handle")


def identity(handle, *, source="id"):
    """`(dev, ino)` 한 쌍. 어느 호출로 만드는지는 root 고정 시점에 **대조해서** 정한다.

    Windows 에서 `os.lstat` 의 `st_dev`/`st_ino` 가 어떤 Win32 호출로 만들어지는지는 CPython
    버전을 탄다. 그것을 추측으로 맞추면, 맞는 환경에서는 통과하고 틀린 환경에서는 모든 지문이
    어긋난다 — 어긋남 자체는 fail-closed 라 안전하지만 원인이 화면에 보이지 않는다.

    그래서 추측하지 않고 두 후보를 다 만들어 실제 `os.lstat` 과 대조한다(`probe_capability`).
    """
    if source == "id":
        value = _id_info(handle)
        if value is not None:
            return value
    info = _by_handle(handle)
    return (info.dwVolumeSerialNumber,
            (info.nFileIndexHigh << 32) | info.nFileIndexLow)


def _open_root(path):
    return _open(None, nt_path(path),
                 access=FILE_LIST_DIRECTORY | FILE_TRAVERSE | FILE_READ_ATTRIBUTES
                 | SYNCHRONIZE,
                 disposition=FILE_OPEN,
                 options=FILE_DIRECTORY_FILE | FILE_OPEN_REPARSE_POINT
                 | FILE_SYNCHRONOUS_IO_NONALERT | FILE_OPEN_FOR_BACKUP_INTENT)


def _open_child(parent, name, *, directory, access=0, create=False, allow_reparse=False):
    """고정된 `parent` 아래 성분 하나. **reparse point 를 따라가지 않는다.**

    `allow_reparse` 는 보관소 정리에서만 참이다. 그때도 따라가지는 않고, reparse point
    자체를 leaf 로 지운다 — 따라가면 그 순간 바깥 tree 를 지운다.
    """
    options = (FILE_OPEN_REPARSE_POINT | FILE_SYNCHRONOUS_IO_NONALERT
               | FILE_OPEN_FOR_BACKUP_INTENT)
    options |= FILE_DIRECTORY_FILE if directory else FILE_NON_DIRECTORY_FILE
    handle = _open(parent, name,
                   access=access | FILE_READ_ATTRIBUTES | SYNCHRONIZE,
                   disposition=FILE_CREATE if create else FILE_OPEN,
                   options=options)
    if create:
        return handle
    # **연 뒤의 모든 실패 경로에서 닫는다.** `_tag_info` 도 실패할 수 있고, 그때 handle 을
    # 놓치면 그 디렉터리를 붙든 채 예외가 올라간다 — Windows 에서는 그 누수가 다른
    # 프로세스를 막는 장애로 곧장 보인다.
    try:
        attributes, tag = _tag_info(handle)
        if attributes & FILE_ATTRIBUTE_REPARSE_POINT and not allow_reparse:
            # 열기는 성공했지만 이것은 우리가 승인한 대상이 아니라 그 이름을 차지한 reparse
            # point 다. 따라가지 않았으므로 밖은 안전하고, 여기서 멈춘다.
            raise ValueError("uninstall.boundary_changed")
    except BaseException:
        _close(handle)
        raise
    return handle


def _open_any(parent, name, *, access=0, allow_reparse=False):
    """디렉터리인지 파일인지 모를 때. 디렉터리로 먼저 시도한다."""
    try:
        return _open_child(parent, name, directory=True, access=access,
                           allow_reparse=allow_reparse), True
    except WindowsMutationError as exc:
        if exc.ntstatus and (exc.code & 0xFFFFFFFF) == STATUS_NOT_A_DIRECTORY:
            return _open_child(parent, name, directory=False, access=access,
                               allow_reparse=allow_reparse), False
        raise


# --- 열거·읽기·쓰기 -------------------------------------------------------------

def _entries(handle):
    """열린 디렉터리 핸들에서 항목을 열거한다. 이름을 다시 열지 않는다."""
    api = _Api.get()
    size = 64 * 1024
    buffer = ctypes.create_string_buffer(size)
    names = []
    info_class = FileFullDirectoryRestartInfo
    while True:
        ok = api.GetFileInformationByHandleEx(HANDLE(handle), info_class,
                                              ctypes.byref(buffer), size)
        if not ok:
            if _last_error() == ERROR_NO_MORE_FILES:
                return names
            raise WindowsMutationError("GetFileInformationByHandleEx/FileFullDirectoryInfo",
                                       _last_error())
        info_class = FileFullDirectoryInfo
        offset = 0
        while True:
            entry = FILE_FULL_DIR_INFO.from_buffer(buffer, offset)
            start = offset + FILE_FULL_DIR_INFO.FileName.offset
            raw = bytes(buffer[start:start + entry.FileNameLength])
            name = raw.decode("utf-16-le")
            if name not in (os.curdir, os.pardir):
                names.append(name)
            if entry.NextEntryOffset == 0:
                break
            offset += entry.NextEntryOffset


def _read_all(handle):
    api = _Api.get()
    chunk = ctypes.create_string_buffer(1024 * 1024)
    read = DWORD(0)
    parts = []
    while True:
        ok = api.ReadFile(HANDLE(handle), ctypes.byref(chunk), len(chunk),
                          ctypes.byref(read), None)
        _check(ok, "ReadFile")
        if read.value == 0:
            return b"".join(parts)
        parts.append(bytes(chunk[:read.value]))


def _write_all(handle, payload):
    api = _Api.get()
    written = DWORD(0)
    total = 0
    view = ctypes.create_string_buffer(payload, len(payload))
    while total < len(payload):
        remaining = len(payload) - total
        ok = api.WriteFile(HANDLE(handle),
                           ctypes.byref(view, total), remaining,
                           ctypes.byref(written), None)
        _check(ok, "WriteFile")
        if written.value <= 0:
            # `WriteFile` 도 요청한 만큼 썼다고 보장하지 않는다. 반환값을 버리면 잘려 쓰인
            # 파일이 정상으로 통과하고, 그 파일이 사용자의 `.gitignore` 일 수 있다.
            raise WindowsMutationError("WriteFile", 0)
        total += written.value
    _check(api.FlushFileBuffers(HANDLE(handle)), "FlushFileBuffers")
    return total


def _rename_in(parent, handle, new_name):
    """열린 핸들을 **같은 부모 아래** 다른 이름으로 옮긴다. 덮어쓰지 않는다.

    ## 왜 Win32 가 아니라 NT 진입점인가

    `SetFileInformationByHandle(FileRenameInfo)` 는 **비-NULL `RootDirectory` 를 받지 않는다.**
    구조체 배치도, 버퍼 크기도, 포인터 전달 방식도 맞는데 `ERROR_INVALID_PARAMETER` 만 낸다 —
    Windows runner 에서 요인을 하나씩 분리해 확인했다(`scripts/ci/windows_rename_probe.py`).
    같은 구조체·같은 부모 핸들·같은 버퍼를 `NtSetInformationFile` 에 넘기면 파일과 디렉터리
    모두 성공한다.

    `RootDirectory` 를 비우고 절대 경로로 물러서는 길은 **택하지 않는다.** 그러면 rename 이
    이름 기준이 되어, 상위가 그 사이 바뀌면 우리가 붙든 것이 아닌 다른 자리로 간다 — 이
    사이클이 닫으려는 위험 자체다. 진입점을 바꾸는 것이 결속을 지키는 유일한 방향이다.
    """
    validate_component(new_name)
    encoded = new_name.encode("utf-16-le")
    header = FILE_RENAME_INFO.FileName.offset
    # 문서가 쓰는 크기다. 구조체 뒤 정렬 패딩까지 포함하므로 `header + n + 2` 보다 넉넉하다.
    size = ctypes.sizeof(FILE_RENAME_INFO) + len(encoded)
    buffer = ctypes.create_string_buffer(size)
    info = FILE_RENAME_INFO.from_buffer(buffer)
    info.Flags = 0                      # ReplaceIfExists = FALSE — 충돌은 덮어쓰지 않는다
    info.RootDirectory = HANDLE(parent)
    info.FileNameLength = len(encoded)
    buffer[header:header + len(encoded)] = encoded
    iosb = IO_STATUS_BLOCK()
    status = _Api.get().NtSetInformationFile(HANDLE(handle), ctypes.byref(iosb),
                                             ctypes.byref(buffer), size,
                                             FileRenameInformation)
    if status != STATUS_SUCCESS:
        raise WindowsMutationError("NtSetInformationFile/FileRenameInformation",
                                   status & 0xFFFFFFFF, ntstatus=True)


def _dispose(handle):
    info = FILE_DISPOSITION_INFO(DeleteFile=1)
    ok = _Api.get().SetFileInformationByHandle(HANDLE(handle), FileDispositionInfo,
                                               ctypes.byref(info), ctypes.sizeof(info))
    _check(ok, "SetFileInformationByHandle/FileDispositionInfo")


def _set_readonly(handle, readonly):
    info = FILE_BASIC_INFO()
    ok = _Api.get().GetFileInformationByHandleEx(
        HANDLE(handle), FileBasicInfo, ctypes.byref(info), ctypes.sizeof(info))
    _check(ok, "GetFileInformationByHandleEx/FileBasicInfo")
    attributes = info.FileAttributes
    attributes = (attributes | FILE_ATTRIBUTE_READONLY) if readonly else (
        attributes & ~FILE_ATTRIBUTE_READONLY)
    if attributes == 0:
        attributes = FILE_ATTRIBUTE_NORMAL
    basic = FILE_BASIC_INFO(CreationTime=0, LastAccessTime=0, LastWriteTime=0,
                            ChangeTime=0, FileAttributes=attributes)
    ok = _Api.get().SetFileInformationByHandle(HANDLE(handle), FileBasicInfo,
                                               ctypes.byref(basic), ctypes.sizeof(basic))
    _check(ok, "SetFileInformationByHandle/FileBasicInfo")


# --- capability ---------------------------------------------------------------

def _volume_facts(handle):
    """핸들에서 파일시스템 이름과 최종 경로를 읽는다. **확정하지 못하면 `None` 이다.**

    `None` 을 로컬·NTFS 로 접지 않는 것이 이 함수의 전부다. `GetFinalPathNameByHandleW` 는
    실패를 반환값 0 으로 알리는데, 그 0 을 "UNC 가 아니다" 로 읽으면 판정 실패가 곧 통과가
    된다. 부재는 안전한 방향이 아니다.
    """
    api = _Api.get()
    name = ctypes.create_string_buffer(261 * 2)
    filesystem = ctypes.create_string_buffer(261 * 2)
    serial = DWORD(0)
    max_component = DWORD(0)
    flags = DWORD(0)
    ok = api.GetVolumeInformationByHandleW(
        HANDLE(handle), ctypes.byref(name), 260, ctypes.byref(serial),
        ctypes.byref(max_component), ctypes.byref(flags),
        ctypes.byref(filesystem), 260)
    fs = None
    if ok:
        fs = bytes(filesystem).decode("utf-16-le").split("\x00", 1)[0] or None
    length = api.GetFinalPathNameByHandleW(HANDLE(handle), None, 0, 0)
    final = None
    if length:
        buffer = ctypes.create_string_buffer(length * 2 + 2)
        got = api.GetFinalPathNameByHandleW(HANDLE(handle), ctypes.byref(buffer), length, 0)
        if got:
            final = bytes(buffer).decode("utf-16-le").split("\x00", 1)[0] or None
    return fs, final


def _drive_type(final_path):
    """최종 경로가 어느 종류의 드라이브인가. **확정하지 못하면 `None`.**"""
    if not final_path:
        return None
    api = _Api.get()
    path = final_path
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"):
        if path.upper().startswith(prefix.upper()):
            if "UNC" in prefix:
                return DRIVE_REMOTE
            path = path[len(prefix):]
            break
    mount = ctypes.create_string_buffer(261 * 2)
    ok = api.GetVolumePathNameW(_wide(path), ctypes.byref(mount), 260)
    if not ok:
        return None
    root = bytes(mount).decode("utf-16-le").split("\x00", 1)[0]
    if not root:
        return None
    return api.GetDriveTypeW(_wide(root))


def local_ntfs(handle):
    """이 핸들이 가리키는 자리가 **로컬 NTFS 로 확정되는가.** 셋 다 확정돼야 참이다.

    돌려주는 것은 `(ok, filesystem, local)` 이고, 확정 실패는 언제나 거짓 쪽이다.
    """
    filesystem, final = _volume_facts(handle)
    if final is None:
        # 최종 경로를 확정하지 못했다. UNC 인지 아닌지 **모르는** 상태를 로컬로 세지 않는다.
        return False, filesystem, False
    kind = _drive_type(final)
    local = kind in LOCAL_DRIVE_TYPES
    if filesystem is None or filesystem.upper() != "NTFS":
        return False, filesystem, local
    return local, filesystem, local


def _is_windows():
    """이 프로세스가 Windows 에서 도는가. **검사가 갈아 끼울 수 있는 자리로 둔다.**

    이 파일의 native 경로는 개발 머신(macOS)에서 한 줄도 실행되지 않는다. 그 상태로 두면
    "지원 환경에서 capability 가 참이 되는가" 를 원격에서만 볼 수 있고, 그 질문에 실제로
    틀린 적이 있다 — 생성자가 만든 사본을 고치지 않아 언제나 거짓이었다.
    """
    return os.name == "nt"


def _windows_10_or_later():
    """Windows 10 이상인가. 그 아래는 이 사이클이 계약을 증명하지 않았다."""
    version = getattr(sys, "getwindowsversion", None)
    if version is None:
        return False
    info = version()
    return info.major > 10 or (info.major == 10 and info.build >= 10240)


def probe_capability(roots=()):
    """**기능마다 실제로 불러 본다.** 이름이 있는지로 대신하지 않는다.

    이름 확인은 "있다" 만 답하고 "동작한다" 는 답하지 않는다. 그리고 이 명령에서 동작하지
    않는 기능 하나는 곧 되돌릴 수 없는 실패다.

    `roots` 를 다 본다. 프로젝트가 NTFS 라도 `$CODEX_HOME` 이 네트워크 드라이브일 수 있고,
    그때 절반만 지울 수 있다는 것은 지원이 아니다.

    ## 이 함수가 **결속을 만들지 않는다**

    여기서 연 핸들은 조사에만 쓰고 닫는다. 실제 변경에 쓰는 핸들은 lock 을 잡은 뒤
    `WindowsBackend.open_roots` 가 따로 열고 계획의 기준과 대조한다. 그래서 이 조사와 실제
    변경 사이에 root 가 바뀌어도 변경 쪽이 다시 잡는다 — 조사 결과를 결속으로 쓰면 그 사이가
    그대로 경쟁 구간이 된다.
    """
    cap = _fs.MutationCapability(_fs.BACKEND_WINDOWS,
                                 primitives={name: False for name in _fs.PRIMITIVES})
    if not _is_windows():
        cap.os_supported = False
        cap.failure_code = "uninstall.unsafe_platform"
        return cap
    cap.os_supported = _windows_10_or_later()
    if not cap.os_supported:
        cap.failure_code = "uninstall.unsafe_platform"
        return cap

    targets = list(dict.fromkeys(os.path.abspath(r) for r in roots or () if r))
    if not targets:
        # root 를 모르면 볼륨을 판정할 수 없다. 판정하지 못한 것을 지원한다고 말하지 않는다.
        cap.failure_code = "uninstall.unsafe_platform"
        return cap

    # **`cap.primitives` 를 직접 고친다.** 지역 dict 를 고치면 생성자가 만든 사본은 전부
    # 거짓으로 남고, 그 capability 는 어떤 환경에서도 지원한다고 답하지 않는다 — 기능이
    # 통째로 죽는데 화면에는 "안전 거부" 로만 보인다.
    primitives = cap.primitives
    filesystems = set()
    # **root 마다 맞는 source 를 따로 모은다.** 공용 불리언 하나로 두면 첫 root 가 맞은 뒤
    # 두 번째 root 가 아무것에도 맞지 않아도 앞의 참이 그대로 남는다 — project 는 맞고
    # `$CODEX_HOME` 은 다른 볼륨이라 어긋나는 배치가 정확히 그 모양이다.
    common_sources = None
    try:
        for root in targets:
            handle = _open_root(root)
            try:
                primitives["relative_open"] = True
                ok, filesystem, local = local_ntfs(handle)
                filesystems.add(filesystem)
                cap.local_volume = cap.local_volume and local
                if not ok:
                    cap.filesystem = filesystem
                    cap.failure_code = "uninstall.unsafe_platform"
                    return cap
                attributes, tag = _tag_info(handle)
                if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    cap.failure_code = "uninstall.unsafe_platform"
                    return cap
                primitives["reparse_no_follow"] = True
                # identity 를 **대조해서** 정한다. 추측하면 틀린 환경에서 모든 지문이
                # 어긋나고, 그 어긋남은 안전하지만 원인이 보이지 않는다.
                expected = os.stat(root)
                anchor = (_stat_mode(expected), expected.st_dev, expected.st_ino)
                matching = {source for source in IDENTITY_SOURCES
                            if (_mode_of(attributes),) + identity(handle, source=source)
                            == anchor}
                common_sources = (matching if common_sources is None
                                  else common_sources & matching)
                if not common_sources:
                    # 이 root 에 맞는 source 가 없거나, 앞선 root 들과 공통인 것이 없다.
                    # 하나의 실행은 하나의 유도만 쓸 수 있으므로 여기서 끝이다.
                    cap.failure_code = "uninstall.unsafe_platform"
                    return cap
                _entries(handle)
                primitives["directory_enumeration"] = True
            finally:
                _close(handle)
        # rename·delete 는 파괴적이라 probe 에서 실행하지 않는다. 진입점이 실제로 결속돼
        # 있는지만 확인하고, 계약은 원격 runner 의 race 검사가 증명한다.
        api = _Api.get()
        primitives["handle_rename"] = bool(api.SetFileInformationByHandle)
        primitives["handle_delete"] = bool(api.SetFileInformationByHandle)
    except (WindowsMutationError, ValueError, OSError):
        cap.failure_code = "uninstall.unsafe_platform"
        return cap
    # 모든 root 에 공통인 source 하나를 고른다. 순서를 값으로 고정하는 이유는 같은 환경이
    # 실행마다 다른 유도를 쓰면 지문 대조가 재현되지 않기 때문이다.
    if not common_sources:
        cap.failure_code = "uninstall.unsafe_platform"
        return cap
    cap.identity_source = next(source for source in IDENTITY_SOURCES
                               if source in common_sources)
    primitives["identity_match"] = True
    cap.filesystem = filesystems.pop() if len(filesystems) == 1 else "mixed"
    return cap


def _stat_mode(info):
    return stat.S_IMODE(info.st_mode)


def _mode_of(attributes):
    """Windows 속성을 POSIX mode 비트로. `os.lstat` 이 이 환경에서 쓰는 규칙과 같아야 한다.

    같은지는 믿지 않고 `probe_capability` 에서 root 로 실제 대조한다. 파일 쪽 규칙이 달라도
    결과는 fail-closed 다 — 지문이 어긋나 명령이 멈추지, 잘못된 기준으로 지우지 않는다.
    """
    mode = 0o111 if attributes & FILE_ATTRIBUTE_DIRECTORY else 0
    mode |= 0o444 if attributes & FILE_ATTRIBUTE_READONLY else 0o666
    return mode


def _kind_of(attributes, tag):
    if attributes & FILE_ATTRIBUTE_REPARSE_POINT and tag in (
            IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT):
        return "symlink"
    return "dir" if attributes & FILE_ATTRIBUTE_DIRECTORY else "file"


# --- backend ------------------------------------------------------------------

def _fingerprint_at(parent, name, source):
    """`install_transaction.path_fingerprint` 와 **같은 형**을 핸들 기준으로 만든다.

    값이 같아야 하는 이유는 계획이 뜬 기준과 대조하기 때문이다. 형이 달라지면 대조는 늘
    "바뀌었다" 가 되고, 그 상태의 명령은 아무것도 지우지 못한다.
    """
    handle, _is_dir = _open_any(parent, name, access=FILE_READ_DATA)
    try:
        attributes, tag = _tag_info(handle)
        kind = _kind_of(attributes, tag)
        common = (kind, _mode_of(attributes)) + identity(handle, source=source)
        if kind != "file":
            return common
        before = _by_handle(handle)
        digest = hashlib.sha256()
        size = 0
        api = _Api.get()
        chunk = ctypes.create_string_buffer(1024 * 1024)
        read = DWORD(0)
        while True:
            ok = api.ReadFile(HANDLE(handle), ctypes.byref(chunk), len(chunk),
                              ctypes.byref(read), None)
            _check(ok, "ReadFile")
            if read.value == 0:
                break
            digest.update(bytes(chunk[:read.value]))
            size += read.value
        after = _by_handle(handle)
        if _stable(before) != _stable(after):
            raise _tx.InstallDriftError(
                _tx.Diagnostic("install.file_changed_during_fingerprint", path=name))
        return common + (size, digest.hexdigest())
    finally:
        _close(handle)


def _stable(info):
    """읽는 동안 파일이 바뀌지 않았는지 볼 값들. 크기·시각·색인 전부."""
    return ((info.nFileSizeHigh << 32) | info.nFileSizeLow,
            info.ftLastWriteTime.dwLowDateTime, info.ftLastWriteTime.dwHighDateTime,
            info.nFileIndexHigh, info.nFileIndexLow, info.dwVolumeSerialNumber,
            info.dwFileAttributes)


def _tree_fingerprint_at(parent, name, source):
    """핸들 기준 tree 지문. reparse point 를 tree 로 따라가지 않는다."""
    root_fp = _fingerprint_at(parent, name, source)
    if root_fp[0] != "dir":
        return ((".", root_fp),)
    entries = [(".", root_fp)]

    def walk(handle, relbase):
        for child in sorted(_entries(handle)):
            rel = f"{relbase}/{child}" if relbase else child
            fp = _fingerprint_at(handle, child, source)
            entries.append((rel.replace("/", os.sep), fp))
            if fp[0] == "dir":
                nested = _open_child(handle, child, directory=True,
                                     access=FILE_LIST_DIRECTORY | FILE_TRAVERSE)
                try:
                    walk(nested, rel)
                finally:
                    _close(nested)

    top = _open_child(parent, name, directory=True,
                      access=FILE_LIST_DIRECTORY | FILE_TRAVERSE)
    try:
        walk(top, "")
    finally:
        _close(top)
    return tuple(entries)


def _rmtree_at(parent, name):
    """고정된 부모 기준 재귀 삭제. 어느 단계에서도 이름을 따라가지 않는다."""
    try:
        handle, is_dir = _open_any(parent, name, access=DELETE | FILE_LIST_DIRECTORY,
                                   allow_reparse=True)
    except WindowsMutationError as exc:
        if exc.ntstatus and (exc.code & 0xFFFFFFFF) in _ABSENT_STATUS:
            return
        raise
    try:
        attributes, _tag = _tag_info(handle)
        # reparse point 는 안으로 들어가지 않는다. 들어가면 그 순간 바깥 tree 를 지운다.
        if is_dir and not attributes & FILE_ATTRIBUTE_REPARSE_POINT:
            for child in _entries(handle):
                _rmtree_at(handle, child)
        if attributes & FILE_ATTRIBUTE_READONLY:
            # readonly 는 삭제를 막는다. 우리가 만든 보관소 안의 파일이므로 속성을 내리고
            # 지운다 — 밖의 파일에는 이 경로가 닿지 않는다.
            _set_readonly(handle, False)
        _dispose(handle)
    finally:
        _close(handle)


class WindowsBackend(_fs.MutationBackend):
    """모든 변경을 **첫 mutation 전에 연 부모 핸들** 기준으로 수행한다.

    POSIX 의 `dir_fd` 와 같은 자리다. 부모를 붙든 뒤에는 상위 이름이 junction 으로 바뀌어도
    작업이 원래 디렉터리로 가고, 붙들 수 없으면 아무것도 하지 않는다.
    """

    name = _fs.BACKEND_WINDOWS

    def __init__(self, capability):
        self.capability = capability
        self.source = getattr(capability, "identity_source", None) or "id"
        self.roots = {}
        self.parents = {}
        self._owned = []
        # 우리가 스스로 놓은 부모. 놓은 뒤 그 아래를 다시 쓰려 하면 경로로 떨어지지
        # 않고 멈추기 위해 기억한다.
        self._released = set()
        # **붙든 부모가 지금 실제로 어디에 있는가.** `parents` 의 key 는 호출자가 쓰는
        # 논리 경로이고 끝까지 바뀌지 않는다 — 그래야 `_parent_of` 가 늘 같은 이름으로 찾는다.
        # 그런데 디렉터리를 보관소 이름으로 옮기면 그 아래 것들의 **물리 위치**가 통째로
        # 움직인다. 둘을 같은 dict 하나로 다루면 옮긴 뒤 그 handle 을 이름으로 찾지 못하고,
        # 되돌릴 때 놓아야 할 handle 을 놓지 못한 채 rename 이 거부된다. 실제로 그렇게
        # rollback 이 통째로 실패했다. 그래서 **논리 이름과 물리 위치를 따로 적는다.**
        self._physical = {}

    # -- 결속 ------------------------------------------------------------------

    def open_roots(self, marks):
        """root 를 **여기서** 열고 계획의 기준·NTFS·로컬·reparse 를 한 번에 대조한다.

        probe 가 연 핸들은 이미 닫혔다. 그 핸들로 확인하고 다른 핸들로 변경하면 둘 사이가
        경쟁 구간이고, root 이름이 junction 으로 바뀌면 확인은 옛 디렉터리에 대해, 변경은
        새 디렉터리에서 일어난다. 여기서 연 핸들은 `close()` 까지 살아 있고, 모든 하강이
        이 핸들에서 시작한다.
        """
        for root, mark in sorted(marks.items()):
            base = os.path.abspath(root)
            if base in self.roots:
                continue
            handle = _open_root(base)
            try:
                ok, filesystem, _local = local_ntfs(handle)
                if not ok:
                    raise ValueError("uninstall.unsafe_platform")
                attributes, tag = _tag_info(handle)
                if attributes & FILE_ATTRIBUTE_REPARSE_POINT:
                    # root 이름이 reparse point 로 바뀌었다. 따라가지 않았으므로 밖은
                    # 안전하고, 여기서 멈춘다.
                    raise ValueError("uninstall.boundary_changed")
                current = (_kind_of(attributes, tag), _mode_of(attributes)) + identity(
                    handle, source=self.source)
                if current != tuple(mark):
                    # 계획을 세운 그 디렉터리가 아니다. 상대 경로는 새 root 안에서도
                    # 성립하므로, 여기서 멈추지 않으면 남의 디렉터리에서 지운다.
                    raise ValueError("uninstall.boundary_changed")
            except BaseException:
                _close(handle)
                raise
            self.roots[base] = handle

    def _root_handle(self, root):
        base = os.path.abspath(root)
        handle = self.roots.get(base)
        if handle is None:
            # root 를 여기서 열면 확인한 root 와 쓰는 root 가 달라진다. 열지 않고 거부한다.
            raise _tx.InstallDriftError(f"root was never opened and verified: {base}")
        return handle

    def pin(self, root, path):
        parent = os.path.dirname(os.path.abspath(path))
        if parent in self.parents:
            return
        base = os.path.abspath(root)
        relative = os.path.relpath(parent, base)
        handle = self._root_handle(base)
        owned = []
        if relative != os.curdir:
            try:
                for part in relative.split(os.sep):
                    handle = _open_child(handle, part, directory=True,
                                         access=FILE_LIST_DIRECTORY | FILE_TRAVERSE)
                    owned.append(handle)
            except BaseException:
                # **역순으로 전부 닫는다.** 남기면 그 디렉터리를 붙든 채 실패가 올라가고,
                # 다른 프로세스는 우리가 만든 장애를 만난다.
                for extra in reversed(owned):
                    _close(extra)
                raise
        self.parents[parent] = handle
        self._physical[parent] = parent
        # root handle 은 `roots` 가 소유한다. 중간 핸들은 마지막 것만 남기고 닫는다.
        for extra in owned[:-1]:
            _close(extra)
        if owned:
            self._owned.append(owned[-1])

    def pinned(self, path):
        parent = os.path.dirname(os.path.abspath(path))
        if parent in self._released:
            # 우리가 스스로 놓은 디렉터리다. `False` 를 돌려주면 상위 층이 **경로 기반
            # 구현으로 조용히 떨어진다** — 결속이 사라진 사실이 결과에 드러나지 않는다.
            # 이 사이클이 반복해서 만난 모양이라 여기서는 소리를 낸다.
            raise _tx.InstallDriftError(f"parent handle was released: {parent}")
        return parent in self.parents

    def _detach_subtree(self, physical):
        """지금 **그 자리에 물리적으로 있는** 붙든 부모들을 전부 놓는다.

        Windows 는 자기 handle 이 열려 있는 디렉터리도, **하위에 열린 handle 이 남은**
        디렉터리도 이름을 바꾸지 못한다. 그래서 옮기기 전에 그 아래 전부를 놓아야 한다.

        **찾는 기준이 물리 위치인 것이 요점이다.** 논리 이름으로 찾으면, 이미 한 번 옮겨진
        디렉터리를 되돌릴 때 그 handle 을 찾지 못한다 — 그 key 는 여전히 원래 이름이고
        지금 그 이름의 자리에는 아무것도 없다. 실제로 그래서 되돌리기가 통째로 실패했다.

        돌려주는 것은 `(논리 key, 옮기는 자리 기준 상대 경로)` 목록이다. 디렉터리는 통째로
        움직이므로 그 상대 구조는 옮긴 뒤에도 같다.
        """
        base = os.path.abspath(physical)
        prefix = base + os.sep
        held = [(key, where) for key, where in self._physical.items()
                if where == base or where.startswith(prefix)]
        detached = []
        # 깊은 것부터 놓는다. 순서를 정해 두면 실패했을 때 어디까지 놓았는지가 결정적이다.
        for key, where in sorted(held, key=lambda item: len(item[1]), reverse=True):
            handle = self.parents.pop(key, None)
            self._physical.pop(key, None)
            if handle is None:
                continue
            if handle in self._owned:
                self._owned.remove(handle)
            _close(handle)
            detached.append((key, os.path.relpath(where, base)))
        return detached

    def _attach_subtree(self, detached, parent, name, physical):
        """옮겨진 자리에서 **같은 구조를 다시 붙들고, 새 물리 위치를 적는다.**

        이름으로 다시 여는 것이지만 경로로 되돌아가는 것이 아니다 — 여는 자리는 언제나 이미
        붙든 handle 아래이고, 첫 성분은 방금 우리가 옮긴 그 객체다.

        논리 key 는 그대로 두고 물리 위치만 갱신한다. 그 둘을 하나로 합치는 순간, 호출자가
        쓰는 이름과 실제 자리가 어긋난 상태를 표현할 방법이 없어진다.
        """
        base_physical = os.path.abspath(physical)
        base = _open_child(parent, name, directory=True,
                           access=FILE_LIST_DIRECTORY | FILE_TRAVERSE)
        attached = False
        for key, relative in sorted(detached, key=lambda item: len(item[1])):
            if relative == os.curdir:
                self.parents[key] = base
                self._physical[key] = base_physical
                self._owned.append(base)
                attached = True
                continue
            handle = base
            owned = []
            for part in relative.split(os.sep):
                handle = _open_child(handle, part, directory=True,
                                     access=FILE_LIST_DIRECTORY | FILE_TRAVERSE)
                owned.append(handle)
            # 중간 handle 은 붙들 이유가 없다. 남기면 그 디렉터리를 옮길 때 같은 벽에 걸린다.
            for extra in owned[:-1]:
                _close(extra)
            self.parents[key] = handle
            self._physical[key] = os.path.join(base_physical, relative)
            self._owned.append(handle)
        if not attached:
            _close(base)

    def _release_parent(self, physical):
        """다시 붙들지 **않고** 놓는다. 사라질 디렉터리에만 쓴다.

        놓은 뒤 그 아래를 다시 쓰려 하면 `pinned()` 가 예외를 낸다. 거짓을 돌려주면 상위
        층이 경로 기반 구현으로 조용히 떨어지고, 결속이 사라진 사실이 결과에 드러나지 않는다.
        """
        for key, _relative in self._detach_subtree(physical):
            self._released.add(key)

    def close(self):
        """몇 번 불려도 안전해야 한다. 어떤 실패 경로에서도 반드시 불린다.

        Windows 에서 핸들을 남기면 그 디렉터리를 다른 프로세스가 만지지 못한다 — POSIX 의
        fd 누수보다 사용자에게 더 직접적으로 보인다.
        """
        for handle in self._owned:
            _close(handle)
        self._owned.clear()
        self.parents.clear()
        self._physical.clear()
        self._released.clear()
        for handle in self.roots.values():
            _close(handle)
        self.roots.clear()

    def _parent_of(self, path):
        parent = self.parents.get(os.path.dirname(os.path.abspath(path)))
        if parent is None:
            raise _tx.InstallDriftError(f"unpinned parent: {path}")
        return parent

    # -- 조작 ------------------------------------------------------------------

    def replace(self, source, target):
        parent = self._parent_of(source)
        if self.parents.get(os.path.dirname(os.path.abspath(target))) != parent:
            # 경로 기준으로 되돌아가지 않는다. 그 길을 남겨 두면 조건 하나가 어긋나는 날
            # 조용히 그쪽으로 떨어진다.
            raise _tx.InstallDriftError(f"unpinned parent for rename: {source}")
        # 옮기려는 것이 **우리가 부모로 붙든 디렉터리 자신**이면 그 handle 을 잠깐 놓고,
        # 옮긴 **직후에 새 이름으로 다시 붙든다.** 놓기만 하면 되돌리기가 그 아래 자식을
        # 제자리에 놓지 못한다.
        detached = self._detach_subtree(source)
        handle, _is_dir = _open_any(parent, os.path.basename(source),
                                    access=DELETE, allow_reparse=True)
        try:
            _rename_in(parent, handle, os.path.basename(target))
        except BaseException:
            if detached:
                # 옮기지 못했으므로 원래 자리 그대로 다시 붙든다. 놓은 채 올라가면 되돌리기가
                # 그 아래를 못 만진다.
                self._attach_subtree(detached, parent, os.path.basename(source), source)
            raise
        finally:
            _close(handle)
        if detached:
            self._attach_subtree(detached, parent, os.path.basename(target), target)

    def remove_tree(self, path):
        # 지우려는 것이 우리가 붙든 디렉터리 자신이어도 같다. 열린 handle 이 남으면 삭제도
        # 서지 않는다.
        self._release_parent(path)
        _rmtree_at(self._parent_of(path), os.path.basename(path))
        return None

    def probe(self, path):
        parent = self._parent_of(path)
        try:
            handle, _is_dir = _open_any(parent, os.path.basename(path),
                                        allow_reparse=True)
        except WindowsMutationError as exc:
            if exc.ntstatus and (exc.code & 0xFFFFFFFF) in _ABSENT_STATUS:
                return False
            raise
        _close(handle)
        return True

    def measure(self, path, form):
        parent = self._parent_of(path)
        if not self.probe(path):
            return ("absent",) if form == "path" else ((".", ("absent",)),)
        name = os.path.basename(path)
        return (_tree_fingerprint_at(parent, name, self.source) if form == "tree"
                else _fingerprint_at(parent, name, self.source))

    def read_bytes(self, path):
        """대상을 부모 핸들 기준으로 읽는다. 이름도 leaf 도 따라가지 않는다."""
        handle = _open_child(self._parent_of(path), os.path.basename(path),
                             directory=False, access=FILE_READ_DATA)
        try:
            return _read_all(handle)
        finally:
            _close(handle)

    def write_new(self, path, body, mode):
        """치워진 자리에 부모 핸들 기준으로 새로 만든다.

        `FILE_CREATE` 는 그 이름이 이미 있으면 실패한다 — POSIX 의 `O_EXCL` 과 같은 의미다.
        원본은 이미 보관소로 치워졌으므로 이 자리는 비어 있어야 하고, 비어 있지 않다면
        누군가 그 사이에 무엇을 놓은 것이다.
        """
        parent = self._parent_of(path)
        name = os.path.basename(path)
        payload = body.encode("utf-8")
        handle = _open_child(parent, name, directory=False, create=True,
                             access=FILE_WRITE_DATA | FILE_READ_DATA
                             | FILE_WRITE_ATTRIBUTES)
        complete = False
        try:
            written = _write_all(handle, payload)
            info = _by_handle(handle)
            size = (info.nFileSizeHigh << 32) | info.nFileSizeLow
            if written != len(payload) or size != len(payload):
                raise WindowsMutationError("WriteFile", 0)
            _set_readonly(handle, not mode & 0o200)
            complete = True
        finally:
            if not complete:
                # **반쯤 쓰인 파일을 남기면 되돌리기가 거부된다.** journal 은 대상 자리에
                # 자기가 모르는 파일이 있으면 복원을 멈춘다. `FILE_CREATE` 로 만들었으니
                # 이 자리는 우리 것이고, 만든 쪽이 치우는 것이 맞다.
                try:
                    _dispose(handle)
                except OSError:
                    pass
            _close(handle)

    def listdir(self, path):
        handle = _open_child(self._parent_of(path), os.path.basename(path),
                             directory=True, access=FILE_LIST_DIRECTORY | FILE_TRAVERSE)
        try:
            return _entries(handle)
        finally:
            _close(handle)
