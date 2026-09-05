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

# 디렉터리에 항목을 만들 권한. 이름이 데이터 권한과 같은 비트라 헷갈리기 쉬워 여기 적어 둔다.
FILE_ADD_FILE = 0x0002              # = FILE_WRITE_DATA
FILE_ADD_SUBDIRECTORY = 0x0004      # = FILE_APPEND_DATA


def main():
    print("== windows rename probe ==")
    if os.name != "nt":
        print("  not applicable on this platform")
        return 0

    from sage import uninstall_windows_fs as w

    api = w._Api.get()
    info = w.FILE_RENAME_INFO
    print(f"  struct sizeof={ctypes.sizeof(info)} "
          f"Flags={info.Flags.offset} RootDirectory={info.RootDirectory.offset} "
          f"FileNameLength={info.FileNameLength.offset} FileName={info.FileName.offset}")

    # 부모 handle 의 권한. 현재 구현은 읽기·순회만 갖는다. rename 은 **대상 디렉터리에
    # 항목을 만드는** 조작이므로 그 권한이 필요할 수 있다 — 있어야 하는지 여기서 가른다.
    parent_modes = [
        ("list+traverse (current)",
         w.FILE_LIST_DIRECTORY | w.FILE_TRAVERSE),
        ("list+traverse+add",
         w.FILE_LIST_DIRECTORY | w.FILE_TRAVERSE | FILE_ADD_FILE | FILE_ADD_SUBDIRECTORY),
    ]
    # 대상의 성격. 실제 소비자에는 중첩 경로·비어 있지 않은 디렉터리가 섞여 있고, probe 가
    # 평평한 빈 fixture 만 보면 그 차이가 원격에서 처음 드러난다.
    kinds = ["file", "dir", "nonempty-dir", "readonly-file", "nested-file"]

    base = os.path.realpath(tempfile.mkdtemp(prefix="rename-probe-"))
    try:
        for parent_label, parent_access in parent_modes:
            print(f"  --- parent handle: {parent_label}")
            for kind in kinds:
                code = run_one(w, base, kind, parent_access)
                print(f"      {kind:16} nt FileRenameInformation  {code}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0


def nt_rename(w, parent, handle, name):
    encoded = name.encode("utf-16-le")
    header = w.FILE_RENAME_INFO.FileName.offset
    size = ctypes.sizeof(w.FILE_RENAME_INFO) + len(encoded)
    buffer = ctypes.create_string_buffer(size)
    info = w.FILE_RENAME_INFO.from_buffer(buffer)
    info.Flags = 0
    info.RootDirectory = w.HANDLE(parent)
    info.FileNameLength = len(encoded)
    buffer[header:header + len(encoded)] = encoded
    iosb = w.IO_STATUS_BLOCK()
    status = w._Api.get().NtSetInformationFile(
        w.HANDLE(handle), ctypes.byref(iosb), ctypes.byref(buffer), size,
        FileRenameInformation) & 0xFFFFFFFF
    return "ok" if status == w.STATUS_SUCCESS else f"nt:{status:#x}"


def build_target(room, kind):
    """대상 하나를 만들고 (부모 상대 경로 성분, leaf 이름) 을 돌려준다."""
    if kind == "nested-file":
        os.makedirs(os.path.join(room, "nested"))
        with open(os.path.join(room, "nested", "target"), "w", encoding="utf-8") as fp:
            fp.write("x")
        return ["nested"], "target"
    if kind == "dir":
        os.mkdir(os.path.join(room, "target"))
    elif kind == "nonempty-dir":
        os.makedirs(os.path.join(room, "target", "inner"))
        with open(os.path.join(room, "target", "inner", "leaf"), "w",
                  encoding="utf-8") as fp:
            fp.write("x")
    else:
        with open(os.path.join(room, "target"), "w", encoding="utf-8") as fp:
            fp.write("x")
        if kind == "readonly-file":
            os.chmod(os.path.join(room, "target"), 0o444)
    return [], "target"


def run_one(w, base, kind, parent_access):
    """매 시도마다 **새 fixture** 를 만든다. 앞 시도의 성공이 다음 시도를 가리지 않게."""
    room = tempfile.mkdtemp(dir=base)
    opened = []
    try:
        parts, leaf = build_target(room, kind)
        parent = w._open_root(room)
        opened.append(parent)
        for part in parts:
            parent = w._open_child(parent, part, directory=True, access=parent_access)
            opened.append(parent)
        handle, _is_dir = w._open_any(parent, leaf, access=w.DELETE, allow_reparse=True)
        opened.append(handle)
        return nt_rename(w, parent, handle, ".sage-install-backup-probe-target")
    except w.WindowsMutationError as exc:
        return f"setup {exc.op}:{'nt' if exc.ntstatus else 'win32'}:{exc.code:#x}"
    except Exception as exc:                                   # noqa: BLE001
        return f"setup {type(exc).__name__}"
    finally:
        for handle in reversed(opened):
            w._close(handle)
        for base_dir, dirs, names in os.walk(room):
            for name in names:
                try:
                    os.chmod(os.path.join(base_dir, name), 0o666)
                except OSError:
                    pass
        shutil.rmtree(room, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
