#!/usr/bin/env python3
"""Windows capability 판정이 **어느 관문에서 갈렸는지** 찍는다.

`probe_capability` 는 어느 관문에서 멈추든 같은 `uninstall.unsafe_platform` 하나를 낸다.
사용자에게는 그것이 옳다 — 왜 안 되는지가 아니라 무엇을 하면 되는지가 필요하다. 그런데
**CI 로그에서도** 그 하나만 보이면, 지원해야 할 환경이 거부로 떨어졌을 때 원인을 알 방법이
없다. 그 환경은 원격에만 있고, 실패한 job 은 그 환경을 들고 있는 유일한 자리다.

그래서 같은 관문들을 순서대로 다시 밟으며 각 단계의 실측값을 낸다. 판정하지 않고 보고만
하므로 **항상 exit 0** 이다 — 이 스크립트가 job 을 붉게 만들면 진짜 실패가 가려진다.

출력은 ASCII 만 쓴다. Windows 러너 콘솔은 cp1252/cp949 로 열려 한글이 물음표로 뭉개진다.
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)


def main():
    print("== windows capability diagnostics ==")
    print(f"  platform={sys.platform} python={sys.version.split()[0]}")
    if os.name != "nt":
        print("  not applicable on this platform")
        return 0

    from sage import uninstall_windows_fs as w

    print(f"  is_windows={w._is_windows()}")
    print(f"  windows_10_or_later={w._windows_10_or_later()}")
    try:
        print(f"  getwindowsversion={tuple(sys.getwindowsversion())}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"  getwindowsversion raised: {exc!r}")

    api = w._Api.get()
    for name in ("NtCreateFile", "SetFileInformationByHandle",
                 "GetVolumeInformationByHandleW", "GetFileInformationByHandleEx"):
        print(f"  api.{name}={bool(getattr(api, name, None))}")

    roots = [os.path.join(REPO, "."), tempfile.gettempdir()]
    for root in roots:
        root = os.path.abspath(root)
        print(f"  --- root {root}")
        try:
            handle = w._open_root(root)
        except Exception as exc:                               # noqa: BLE001
            print(f"      _open_root raised: {type(exc).__name__}: {exc}")
            continue
        try:
            try:
                ok, filesystem, local = w.local_ntfs(handle)
                print(f"      local_ntfs ok={ok} filesystem={filesystem!r} local={local}")
            except Exception as exc:                           # noqa: BLE001
                print(f"      local_ntfs raised: {type(exc).__name__}: {exc}")
            try:
                attributes, tag = w._tag_info(handle)
                print(f"      attributes=0x{attributes:08x} reparse_tag=0x{tag:08x} "
                      f"is_reparse={bool(attributes & w.FILE_ATTRIBUTE_REPARSE_POINT)}")
            except Exception as exc:                           # noqa: BLE001
                print(f"      _tag_info raised: {type(exc).__name__}: {exc}")
                attributes = None
            info = os.stat(root)
            print(f"      os.stat mode=0o{w._stat_mode(info):o} "
                  f"st_dev={info.st_dev} st_ino={info.st_ino}")
            # **여기가 가장 자주 갈리는 자리다.** 어느 source 도 `os.stat` 과 맞지 않으면
            # 지원 환경이 거부로 떨어진다. 맞는 것이 없을 때 무엇이 얼마나 달랐는지가
            # 보이지 않으면 다음 수정은 추측이 된다.
            for source in w.IDENTITY_SOURCES:
                try:
                    derived = w.identity(handle, source=source)
                    mode = w._mode_of(attributes) if attributes is not None else None
                    anchor = (w._stat_mode(info), info.st_dev, info.st_ino)
                    print(f"      identity[{source}] = {(mode,) + derived} "
                          f"anchor = {anchor} match={((mode,) + derived) == anchor}")
                except Exception as exc:                       # noqa: BLE001
                    print(f"      identity[{source}] raised: {type(exc).__name__}: {exc}")
            try:
                names = w._entries(handle)
                print(f"      _entries ok, {len(names)} names")
            except Exception as exc:                           # noqa: BLE001
                print(f"      _entries raised: {type(exc).__name__}: {exc}")
        finally:
            w._close(handle)

    from sage import uninstall_fs as _fs
    cap = _fs.capability(tuple(os.path.abspath(r) for r in roots))
    print(f"  capability supported={cap.supported} backend={cap.backend} "
          f"failure_code={cap.failure_code} filesystem={cap.filesystem} "
          f"local_volume={cap.local_volume} identity_source={cap.identity_source}")
    print(f"  primitives={cap.primitives}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
