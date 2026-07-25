"""sage feedback: `sage-feedback ::` 개발자 피드백 마커 조회 (§10-a-C).

마커 **처리**(계획 문서 대조 → 3분기 판정 → 수정/제거/되질문)는 `/sage-feedback` 스킬이
reviewer 에이전트로 수행한다. 이 CLI 는 그 스킬과 게이트가 공유하는 **결정론 스캔 표면**만
제공한다 — 어디에 어떤 마커가 몇 개 있는지는 AI 판단 없이 확정할 수 있어야 하기 때문이다.
"""
import json
import os

from sage import feedback as fb
from sage.profile_layers import load_profile_layers


def register(sub):
    parser = sub.add_parser("feedback", help="sage-feedback 마커를 스캔해 보여줍니다")
    parser.add_argument("--root", default=None, help="프로젝트 루트(기본: profile 을 가진 상위 디렉토리)")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    parser.add_argument("--blocking-only", action="store_true",
                        help="차단성(!sage-feedback) 마커만 표시")
    parser.add_argument("--exit-code", action="store_true",
                        help="미해결 차단성 마커가 있으면 2 로 종료(스크립트·CI 용)")
    parser.set_defaults(func=run)


def _find_project_root(start):
    """프로젝트 루트 = sage/project-profile.yaml 보유 디렉토리. 폴백 cwd (retro CLI 와 동일 마커)."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "sage", "project-profile.yaml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def _load_profile(root):
    layers = load_profile_layers(os.path.join(root, "sage", "project-profile.yaml"))
    return {} if layers.has_fail else layers.effective


def run(args):
    root = os.path.abspath(args.root) if args.root else _find_project_root(os.getcwd())
    profile = _load_profile(root)

    if not fb.enabled(profile):
        # 하위호환: feedback 섹션이 없거나 꺼진 프로필에서 조용히 무동작(스캔조차 하지 않음).
        if args.output == "json":
            print(json.dumps({"enabled": False, "markers": []}, ensure_ascii=False, indent=2))
        else:
            print("[sage feedback] feedback.enabled 가 false — 스캔하지 않습니다 "
                  "(sage/project-profile.yaml 의 feedback.enabled 를 true 로).")
        return 0

    markers = fb.scan(root, profile)
    shown = fb.blocking(markers) if args.blocking_only else markers
    blockers = fb.blocking(markers)

    if args.output == "json":
        print(json.dumps({"enabled": True,
                          "counts": {"total": len(markers), "blocking": len(blockers)},
                          "markers": [m.as_dict() for m in shown]},
                         ensure_ascii=False, indent=2))
    else:
        if not shown:
            print("[sage feedback] 마커 없음.")
        for marker in shown:
            mark = "!" if marker.blocking else " "
            print(f"  {mark} {marker.path}:{marker.line}  {marker.text}")
        print(f"\n총 {len(markers)}건 (차단성 {len(blockers)}건)")
        if blockers:
            print("차단성 마커는 해당 코드를 포함하는 범위의 03 구현 진입을 막습니다. "
                  "`/sage-feedback` 으로 처리하세요.")

    if args.exit_code and blockers:
        return 2
    return 0
