"""sage retro — Loop C (Act→Plan process-absorb): 사이클 학습을 자산 개선 *제안*으로 (자동반영 없음).

PDCA 의 빈 Act→Plan arm 을 닫는다. Loop A(Phase 05) 가 잡아낸 것 = host AI 가 *체계적으로 놓친 것*.
retro 는 그 증거(loop_audit 라운드 집계 + 05 리뷰 문서)를 결정론적으로 모아 distiller 프롬프트와 함께
제시한다. 패턴 분류(기계적→hook/profile · 의미적→agent/skill)는 판단이므로 host AI 가 프롬프트로 수행한다
(SAGE CLI 는 LLM 없음 — sage-review 와 같은 결정론/interpretive 분리). 적용은 absorb 철학 그대로:
제안 → 사람 승인 → 정상 generate/validate. 자동 반영하지 않는다(SSOT 보호).

증거 축:
- loop_audit: 라운드별 found/survived/accepted 집계 = 리뷰가 채운 누락의 양(결정론).
- 05 plan 문서: finding 텍스트(패턴 분류의 원천) — retro 는 경로를 가리키고 AI 가 정독한다.
"""
import glob
import os
import re
import sys


def register(sub):
    p = sub.add_parser("retro", help="리뷰 사이클 학습을 자산 개선 제안으로 정리합니다(Loop C, 자동반영 없음)")
    p.add_argument("--run-id", default=None, help="대상 loop_audit run_id(기본: 최신)")
    p.add_argument("--feature", default=None, help="05 문서 경로 필터(스템). 예: loop-engineering")
    p.add_argument("--vault", nargs="?", const="", default=None,
                   help="Obsidian vault 에 human-gate 노트(approved:false) 작성. 경로 생략 시 profile.knowledge_capture.vault_path")
    p.add_argument("--no-vault", action="store_true",
                   help="이번 실행만 vault 노트 생략(retro_note 플래그가 켜져 있어도). --vault 보다 우선")
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _load_loop_audit(root):
    from sage import _resources
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import loop_audit as la
    return la


def _find_project_root(start):
    """프로젝트 루트 = sage/project-profile.yaml 보유 디렉토리(plan_docs·.sage 가 여기 있음). 폴백 cwd.
    review_loop CLI 와 동일 마커 — 서브디렉토리에서 실행해도 같은 .sage/plan_docs 를 본다."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.exists(os.path.join(cur, "sage", "project-profile.yaml")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def _load_profile(root):
    """<root>/sage/project-profile.yaml → dict. 없음/실패 → {}. (run 에서 1회 로드해 재사용)"""
    ppath = os.path.join(root, "sage", "project-profile.yaml")
    if not os.path.exists(ppath):
        return {}
    try:
        import yaml
        prof = yaml.safe_load(open(ppath, encoding="utf-8")) or {}
        return prof if isinstance(prof, dict) else {}
    except Exception:
        return {}


def _approve_glob(profile):
    """05(approve) phase 글롭 — profile.pdca.phases 에서 approve_phase id 의 glob 을 읽어 도메인값 0.
    실패/미설정 시 표준 기본값(plan_docs/05-expert-review/**/*.md)."""
    default = os.path.join("plan_docs", "05-expert-review", "**", "*.md")
    pdca = profile.get("pdca") or {}
    approve_id = pdca.get("approve_phase", "05")
    for ph in (pdca.get("phases") or []):
        if isinstance(ph, dict) and ph.get("id") == approve_id and ph.get("glob"):
            return ph["glob"]
    return default


_DISTILLER_PROMPT = """\
[ROLE] 너는 회고(retro) 분석가다.
[INPUT]
- 루프 라운드 집계(아래 '감사 요약')  — 리뷰가 채운 누락의 양/추이
- 05 리뷰 문서(아래 경로)의 채택 finding 텍스트  — 무엇을 놓쳤는지
[TASK] 이 host 가 *체계적으로 놓치는 패턴*만 추출하라(1회성 실수 제외, 반복·구조적인 것만). 각 패턴을 분기:
- 기계로 탐지 가능(파일패턴/키워드/구조 신호 있음) → target = hook | profile  (다음부터 결정론 강제 차단)
- 의미적(판단 필요, 패턴화 불가)                  → target = agent | skill   (다음부터 페르소나/체크리스트로 유도)
[OUTPUT] 제안 목록(자동반영 아님):
[{ "pattern":"...", "evidence":["finding 근거/파일:라인"], "target":"hook|profile|agent|skill",
   "proposed_change":"구체 patch 문구(profile 키/컨벤션 문장/agent 체크리스트 등)", "confidence":"high|med|low" }]
