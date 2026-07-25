"""sage feedback: `sage-feedback ::` 개발자 피드백 마커 조회 (§10-a-C).

마커 **처리**(계획 문서 대조 → 3분기 판정 → 수정/제거/되질문)는 `/sage-feedback` 스킬이
reviewer 에이전트로 수행한다. 이 CLI 는 그 스킬과 게이트가 공유하는 **결정론 스캔 표면**만
제공한다 — 어디에 어떤 마커가 몇 개 있는지는 AI 판단 없이 확정할 수 있어야 하기 때문이다.

`--record` 도 같은 분업이다: 판정은 스킬이 하고 여기서는 적기만 한다. 기록 여부·대상은
프로필(`feedback.record`·`record_target`)이 정하므로 스킬은 매번 같은 명령을 호출하면 된다.
"""
import json
import os
import re
import sys

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
    parser.add_argument("--release-gate", action="store_true",
                        help="feedback.block_release 가 true 일 때만 미해결 차단성 마커로 2 종료 "
                             "(릴리즈 CI 가 무조건 호출하고 판정은 프로필이 한다)")
    parser.add_argument("--record", action="store_true",
                        help="마커 1건의 처리 결과를 기록한다(--path/--line/--verdict/--note 필요)")
    parser.add_argument("--path", help="--record: 마커가 있던 저장소 상대 경로")
    parser.add_argument("--line", type=int, help="--record: 마커 줄 번호")
    parser.add_argument("--verdict", choices=list(fb.VERDICTS),
                        help="--record: 3분기 판정 (fixed=수정함 | intentional=불일치 아님 | "
                             "undetermined=판단 불가·마커 유지)")
    parser.add_argument("--note", help="--record: 판단 근거 한 줄(계획 문서의 어느 부분인지)")
    parser.add_argument("--cycle-stem", default=None,
                        help="--record: 그 코드를 만든 사이클 stem(vault 노트 단위)")
    parser.add_argument("--vault", nargs="?", const="", default=None,
                        help="--record: vault 경로 오버라이드(생략 시 profile vault_path)")
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

    if args.record:
        return _run_record(args, root, profile)

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

    if blockers and args.exit_code:
        return 2
    # --release-gate 는 강제력 판단을 프로필로 넘긴다. CI 는 프로젝트마다 분기하지 않고 항상
    # 이 한 줄을 호출하고, 막을지 말지는 feedback.block_release 가 정한다.
    if blockers and args.release_gate and fb.block_release(profile):
        print("차단성 마커가 남아 릴리즈를 차단합니다 (feedback.block_release=true).")
        return 2
    return 0


