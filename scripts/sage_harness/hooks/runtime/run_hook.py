#!/usr/bin/env python3
"""run_hook — 설치된 thin 어댑터의 단일 진입점 (외부검토 R1 / P0-1).

shell 어댑터에 임베드돼 복제되던 Python 을 hook_runtime + io_{runtime} 로 들어올린 뒤,
어댑터 셸은 이 파일을 exec 만 한다(본문 단일소스). 입력: --runtime/--hook/--root/--core-dir, raw=stdin.

branch 는 SAGE_GATE_BRANCH 우선, 없으면 root 기준 git 으로 해석(원본 셸 BRANCH 로직 이식).
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # .../scripts/sage_harness/hooks/runtime
sys.path.insert(0, HERE)
import hook_runtime as hr   # noqa: E402
import io_claude            # noqa: E402
import io_codex             # noqa: E402

_IO = {"claude": io_claude, "codex": io_codex}


def _branch(root):
    b = os.environ.get("SAGE_GATE_BRANCH")
    if b:
        return b
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", required=True, choices=["claude", "codex"])
    ap.add_argument("--hook", required=True)
    ap.add_argument("--root", required=True)
    ap.add_argument("--core-dir", required=True)
    a = ap.parse_args()
    io = _IO[a.runtime]
    raw_text = sys.stdin.read()

    if a.hook == "pre-implementation-gate":
        rc = hr.run_pre_implementation_gate(io, a.root, a.core_dir, _branch(a.root), raw_text)
    else:
        # 아직 thin 전환 안 된 hook → 안전 통과(전환 완료 후 이 분기 제거).
        rc = 0
    sys.exit(rc)


if __name__ == "__main__":
    main()