"""


def _fmt_audit(la, root, run_id):
    """감사 요약 + 대상 run_id 반환. run_id 없으면 최신. 기록 없으면 (None, [])."""
    runs = la.runs(root)
    if not runs:
        return None, ["(loop_audit 기록 없음 — review_loop 루프가 아직 돈 적 없음. 단발 리뷰면 05 문서만 참고)"]
    rid = run_id or runs[-1]
    rounds = la.rounds_of(root, rid)
    close = la.close_of(root, rid)
    lines = [f"run_id={rid}" + ("" if rid in runs else "  ⚠️ (해당 run_id 의 loop_open 없음)")]
    tot = {"found": 0, "survived": 0, "accepted": 0, "arch": 0}
    for r in rounds:
        for k in tot:
            tot[k] += int(r.get(k, 0) or 0)
        lines.append(f"  [{r.get('iteration')}] found={r.get('found')} survived={r.get('survived')} "
                     f"accepted={r.get('accepted')} arch={r.get('arch')} tokens={r.get('tokens')}")
    lines.append(f"  합계: found={tot['found']} survived={tot['survived']} accepted={tot['accepted']} "
                 f"arch={tot['arch']}  → accepted={tot['accepted']} 가 '리뷰가 채운 체계적 누락'의 양")
    if close:
        lines.append(f"  종료: {close.get('result')}/{close.get('reason')} ({close.get('iterations')}회)")
    else:
        lines.append("  종료: (미종료 — 진행중이거나 close 누락)")
    return rid, lines


_APPLY_PATH = (
    "【 적용 경로 (absorb 철학 — 자동 반영 절대 없음) 】\n"
    "  제안 → 사람 승인 → 자산 수정:\n"
    "    · 기계적(hook/profile): spec/profile 수정 → sage generate → sage validate\n"
    "    · 의미적(agent/skill):  spec(intent/advisory_scope) 보강 → sage generate --kind agent|skill → sage validate\n"
    "  feed-forward: 다음 feature 의 00 Prior-Knowledge Scan 이 반영분을 읽음."
)


def run(args):
    root = os.path.abspath(args.root) if args.root else _find_project_root(os.getcwd())
    profile = _load_profile(root)
    la = _load_loop_audit(root)

    rid, audit_lines = _fmt_audit(la, root, args.run_id)

    # 05 리뷰 문서 수집(finding 텍스트 원천) — approve phase 글롭. --feature 로 경로 필터.
    pattern = os.path.join(root, _approve_glob(profile))
    docs = sorted(glob.glob(pattern, recursive=True))
    if args.feature:
        # 파일명(basename)에서 -/_/. 로 구분된 토큰 경계 매치(codex S4 P3). raw 부분문자열은
        # 'loop' 이 'preloop' 이나 부모 디렉토리 세그먼트까지 오매치 → 무관 05 문서가 증거에 섞임.
        feat_re = re.compile(r"(^|[-_.])" + re.escape(args.feature) + r"([-_.]|$)")
        docs = [d for d in docs if feat_re.search(os.path.basename(d))]

    integ = la.integrity_issues(root)

    # 본문 1회 구성 → stdout + (vault 활성 시) human-gate 노트 공용.
    out = ["== sage retro (Loop C — process-absorb 제안 / 자동반영 없음) ==", "",
           "【 감사 요약 — 리뷰가 잡은 host 의 체계적 누락 】", *audit_lines, "",
           "【 05 리뷰 문서(채택 finding 텍스트 원천 — AI 가 정독) 】"]
    if docs:
        out += [f"  · {os.path.relpath(d, root)}" for d in docs]
    else:
        out.append(f"  (없음 — {os.path.relpath(pattern, root)} 매치 0. 05 리뷰 문서가 있어야 패턴 분류 가능)")
    out += ["", "【 distiller 프롬프트 (host AI 가 위 증거로 실행) 】", _DISTILLER_PROMPT, _APPLY_PATH]
    if integ:
        out += ["", "⚠️  loop_audit 무결성 경고(증거 신뢰성 점검):"] + [f"   - {i}" for i in integ]

    print("\n".join(out))

    # vault 결정 우선순위: --no-vault(명시 off) > --vault PATH(명시 경로) > --vault(bare)/retro_note(profile 경로) > 없음.
    kc = profile.get("knowledge_capture")
    kc = kc if isinstance(kc, dict) else {}   # 비-dict 방어(codex A — .get 크래시 방지)
    if args.no_vault:
        vault_arg = None
    else:
        vault_arg = args.vault
        if vault_arg is None and kc.get("retro_note") is True:
            vault_arg = ""   # profile vault_path 사용(자동 활성)
    if vault_arg is not None:
        _write_vault_note(profile, root, rid, args.feature, out, vault_arg or None)
    return 0


def _write_vault_note(profile, root, rid, feature, out_lines, override):
    """retro 패킷을 vault 에 human-gate 노트(approved:false)로 작성. 사람이 Obsidian 에서 검토·승인."""
    from sage.commands import _vault
    vault, folder = _vault.vault_target(profile, override)
    if not vault:
        print("  ℹ️  vault 비활성(knowledge_capture.vault_path 미설정, --vault 경로도 없음) → 노트 생략", file=sys.stderr)
        return
    import datetime
    from sage.commands.knowledge import _note_filename
    from sage.commands._common import _project_name
    # 파일명 stem 은 사용자 입력(--feature)일 수 있으므로 경로 탈출 방지 — 안전 문자만 남긴다.
    raw_stem = feature or rid or "cycle"
    stem = re.sub(r"[^A-Za-z0-9._-]", "-", raw_stem).strip("-.") or "cycle"
    today = datetime.date.today().isoformat()
    # 파일명은 vault note_convention(prefix + filename_pattern)을 따른다 — loop-audit 대시보드와 동일 방식.
    # 프로젝트/stem/날짜로 유일성 유지(같은 날 재실행 create-only 보존). project.name 비면 'SAGE' 폴백.
    name = _project_name(profile) or "SAGE"
    fname = _note_filename(profile, "TECH", f"{name} retro {stem} {today}")
    fm = {"tags": ["sage", "retro", "loop-c"], "approved": False, "run_id": rid or "",
          "date": today, "status": "pending-review"}
    body = ("> **Loop C retro — human gate.** `## 요약` 에 사람용 회고 1~2줄, `## 제안` JSON 에 distill 결과를\n"
            "> 채운 뒤 검토해 frontmatter `approved: true` 로 승인하세요. 그 다음 `sage absorb --from-retro <이 노트>`\n"
            "> 로 자산 patch 후보를 받습니다. 자동 반영되지 않습니다(SSOT 보호).\n\n"
            "## 요약\n"
            "_이번 사이클에 체계적으로 놓친 것과 바꾸기로 한 것을 사람이 읽을 1~2줄로 (absorb 파싱 대상 아님)._\n\n"
            "## 제안 (proposals) — distill 결과를 JSON 배열로 채우세요. target ∈ {profile,hook,agent,skill}\n"
            "```json\n[]\n```\n\n"
            "---\n"
            "<details>\n<summary>증거 · distiller 프롬프트 (참고 — 채울 때만 사용, absorb 는 위 `## 제안` JSON 만 읽음)</summary>\n\n"
            "```\n" + "\n".join(out_lines) + "\n```\n\n</details>\n")
    # create-only: 같은 날 재실행이 사람이 검토/승인(approved:true)한 노트를 덮어쓰지 않게(codex S5 P2).
    path = _vault.write_note(vault, folder, fname, fm, body, create_only=True)
    if path is None:
        print(f"  ℹ️  retro 노트가 이미 존재 — 사람 검토 상태 보존(덮지 않음): "
              f"{os.path.join(vault, folder, fname)}", file=sys.stderr)
    else:
        print(f"  ✅ Obsidian retro human-gate 노트 작성(approved:false): {path}", file=sys.stderr)
