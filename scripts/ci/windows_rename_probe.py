#!/usr/bin/env python3
"""`FileRenameInfo` 실패의 **요인을 하나씩 분리한다.** 추측으로 고치지 않기 위해서다.

Windows 세 job 이 전부 첫 backup rename 에서 `ERROR_INVALID_PARAMETER` 로 죽는다. 구조체
배치도, 버퍼 크기도, `FileNameLength` 도, handle 권한도 소스만 읽어서는 전부 맞아 보인다.
맞아 보이는 것 여럿 중 하나가 틀렸을 때 소스를 더 오래 읽는 것으로는 어느 것인지 알 수 없다.

그래서 한 번의 job 에서 **한 요인만 다른** 변형들을 각각 실제로 불러 code 를 비교한다.
파일과 디렉터리 둘 다 돌린다 — 한쪽만 되는 방식을 고르면 나머지 절반이 사용자에게서 처음
실패한다.

`RootDirectory` 를 빼는 변형이 있지만 그것은 **관측용**이다. 절대 경로 rename 으로 물러서면
부모 handle 결속이 무너지고, 그것이 이 사이클이 닫으려는 위험 자체다. 채택 후보는
handle 상대 의미를 유지하는 것들뿐이다.

출력에는 경로도 OS 원문 메시지도 싣지 않는다. 변형 이름과 정수 code 만 낸다.
"""
import ctypes
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

FileRenameInformation = 10          # NT 쪽 class 번호. Win32 의 3 과 다르다.


def main():
    print("== windows rename probe ==")
    if os.name != "nt":
        print("  not applicable on this platform")
        return 0

    from sage import uninstall_windows_fs as w

    api = w._Api.get()
    nt_set = api.ntdll.NtSetInformationFile
    nt_set.restype = w.NTSTATUS
    nt_set.argtypes = [w.HANDLE, ctypes.POINTER(w.IO_STATUS_BLOCK), w.PVOID,
                       w.ULONG, ctypes.c_int]

    info = w.FILE_RENAME_INFO
    print(f"  struct sizeof={ctypes.sizeof(info)} "
          f"Flags={info.Flags.offset} RootDirectory={info.RootDirectory.offset} "
          f"FileNameLength={info.FileNameLength.offset} FileName={info.FileName.offset}")
    print(f"  pointer_size={ctypes.sizeof(ctypes.c_void_p)}")

    base = os.path.realpath(tempfile.mkdtemp(prefix="rename-probe-"))
    try:
        for kind in ("file", "dir"):
            print(f"  --- target kind={kind}")
            for label, attempt in variants(w, nt_set):
                code = run_one(w, base, kind, attempt)
                print(f"      {label:44} {code}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0


def variants(w, nt_set):
    """(이름, 시도) 목록. **한 번에 한 요인만 바꾼다.**"""
    def header_plus_two(parent, handle, name):
        # 현재 구현과 같다. 버퍼는 `FileName` offset + 이름 + null 종단.
        return win32_rename(w, parent, handle, name,
                            size=lambda header, n: header + n + 2)

    def sizeof_plus_name(parent, handle, name):
        # MSDN 예제가 쓰는 크기. `sizeof(FILE_RENAME_INFO) + FileNameLength` 다 —
        # 구조체 뒤 정렬 패딩이 포함되므로 위보다 크다.
        return win32_rename(w, parent, handle, name,
                            size=lambda header, n: ctypes.sizeof(w.FILE_RENAME_INFO) + n)

    def by_value_buffer(parent, handle, name):
        # `byref(buffer)` 대신 배열 자체를 넘긴다. argtype 이 `PVOID` 라 둘 다 통과하지만
        # 실제로 커널에 가는 값이 같은지는 불러 봐야 안다.
        return win32_rename(w, parent, handle, name,
                            size=lambda header, n: header + n + 2, byref=False)

    def no_root_directory(parent, handle, name):
        # **관측 전용.** 채택 후보가 아니다 — 절대 경로 rename 은 결속을 버린다.
        return win32_rename(w, parent, handle, name,
                            size=lambda header, n: ctypes.sizeof(w.FILE_RENAME_INFO) + n,
                            root=None)

    def nt_header_plus_two(parent, handle, name):
        return nt_rename(w, nt_set, parent, handle, name,
                         size=lambda header, n: header + n + 2)

    def nt_sizeof_plus_name(parent, handle, name):
        return nt_rename(w, nt_set, parent, handle, name,
                         size=lambda header, n: ctypes.sizeof(w.FILE_RENAME_INFO) + n)

    return [
        ("win32 FileRenameInfo, header+n+2 (current)", header_plus_two),
        ("win32 FileRenameInfo, sizeof+n", sizeof_plus_name),
        ("win32 FileRenameInfo, buffer by value", by_value_buffer),
        ("win32 FileRenameInfo, RootDirectory=NULL (observe)", no_root_directory),
        ("nt   FileRenameInformation, header+n+2", nt_header_plus_two),
        ("nt   FileRenameInformation, sizeof+n", nt_sizeof_plus_name),
    ]


def build(w, name, size, root):
    encoded = name.encode("utf-16-le")
    header = w.FILE_RENAME_INFO.FileName.offset
    total = size(header, len(encoded))
    buffer = ctypes.create_string_buffer(total)
    info = w.FILE_RENAME_INFO.from_buffer(buffer)
    info.Flags = 0
    info.RootDirectory = root
    info.FileNameLength = len(encoded)
    buffer[header:header + len(encoded)] = encoded
    return buffer, total


def win32_rename(w, parent, handle, name, *, size, root=True, byref=True):
    buffer, total = build(w, name, size, w.HANDLE(parent) if root else None)
    pointer = ctypes.byref(buffer) if byref else buffer
    ok = w._Api.get().SetFileInformationByHandle(
        w.HANDLE(handle), w.FileRenameInfo, pointer, total)
    if ok:
        return "ok"
    return f"win32:{ctypes.get_last_error():#x}"


def nt_rename(w, nt_set, parent, handle, name, *, size):
    buffer, total = build(w, name, size, w.HANDLE(parent))
    iosb = w.IO_STATUS_BLOCK()
    status = nt_set(w.HANDLE(handle), ctypes.byref(iosb), ctypes.byref(buffer),
                    total, FileRenameInformation) & 0xFFFFFFFF
    if status == w.STATUS_SUCCESS:
        return "ok"
    return f"nt:{status:#x}"


def run_one(w, base, kind, attempt):
    """매 시도마다 **새 fixture** 를 만든다. 앞 시도의 성공이 다음 시도를 가리지 않게."""
    room = tempfile.mkdtemp(dir=base)
    parent = None
    handle = None
    try:
        if kind == "dir":
            os.mkdir(os.path.join(room, "target"))
        else:
            with open(os.path.join(room, "target"), "w", encoding="utf-8") as fp:
                fp.write("x")
        parent = w._open_root(room)
        handle, _is_dir = w._open_any(parent, "target", access=w.DELETE,
                                      allow_reparse=True)
        return attempt(parent, handle, ".sage-install-backup-probe-target")
    except w.WindowsMutationError as exc:
        return f"setup {exc.op}:{'nt' if exc.ntstatus else 'win32'}:{exc.code:#x}"
    except Exception as exc:                                   # noqa: BLE001
        return f"setup {type(exc).__name__}"
    finally:
        if handle:
            w._close(handle)
        if parent:
            w._close(parent)
        shutil.rmtree(room, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
