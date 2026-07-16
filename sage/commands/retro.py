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
    p.add_argument("--feature", default=None,
                   help="사이클 스템 — 05 문서 경로 필터 + human-gate 노트 제목. 예: loop-engineering")
    p.add_argument("--vault", nargs="?", const="", default=None,
                   help="Obsidian vault 에 human-gate 노트(approved:false) 작성. 경로 생략 시 profile.knowledge_capture.vault_path")
    p.add_argument("--no-vault", action="store_true",
                   help="이번 실행만 vault 노트 생략(retro_note 플래그가 켜져 있어도). --vault 보다 우선")
    p.add_argument("--check", default=None, metavar="NOTE",
                   help="retro 노트가 실제로 채워졌는지 결정론 검사(빈 템플릿/무효 제안이면 non-zero). "
                        "--run-id 를 함께 주면 그 run 의 노트인지도 대조")
    p.add_argument("--root", default=None)
    p.set_defaults(func=run)


def _load_retro_audit():
    """retro_audit 모듈 동적 import — _load_loop_audit 과 동일 패턴(hook 런타임 모듈을 sage 패키지가
    재사용, 반대 방향 의존은 없음). 9-C: `sage retro --check` 성공 증거를 Stop 훅이 사후 대조한다."""
    from sage import _resources
    rt = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks", "runtime")
    if rt not in sys.path:
        sys.path.insert(0, rt)
    import retro_audit as ra
    return ra


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
[MECHANISM] target 을 정하기 전 각 SAGE 필드/메커니즘의 *실제* 용도를 확인하라(이름만 보고 추측 금지):
- `profile.conventions`(+ convention-checker 에이전트) = convention 문서(경로/설정)를 리뷰 시 **참조**하는 의미적·advisory 경로. **결정론 grep 아님** — 에이전트가 그 문서를 보고 diff 를 점검할 뿐(스키마는 느슨한 배열, 강제 게이트 아님). 반복 코드 규칙을 "다음 리뷰에서 잡게" 하려면 여기 + convention doc(단 하드 차단은 아님).
- `risk.l3_content_keywords`/`risk.l3_filename_globs` = 위험도 분류 트리거(무엇을 L3 로 볼지). 안티패턴 탐지 아님.
- `risk.review_patterns` = **L3 리뷰 대상 문서 탐지용**(`claude_grep_first` 전략, scripts/sage_harness/hooks/strategies/). **코드 안티패턴 탐지가 아니다** — 여기에 코드 규칙을 넣지 말 것.
- `hook` = pre-implementation-gate 등 결정론 게이트(phase/risk 순서 강제) — **실제 결정론 차단은 여기**. 단 "범용 코드 안티패턴 grep" 전용 필드는 현재 없으므로, 그런 하드 차단이 필요하면 hook/전략 신설이 별도 과제다.
- `agent|skill` = 페르소나/체크리스트로 판단 유도(패턴화 불가한 것).
- `sage/asset_overrides/agents/*.md` · `sage/asset_overrides/skills/*.md` = 프로젝트 로컬 overlay. SAGE 가 eligible 자산의 overlay 를 CORE 렌더에 관리 블록으로 물리화(install/sync)하고 `sage validate` 가 게이트한다. `sage install --force` 가 ship 하지 않아 loop 학습이 보존된다. agent/skill 개선은 CORE 렌더 직접수정이 아니라 `/sage-asset-override` overlay 로 제안하라(게이트-보유 자산은 SD-8 전까지 overlay 미지원 → validate 가 안내).
[VERIFY] 제안한 target 이 실제로 그 결함을 다음부터 잡을 수 있는지, 해당 메커니즘의 소스(전략 스크립트/profile 스키마)를 확인한 뒤 확정하라.
[OUTPUT] 제안 목록(자동반영 아님):
[{ "pattern":"...", "evidence":["finding 근거/파일:라인"], "target":"hook|profile|agent|skill",
   "asset_id":"해당 agent/skill id(있을 때)", "proposed_change":"구체 patch 문구(profile 키/overlay 문장/hook spec 변경 등)", "confidence":"high|med|low" }]
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
    "    · 의미적(agent/skill):  /sage-asset-override 로 overlay 작성(install-safe) → SAGE 가 eligible 자산 렌더에 물리화, validate 가 게이트\n"
    "      범용화할 내용이면 별도 CORE/spec 변경으로 승격\n"
    "  feed-forward: 다음 feature 의 00 Prior-Knowledge Scan 이 반영분을 읽음."
)

