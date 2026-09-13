"""Windows 검증 보조 — 레이아웃 판정과 backend 신원을 한 줄로 낸다.

PowerShell here-string 안에 python 을 넣으면 인용 부호가 두 단계를 지나며 깨진다. 파일로 두면
그 층이 사라진다 — 원격 실행에서 스크립트를 `scp` 후 `-File` 로 부르는 것과 같은 이유다.
"""
import sys

sys.path.insert(0, sys.argv[1])


def main():
    what, root = sys.argv[2], sys.argv[3]
    if what == "layout":
        from sage import asset_paths
        print(asset_paths.detect_layout(root))
    elif what == "core":
        from sage import hook_entry
        print(hook_entry._resolve_core_dir(root, None))
    elif what == "backend":
        from sage import uninstall_fs
        cap = uninstall_fs.capability([root])
        print(f"{cap.backend}|{cap.supported}")
    else:
        raise SystemExit(f"unknown probe: {what}")


main()