def _safe_rel(value):
    """저장소 상대경로로 정규화. 절대경로·`..` 는 거부(기록 경로가 저장소 밖을 가리키지 못하게)."""
    rel = (value or "").strip().replace(os.sep, "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    return rel


def _marker_at(root, rel, line):
    """해당 줄에 지금도 마커가 있으면 반환. 기록 정합성 확인용(파일 1건만 읽는다)."""
    try:
        with open(os.path.join(root, rel), "rb") as handle:
            raw = handle.read()
        if b"\0" in raw:
            return None
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return next((m for m in fb.scan_text(text, rel) if m.line == line), None)


def _run_record(args, root, profile):
    """마커 1건의 처리 결과를 기록한다. 판정은 `/sage-feedback` 스킬이 하고 여기서는 적기만 한다."""
    missing = [name for name, value in (("--path", args.path), ("--line", args.line),
                                        ("--verdict", args.verdict), ("--note", args.note))
               if value is None]
    if missing:
        print(f"[sage feedback] --record 에는 {', '.join(missing)} 이(가) 필요합니다", file=sys.stderr)
        return 2
    rel = _safe_rel(args.path)
    if rel is None:
        print(f"[sage feedback] --path 가 저장소 상대경로가 아님: {args.path!r}", file=sys.stderr)
        return 2
    if not fb.enabled(profile):
        # 스캔은 조용히 무동작이지만 기록은 명시 요청이라 침묵하면 안 된다 — 기록됐다고 오인한다.
        print("[sage feedback] feedback.enabled 가 false — 기록하지 않습니다 "
              "(sage/project-profile.yaml 의 feedback.enabled 를 true 로).", file=sys.stderr)
        return 2
    if not fb.record_enabled(profile):
        print("[sage feedback] feedback.record 가 false — 기록 없이 채팅 응답만 남깁니다(기본 정책).")
        return 0

    marker = _marker_at(root, rel, args.line)
    if args.verdict == fb.VERDICT_UNDETERMINED and marker is None:
        print(f"  ⚠️  판단 불가로 기록하는데 {rel}:{args.line} 에 마커가 없습니다 — "
              "판단 불가 분기는 마커를 유지해야 합니다.", file=sys.stderr)
    if args.verdict != fb.VERDICT_UNDETERMINED and marker is not None:
        print(f"  ⚠️  해소로 기록하는데 {rel}:{args.line} 에 마커가 남아 있습니다 — "
              "해소 분기는 마커를 제거합니다.", file=sys.stderr)

    record = fb.build_record(rel, args.line, args.verdict, args.note,
                             blocking=marker.blocking if marker else False,
                             marker_text=marker.text if marker else None,
                             cycle_stem=args.cycle_stem)
    target = fb.record_target(profile)
    note_path = None
    if target in ("auto", "vault"):
        # `--vault` bare("") 는 profile vault_path 사용(retro 와 동일 관례) — override 는 명시 경로만.
        note_path = _write_vault_entry(profile, root, record, args.vault or None)
    # 감사 로그는 기본 축이다. 명시 `vault` 여도 vault 가 비활성이면 여기로 떨어뜨린다 —
    # 기록하라고 켠 설정이 조용히 아무것도 안 남기는 것이 최악이다.
    if target != "vault" or note_path is None:
        print(f"  ✅ 기록: {fb.append_record(root, record)}")
    if note_path:
        print(f"  ✅ vault 사이클 노트: {note_path}")
    elif target == "vault":
        print("  ℹ️  vault 비활성(knowledge_capture.vault_path 미설정) → 감사 로그에만 기록",
              file=sys.stderr)
    return 0


def _write_vault_entry(profile, root, record, override):
    """사이클 stem 단위 노트에 사람이 읽는 서술을 누적한다(없으면 헤더와 함께 생성).

    기계 판독·감사는 단일 누적 JSONL, 사람이 읽는 서술은 사이클 단위 — 같은 사건을 두 축에 남긴다.
    사이클 단위인 이유는 SAGE 의 기존 감사 축(plan_docs·05/06 evidence·retro)이 전부 그 단위이기
    때문이다. 전역 단일 노트는 비대해지고, 마커당 노트 하나는 vault 를 오염시킨다."""
    from sage.commands import _vault
    vault, folder = _vault.vault_target(profile, override, root)
    if not vault:
        return None
    from sage.commands._common import _project_name
    from sage.commands.knowledge import _note_filename
    # 경로 탈출 방지 — stem 은 사용자 입력이다. 한글 등 비-ASCII 낱말문자는 보존한다(retro 와 동일):
    # 구분자만 제거하면 탈출은 막히고, ASCII-only 로 깎으면 한글 사이클명이 통째로 사라진다.
    stem = re.sub(r"[^\w.-]", "-", record.get("cycle_stem") or "", flags=re.UNICODE).strip("-.")
    name = _project_name(profile) or "SAGE"
    # stem 미특정(사이클 식별 실패)은 별도 노트로 모은다 — 엉뚱한 사이클 노트에 섞는 것보다 낫다.
    title = f"{name} feedback {stem}" if stem else f"{name} feedback 미분류"
    fname = _note_filename(profile, "SAGE", title)
    fm = {"tags": ["sage", "feedback"], "cycle_stem": record.get("cycle_stem") or "",
          "source": "sage feedback --record"}
    header = (f"> `/sage-feedback` 개발자 피드백 마커 처리 이력 — 사이클 `{record.get('cycle_stem') or '미분류'}`.\n"
              "> 기계 판독용 원본은 `.sage/feedback.jsonl` 이다.\n\n"
              "## 처리 이력\n\n")
    path = _vault.write_note(vault, folder, fname, fm, header, create_only=True)
    if path is None:                     # 이미 있는 노트에 누적
        path = os.path.join(vault, folder, os.path.basename(fname))
        if os.path.islink(path):
            # 심링크면 따라가지 않는다 — vault 밖을 가리키는 링크로 기록이 새는 것을 막는다.
            os.unlink(path)
            path = _vault.write_note(vault, folder, fname, fm, header, create_only=True) or path
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(_vault_entry_md(record))
    return path


_VERDICT_LABEL = {fb.VERDICT_FIXED: "수정함", fb.VERDICT_INTENTIONAL: "불일치 아님",
                  fb.VERDICT_UNDETERMINED: "판단 불가(마커 유지)"}


def _vault_entry_md(record):
    force = "차단성" if record.get("blocking") else "advisory"
    lines = [f"### `{record['path']}:{record['line']}` — {_VERDICT_LABEL.get(record['verdict'], record['verdict'])}",
             f"- {record['ts']} · {force} · by {record['user']}"]
    if record.get("marker_text"):
        lines.append(f"- 마커: {record['marker_text']}")
    lines.append(f"- 판단: {record['note']}")
    return "\n".join(lines) + "\n\n"