# 노트 템플릿 ↔ --check 의 단일 소스. 이 문장이 그대로 남아 있으면 host 가 distill 을 돌리지 않은 것.
_SUMMARY_PLACEHOLDER = "_이번 사이클에 체계적으로 놓친 것과 바꾸기로 한 것을 사람이 읽을 1~2줄로 (absorb 파싱 대상 아님)._"
_PROPOSAL_TARGETS = ("profile", "hook", "agent", "skill")   # absorb 가 분기하는 target 어휘


def _derive_stem(feature, docs, rid):
    """human-gate 노트 파일명 stem → (stem, hint). 우선순위: --feature > 유일한 05 문서명 > run_id.

    run_id 폴백은 제목만으로 어떤 사이클인지 알아볼 수 없어(난수형) 마지막 수단이다. 05 문서가
    하나뿐이면 그 파일명이 곧 사이클 식별자이므로 결정론적으로 승격한다."""
    if feature:
        return feature, None
    if len(docs) == 1:
        return os.path.splitext(os.path.basename(docs[0]))[0], None
    reason = f"05 문서 {len(docs)}건 — 사이클 특정 불가" if docs else "05 문서 0건"
    return (rid or "cycle"), (
        f"노트 제목에 run_id 를 사용합니다({reason}). 제목만으로 사이클을 알아보려면 "
        f"`--feature <사이클 stem>` 을 주세요.")


def _summary_body(text):
    """`## 요약` 섹션 본문(다음 `## ` 헤딩 전까지). 헤딩 없음 → None."""
    m = re.search(r"(?m)^##[ \t]*요약[ \t]*$", text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"(?m)^##[ \t]", rest)
    return rest[:nxt.start()] if nxt else rest


def _check_note(path, root, run_id=None):
    """retro 노트가 실제로 채워졌는지 결정론 검사 → exit code.

    CLI 는 빈 템플릿만 쓰고 distill/작성은 host AI 에 맡긴다(설계: gather=결정론, distillation=판단).
    그 위임이 조용히 실패해도(요약 placeholder 그대로·제안 `[]`) 지금까지는 아무 게이트가 잡지
    못했다 — 이 검사가 완료 게이트의 결정론 백스톱이다.

    통과 조건: 노트가 대상 run 의 것(--run-id 를 준 경우) + `## 요약` 이 placeholder 를 넘어선 산문
    + `## 제안` 이 유효 JSON 배열이고 각 항목이 absorb 가 분기할 수 있는 형태(dict · target 어휘 ·
    비어있지 않은 proposed_change). 제안 0건은 '이번 사이클엔 구조적 패턴 없음' 이라는 정당한 결론일
    수 있어 통과시키되 경고한다.
    """
    # 노트 파서 단일화(absorb 가 읽는 블록과 동일) — check 통과가 absorb 파싱 성공을 함의해야 한다.
    from sage.commands.absorb import _extract_proposals, frontmatter_value

    # isfile: 디렉토리 경로도 exists() 는 참이라 read() 가 IsADirectoryError 로 터진다(오타 흔함).
    if not os.path.isfile(path):
        print(f"[sage retro --check] 노트 파일 없음: {path}", file=sys.stderr)
        return 2
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"[sage retro --check] 노트 읽기 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    problems = []

    # run 결속: 파일명에 run_id 가 없으므로 같은 stem/날짜의 *이전* run 노트가 재사용될 수 있다.
    # 그 노트는 이미 채워져 있어 검사를 통과 → 이번 run 은 회고 없이 완료 처리된다(게이트 우회).
    # 노트가 run 을 선언했는데 --run-id 를 안 주면 결속 검사가 통째로 꺼지므로, 생략 자체를 실패로 본다.
    noted = frontmatter_value(text, "run_id")
    if run_id:
        if noted != run_id:
            problems.append(f"노트 run_id={noted!r} ≠ 대상 run_id={run_id!r} — 다른 사이클의 회고 노트")
    elif noted:
        problems.append(f"--run-id 미전달 — 이 노트는 run_id={noted!r} 에 결속돼 있어 대조가 필요합니다 "
                        f"(`--run-id {noted}`)")

    body = _summary_body(text)
    if body is None:
        problems.append("`## 요약` 헤딩이 없음(노트 구조 손상)")
    else:
        # placeholder 를 지웠든 그 아래에 덧붙였든 통과 — 남은 산문이 있으면 사람이 쓴 것.
        prose = "\n".join(l for l in body.splitlines() if l.strip() and _SUMMARY_PLACEHOLDER not in l).strip()
        if not prose:
            problems.append("`## 요약` 이 비었거나 템플릿 placeholder 그대로 — 사이클 회고가 작성되지 않음")

    proposals, err = _extract_proposals(text)
    if err:
        problems.append(f"`## 제안` 파싱 불가: {err}")
    else:
        for i, p in enumerate(proposals):
            if not isinstance(p, dict):
                problems.append(f"제안[{i}] 이 객체가 아님: {p!r}")
                continue
            if p.get("target") not in _PROPOSAL_TARGETS:
                problems.append(f"제안[{i}] target={p.get('target')!r} — {list(_PROPOSAL_TARGETS)} 중 하나여야 absorb 가 분기")
            if not str(p.get("proposed_change") or "").strip():
                problems.append(f"제안[{i}] proposed_change 가 비었음")

    if problems:
        print(f"== sage retro --check ({os.path.basename(path)}) — 미완성 ==", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print("\n노트를 열어 distiller 결과로 `## 요약`(사람용 1~2줄)과 `## 제안`(JSON 배열)을 채운 뒤 "
              "다시 실행하세요. 증거·프롬프트는 노트 하단 <details> 에 있습니다.", file=sys.stderr)
        return 1

    n = len(proposals)
    print(f"== sage retro --check ({os.path.basename(path)}) — OK ==")
    print(f"  요약 작성됨 · 제안 {n}건" + (" (전부 유효 target)" if n else ""))
    if n == 0:
        print("  ⚠️  제안 0건 — 구조적 패턴이 정말 없었다면 정상이나, 그 판단 근거를 완료 보고에 남기세요.")

    # 9-C: 성공 증거를 .sage/retro_audit.jsonl 에 기록 — Stop 훅(retro_gate)이 이 run 이 실제로
    # check 를 통과했는지 사후 대조한다. 기록 실패는 --check 자체를 실패로 본다: 기록 안 된 성공은
    # 게이트가 못 보는 성공과 같다(codex 설계리뷰 1R). run_id 를 특정할 수 없으면(--run-id 도 없고
    # 노트도 선언 안 함) 대조 대상이 없어 조용히 건너뛴다 — 그 경우도 위에서 이미 검증됐다.
    bind_id = run_id or noted
    if bind_id:
        try:
            ra = _load_retro_audit()
            ra.record_check(root, bind_id, path, text)
        except Exception as e:
            print(f"[sage retro --check] retro_audit 기록 실패: {type(e).__name__}: {e} "
                  f"— 게이트가 이 사이클을 완료로 인식할 수 없습니다.", file=sys.stderr)
            return 2

    print("  다음: 사람이 검토 후 frontmatter `approved: true` → `sage absorb --from-retro <노트>`")
    return 0


def run(args):
    root = os.path.abspath(args.root) if args.root else _find_project_root(os.getcwd())
    if args.check:
        return _check_note(args.check, root, args.run_id)

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
        # --no-vault 는 이 run 을 "노트 생략"으로 감사에 남겨 Stop 게이트가 없는 노트의 --check 를 요구하지
        # 않게 한다(게이트 면제 생성). 일반 조회보다 엄격하게 결속한다:
        #  · run 이 정확히 1개면 자동 결속 허용   · 2개↑면 --run-id 필수(엉뚱한 최신 run 자동 면제 방지)
        #  · 명시 --run-id 는 실재 run 이어야 함(임의 id 우회 차단)   · 기록 실패는 fail-fast(기록 안 된 skip=게이트 미가시)
        real_runs = list(la.runs(root))
        target = None
        if args.run_id:
            if args.run_id not in real_runs:
                print(f"⛔ [sage retro --no-vault] run_id={args.run_id} 는 실재하는 loop_audit run 이 아닙니다 "
                      f"— skip 미기록(게이트 우회 방지).", file=sys.stderr)
                return 2
            target = args.run_id
        elif len(real_runs) == 1:
            target = real_runs[0]   # 단일 run 자동 결속
        elif len(real_runs) >= 2:
            print(f"⛔ [sage retro --no-vault] loop_audit run 이 {len(real_runs)}개 — 어느 run 을 면제할지 "
                  f"모호합니다. --run-id 로 명시하세요(엉뚱한 최신 run 자동 면제 방지).", file=sys.stderr)
            return 2
        else:
            # 결속할 run 자체가 없음(단발 리뷰 등) — 게이트는 06 Loop-Run 결속으로만 판정하므로 skip 불필요.
            print("  ℹ️  [--no-vault] 결속할 loop_audit run 이 없어 skip 미기록(노트만 생략).", file=sys.stderr)
        if target:
            try:
                _load_retro_audit().record_skip(root, target, reason="no_vault")
            except Exception as e:
                print(f"⛔ [sage retro --no-vault] retro_audit skip 기록 실패: {type(e).__name__}: {e} "
                      f"— 기록 안 된 skip 은 게이트가 못 봅니다(false BLOCK).", file=sys.stderr)
                return 2
    else:
        vault_arg = args.vault
        if vault_arg is None and kc.get("retro_note") is True:
            vault_arg = ""   # profile vault_path 사용(자동 활성)
    if vault_arg is not None:
        raw_stem, stem_hint = _derive_stem(args.feature, docs, rid)
        if stem_hint:
            print(f"  ℹ️  {stem_hint}", file=sys.stderr)
        _write_vault_note(profile, root, rid, raw_stem, out, vault_arg or None)
    return 0


def _write_vault_note(profile, root, rid, raw_stem, out_lines, override):
    """retro 패킷을 vault 에 human-gate 노트(approved:false)로 작성. 사람이 Obsidian 에서 검토·승인."""
    from sage.commands import _vault
    vault, folder = _vault.vault_target(profile, override, root)
    if not vault:
        print("  ℹ️  vault 비활성(knowledge_capture.vault_path 미설정, --vault 경로도 없음) → 노트 생략", file=sys.stderr)
        return
    import datetime
    from sage.commands.knowledge import _note_filename
    from sage.commands._common import _project_name
    from sage.commands.review_loop import _dashboard_filename, _wiki_stem, _write_vault_dashboard
    # 파일명 stem 은 사용자 입력(--feature)이거나 05 문서명일 수 있으므로 경로 탈출 방지 — 안전 문자만 남긴다.
    # 비-ASCII 낱말문자(한글 등)는 보존: 구분자만 제거하면 탈출은 막히고(+ _note_filename 이 basename),
    # ASCII-only 로 깎으면 한글 사이클명이 통째로 사라져 제목이 다시 식별 불가가 된다.
    stem = re.sub(r"[^\w.-]", "-", raw_stem, flags=re.UNICODE).strip("-.") or "cycle"
    today = datetime.date.today().isoformat()
    # 파일명은 vault note_convention(prefix + filename_pattern)을 따른다 — loop-audit 대시보드와 동일 방식.
    # 프로젝트/stem/날짜로 유일성 유지(같은 날 재실행 create-only 보존). project.name 비면 'SAGE' 폴백.
    name = _project_name(profile) or "SAGE"
    fname = _note_filename(profile, "TECH", f"{name} retro {stem} {today}")
    # 파일명은 run_id 를 담지 않는다(제목 식별성). 그래서 같은 날 같은 stem 의 *다른* run 이 돌면
    # create-only 가 앞 run 의 (이미 채워진) 노트를 그대로 두어, 이번 run 이 회고 없이 완료 게이트를
    # 통과한다. 충돌할 때만 run suffix 로 분리 — 흔한 경우의 제목은 그대로 두면서 결속을 지킨다.
    if rid:
        prior = os.path.join(vault, folder, fname)
        if os.path.isfile(prior):
            from sage.commands.absorb import frontmatter_value
            try:
                prev_rid = frontmatter_value(open(prior, encoding="utf-8").read(), "run_id")
            except (OSError, UnicodeDecodeError):
                prev_rid = None
            if prev_rid and prev_rid != rid:
                fname = _note_filename(profile, "TECH", f"{name} retro {stem} {today} {rid}")
                print(f"  ℹ️  같은 이름의 노트가 다른 run({prev_rid})의 것 → 이번 run 은 별도 노트로 작성",
                      file=sys.stderr)
    dash_name = _dashboard_filename(profile)
    fm = {"tags": ["sage", "retro", "loop-c"], "approved": False, "run_id": rid or "",
          "date": today, "status": "pending-review"}
    check_cmd = f"sage retro --check <이 노트>" + (f" --run-id {rid}" if rid else "")
    body = ("> **Loop C retro — human gate.** `## 요약` 에 사람용 회고 1~2줄, `## 제안` JSON 에 distill 결과를\n"
            f"> 채운 뒤(`{check_cmd}` 로 확인) 검토해 frontmatter `approved: true` 로 승인하세요.\n"
            "> 그 다음 `sage absorb --from-retro <이 노트>` 로 자산 patch 후보를 받습니다.\n"
            "> 자동 반영되지 않습니다(SSOT 보호).\n\n"
            f"관련 loop audit: [[{_wiki_stem(dash_name)}]]\n\n"
            "## 요약\n"
            f"{_SUMMARY_PLACEHOLDER}\n\n"
            "## 제안 (proposals) — distill 결과를 JSON 배열로 채우세요. target ∈ {profile,hook,agent,skill}\n"
            "```json\n[]\n```\n\n"
            "---\n"
            "<details>\n<summary>증거 · distiller 프롬프트 (참고 — 채울 때만 사용, absorb 는 위 `## 제안` JSON 만 읽음)</summary>\n\n"
            "```\n" + "\n".join(out_lines) + "\n```\n\n</details>\n")
    # create-only: 같은 날 재실행이 사람이 검토/승인(approved:true)한 노트를 덮어쓰지 않게(codex S5 P2).
    path = _vault.write_note(vault, folder, fname, fm, body, create_only=True)
    if path is None:
        path = os.path.join(vault, folder, fname)
        print(f"  ℹ️  retro 노트가 이미 존재 — 사람 검토 상태 보존(덮지 않음): {path}", file=sys.stderr)
    else:
        print(f"  ✅ Obsidian retro human-gate 노트 작성(approved:false): {path}", file=sys.stderr)
    # 노트는 빈 템플릿으로 나간다 — 채우는 건 host 몫이므로, 검산 명령을 여기서 못박아 전달한다.
    # --run-id 를 포함해 출력한다: 빠뜨리면 run 결속 검사가 꺼져 남의 노트로 통과할 수 있다.
    rid_arg = f' --run-id {rid}' if rid else ""
    print(f'  ▶ 다음: 노트의 `## 요약`/`## 제안` 을 distill 결과로 채운 뒤 '
          f'`python -m sage retro --check "{path}"{rid_arg}` (미완성이면 non-zero)', file=sys.stderr)
    try:
        _write_vault_dashboard(_load_loop_audit(root), root, override)
    except Exception as e:
        print(f"  ⚠️  loop audit 대시보드 retro 링크 갱신 실패: {type(e).__name__}: {e}", file=sys.stderr)
