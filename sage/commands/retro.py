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
import importlib
import os
import re
import sys
from pathlib import Path

from sage.profile_layers import LOCAL_PROFILE_NAME, load_profile_layers
from sage.i18n import CATALOGS, language_of, render_issue, tr


def register(sub, context):
    p = sub.add_parser("retro", help=tr(context, "cli.retro.retro"))
    p.add_argument("--run-id", default=None, help=tr(context, "cli.retro.run_id"))
    p.add_argument("--feature", default=None,
                   help=tr(context, "cli.retro.feature"))
    p.add_argument("--vault", nargs="?", const="", default=None,
                   help=tr(context, "cli.retro.vault"))
    p.add_argument("--no-vault", action="store_true",
                   help=tr(context, "cli.retro.no_vault"))
    p.add_argument("--check", default=None, metavar="NOTE",
                   help=tr(context, "cli.retro.check"))
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


def _load_runtime_module(name):
    """hook runtime 모듈 동적 import — `_load_loop_audit` 과 같은 경로 규칙.

    문서 언어 판정은 hook 런타임이 정본이다. 같은 마커를 CLI 가 따로 파싱하면 두 파서가 갈리는
    순간 게이트와 회고 노트가 서로 다른 언어를 정답이라고 말한다.
    """
    from sage import _resources
    hooks = os.path.join(_resources.sage_root(), "scripts", "sage_harness", "hooks")
    for path in (os.path.join(hooks, "runtime"), hooks):
        if path not in sys.path:
            sys.path.insert(0, path)
    return importlib.import_module(name)


def _candidate_stems(la, root, feature, rid, docs=None):
    """문서 언어를 물어볼 사이클 stem 후보 — `--feature`, loop_open 의 cycle_stem, 고른 05 문서명.

    셋째가 있어야 하는 이유는 이 명령의 다른 축이 이미 그것을 사이클 식별자로 쓰고 있기 때문이다.
    `_derive_stem` 은 05 문서가 하나면 그 파일명을 노트 제목 stem 으로 승격한다. 언어 판정만 그것을
    못 보면, loop run 도 `--feature` 도 없이 05 문서 하나로만 식별되는 사이클에서 같은 실행이
    제목은 그 사이클이라고 하면서 언어는 "선언한 적 없다"고 말한다.

    `--feature` 는 부분 토큰이어도 되는 지원 계약이다(`--feature loop` 가 `loop-engineering` 을
    고른다). 그런데 Phase 00 결속은 exact stem 비교라, 부분 토큰 문자열 자체는 어떤 Phase 00 과도
    매치하지 않는다. 필터가 실제로 고른 문서의 stem 을 함께 들고 가는 것이 부분 필터를 깨지 않고
    정확한 stem 을 얻는 유일한 길이다.

    후보를 하나로 좁히지 않는다. 좁히려면 어느 쪽이 맞는지 골라야 하고, 그 선택이 틀리면 남의
    사이클 선언을 이 사이클의 정답으로 쓴다. 후보들이 같은 답을 내면 고를 필요가 없고, 다른 답을
    내면 그건 고를 문제가 아니라 막을 문제다 — `consistency_issues` 가 막는다.

    05 문서가 여럿이면 문서에서 stem 을 얻지 않는다. 어느 것이 이 사이클인지 모르는 상태이고,
    아무거나 고르면 다른 사이클의 선언 언어로 회고가 쓰인다.
    """
    from sage.commands.review_loop import _open_record
    recorded = (_open_record(la, root, rid) or {}).get("cycle_stem") if rid else None
    selected = None
    if docs and len(docs) == 1:
        selected = _load_runtime_module("cycle_binding").path_stem(docs[0])
    stems = []
    for value in (feature, recorded, selected):
        if isinstance(value, str) and value.strip() and value not in stems:
            stems.append(value)
    return stems


def _phase00_documents(root, profile, stems):
    """(이 stem 의 Phase 00 문서 | None, 판독 실패 사유 | None).

    **부재와 판독 실패를 가른다.** phase 00 계약이 아예 없는 프로젝트는 부재라 통과시키고,
    계약이 있는데 읽지 못한 상태(루트를 벗어나는 경로·권한·인코딩 손상)는 통과시키지 않는다.
    둘을 같은 값으로 뭉개면 "선언이 없다"와 "선언을 확인하지 못했다"가 구분되지 않고, 그러면
    파일 하나를 깨뜨리는 것이 언어 판정을 건너뛰는 레버가 된다.
    """
    pdca = profile.get("pdca") if isinstance(profile.get("pdca"), dict) else {}
    entry = next((item for item in (pdca.get("phases") or [])
                  if isinstance(item, dict) and str(item.get("id") or "") == "00"), None)
    pattern = (entry or {}).get("glob")
    if not pattern:
        return {}, None
    try:
        from sage.commands.review_loop import _phase_docs
        docs = _phase_docs(root, profile, "00")
    except (ValueError, TypeError, OSError, UnicodeDecodeError) as exc:
        return None, f"{pattern!r}: unreadable ({type(exc).__name__})"
    binding = _load_runtime_module("cycle_binding")
    return {doc["path"]: doc.get("content") or "" for doc in docs
            if binding.path_stem(doc.get("path") or "") in stems}, None


def _mirror_language(root, stems):
    """(미러 언어 | None, 진단 | None) — `.sage/cycle.json` 이 이 사이클에 대해 적어 둔 값.

    부재·legacy(v1)·남의 stem 은 (None, None) 이다. 어느 쪽도 선언이 아니고, 없다고 해서 판정이
    틀리지는 않는다. 손상은 갈라서 돌려준다 — 이 파일은 Phase 00 정본을 교차검증하는 유일한
    상대라, 읽지 못한 상태를 부재로 뭉개면 교차검증이 조용히 사라진다.

    손상일 때는 stem 을 알 수 없으므로 남의 사이클 파일일 가능성이 있어도 그대로 올린다.
    누구 것인지 모르는 것이 곧 이 사이클 것이 아니라는 증거는 아니다.
    """
    record = _load_runtime_module("cycle_state").read_declaration_record(root)
    if record.error:
        return None, record.error
    if record.stem not in stems:
        return None, None
    return record.document_language, None


def _cycle_document_language(root, profile, la, feature, rid, language=None, docs=None):
    """(문서 언어 | None, 차단 사유 | None) — 이 사이클이 어느 언어로 쓰이기로 선언됐는가.

    표시 언어(`--lang`)와 별개 축이다. 표시 언어는 실행 하나의 성질이고 문서 언어는 사이클 전체의
    성질이라, 화면을 지나 노트 *안으로* 들어가는 문자열은 후자를 따라야 한다. 둘을 섞으면 표시가
    ko 인 사용자가 `Document-Language: en` 사이클을 회고할 때 영어 사이클의 증거에 한국어 산문이
    남는다 — 역사 증거는 나중에 재번역하지 않으므로 그대로 굳는다.

    Phase 00 의 마커가 정본이고 `.sage/cycle.json` 은 재개용 미러다. **미러는 교차검증 상대일 뿐
    답의 출처가 아니다** — 정본이 말하지 않은 것을 미러가 대신 말하게 하면, 마커 없는 사이클이
    미러 한 줄로 특정 언어를 선언한 사이클이 된다. 둘이 다르면 어느 쪽도 고르지 않고 막는다.
    고르는 순간 사용자가 선언하지 않은 언어로 회고가 쓰인다.

    **미선언은 막지 않는다.** 마커 이전에 시작한 사이클의 회고가 전부 막히는 과차단이 되고, 그건
    이 판정이 만든 결함이다. 대신 언어를 지어내지 않고 None 을 돌려준다 — 호출부가 "선언 없음"을
    그대로 말한다.

    **판독 실패는 부재가 아니다.** 선언이 없는 것과 선언을 확인하지 못한 것은 다른 상태고, 뒤쪽을
    통과시키면 확인하지 못한 채로 언어가 정해진다. 원인을 실어 막는다.
    """
    stems = _candidate_stems(la, root, feature, rid, docs)
    if not stems:
        return None, None
    documents, unreadable = _phase00_documents(root, profile, stems)
    if unreadable:
        return None, tr(language, "cli.retro.blocker_document_language_unreadable",
                        detail=unreadable)
    if not documents:
        return None, None

    mirror, mirror_error = _mirror_language(root, stems)
    if mirror_error:
        return None, tr(language, "cli.retro.blocker_document_language_unreadable",
                        detail=render_issue(language, mirror_error))
    dl = _load_runtime_module("document_language")
    # MISSING 은 부재라 위 원칙대로 통과시키고, 중복·미지원 값·불일치만 막는다.
    conflicts = [(path, reason) for path, reason in dl.consistency_issues(documents, mirror)
                 if reason != dl.MISSING]
    if conflicts:
        detail = "; ".join(f"{path}: {reason}" for path, reason in conflicts[:3])
        return None, tr(language, "cli.retro.blocker_document_language", detail=detail)
    declared = {value for value, problem in (dl.scan(text) for text in documents.values())
                if not problem}
    return (declared.pop() if declared else None), None


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


# 표시 언어만 무효로 만드는 진단. 이 값이 틀려도 phase 글롭·vault 경로·pdca 계약은 그대로
# 읽히고, `effective_profile` 은 `interface` 를 복사조차 하지 않는다. 그래서 이것 하나만으로는
# retro 를 멈추지 않는다 — 표시 언어는 한국어로 폴백하고 경고만 낸다. catalog 의 경고문과
# 상세 설계가 "판정과 exit code 는 영향받지 않는다" 로 이미 계약돼 있고, 개인 설정 오타가
# 회고를 통째로 막는 것은 그 계약을 깨는 과차단이다.
_DISPLAY_ONLY_PROFILE_FAILURES = frozenset({"layers.interface_language_invalid"})


def _load_profile(root):
    """(유효 설정 | None, 판독에 실패한 계층 | None).

    **부재와 판독 실패를 가른다.** profile 이 설치되지 않은 저장소에서 단발로 도는 retro 는
    기존 계약대로 통과시키고, 파일이 있는데 읽지 못한 상태는 통과시키지 않는다. 둘을 같은 `{}`
    로 뭉개면 손상된 profile 이 phase 00 글롭째 지워, 언어를 선언한 사이클이 미선언으로 보이고
    그 오판이 노트에 그대로 굳는다 — 설정 파일 한 줄을 깨뜨리는 것이 언어 판정을 건너뛰는
    레버가 된다.

    부재는 shared 와 local 이 **둘 다** 없을 때만이다. local 만 남고 shared 가 사라진 것은
    무설치가 아니라 계층이 깨진 상태이고, 그것을 부재로 받으면 파일 하나를 지우는 것이 다시
    같은 레버가 된다. 끊어진 symlink 도 없는 것이 아니라 고장난 것이므로 `lexists` 로 본다.
    """
    ppath = os.path.join(root, "sage", "project-profile.yaml")
    lpath = os.path.join(root, "sage", LOCAL_PROFILE_NAME)
    if not os.path.lexists(ppath) and not os.path.lexists(lpath):
        return {}, None
    layers = load_profile_layers(ppath)
    failures = [message for severity, message in layers.issues if severity == "FAIL"]
    if failures and any(getattr(message, "code", None) not in _DISPLAY_ONLY_PROFILE_FAILURES
                        for message in failures):
        return None, layers
    return layers.effective, None


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
- `sage/asset_overrides/agents/*.md` · `sage/asset_overrides/skills/*.md` = 프로젝트 로컬 overlay. SAGE 가 `COMPOSE_ALLOWED` 자산의 overlay 만 CORE 렌더에 관리 블록으로 물리화(install/sync)하고 `sage validate` 가 게이트한다. `sage install --force` 가 ship 하지 않아 loop 학습이 보존된다. eligible 자산 개선은 CORE 렌더 직접수정이 아니라 `/sage-asset-override` overlay 로 제안한다. 게이트-보유/blocked 자산은 overlay 를 제안하지 말고 profile/convention/project-local doc 또는 별도 CORE/spec 변경으로 라우팅한다.
[VERIFY] 제안한 target 이 실제로 그 결함을 다음부터 잡을 수 있는지, 해당 메커니즘의 소스(전략 스크립트/profile 스키마)를 확인한 뒤 확정하라.
[OUTPUT] 제안 목록(자동반영 아님):
[{ "pattern":"...", "evidence":["finding 근거/파일:라인"], "target":"hook|profile|agent|skill",
   "asset_id":"해당 agent/skill id(있을 때)", "proposed_change":"구체 patch 문구(profile 키/overlay 문장/hook spec 변경 등)", "confidence":"high|med|low" }]
"""


def _fmt_audit(la, root, run_id, language=None):
    """감사 요약 + 대상 run_id 반환. run_id 없으면 최신. 기록 없으면 (None, [])."""
    runs = la.runs(root)
    if not runs:
        return None, [tr(language, "cli.retro.audit_no_history")]
    rid = run_id or runs[-1]
    rounds = la.rounds_of(root, rid)
    close = la.close_of(root, rid)
    lines = [f"run_id={rid}" + ("" if rid in runs else tr(language, "cli.retro.audit_unknown_run_suffix"))]
    tot = {"found": 0, "survived": 0, "accepted": 0, "arch": 0}
    for r in rounds:
        for k in tot:
            tot[k] += int(r.get(k, 0) or 0)
        lines.append(f"  [{r.get('iteration')}] found={r.get('found')} survived={r.get('survived')} "
                     f"accepted={r.get('accepted')} arch={r.get('arch')} tokens={r.get('tokens')}")
    lines.append(tr(language, "cli.retro.audit_totals", found=tot["found"], survived=tot["survived"],
                    accepted=tot["accepted"], arch=tot["arch"]))
    if close:
        lines.append(tr(language, "cli.retro.audit_closed", result=close.get("result"),
                        reason=close.get("reason"), iterations=close.get("iterations")))
    else:
        lines.append(tr(language, "cli.retro.audit_not_closed"))
    return rid, lines


_APPLY_PATH = (
    "【 적용 경로 (absorb 철학 — 자동 반영 절대 없음) 】\n"
    "  제안 → 사람 승인 → 자산 수정:\n"
    "    · 기계적(hook/profile): spec/profile 수정 → sage generate → sage validate\n"
    "    · 의미적(agent/skill): COMPOSE_ALLOWED 자산만 /sage-asset-override 로 overlay 작성(install-safe)\n"
    "      blocked/gate-bearing 자산은 profile/convention/project-local doc 또는 별도 CORE/spec 변경으로 라우팅\n"
    "  feed-forward: 다음 feature 의 00 Prior-Knowledge Scan 이 반영분을 읽음."
)

_PROPOSAL_TARGETS = ("profile", "hook", "agent", "skill")   # absorb 가 분기하는 target 어휘

# 요약 헤딩 이름을 catalog(cli.retro.heading_summary) 에서 직접 가져와 정규식을 구성한다 —
# 헤딩 문구가 바뀌면 이 정규식도 자동으로 따라간다(§4c/§4d SSOT, 하드코딩 이중관리 금지).
_SUMMARY_HEADING_ALTERNATION = "|".join(
    re.escape(CATALOGS[lang]["cli.retro.heading_summary"]) for lang in CATALOGS)
_SUMMARY_HEADING_RE = re.compile(rf"(?m)^##[ \t]*(?:{_SUMMARY_HEADING_ALTERNATION})[ \t]*$")


def _derive_stem(feature, docs, rid, language=None):
    """human-gate 노트 파일명 stem → (stem, hint). 우선순위: --feature > 유일한 05 문서명 > run_id.

    run_id 폴백은 제목만으로 어떤 사이클인지 알아볼 수 없어(난수형) 마지막 수단이다. 05 문서가
    하나뿐이면 그 파일명이 곧 사이클 식별자이므로 결정론적으로 승격한다."""
    if feature:
        return feature, None
    if len(docs) == 1:
        return os.path.splitext(os.path.basename(docs[0]))[0], None
    reason = (tr(language, "cli.retro.stem_reason_multi", count=len(docs)) if docs
              else tr(language, "cli.retro.stem_reason_none"))
    return (rid or "cycle"), tr(language, "cli.retro.stem_hint", reason=reason)


def _summary_body(text):
    """`## 요약`/`## Summary` 섹션 본문(다음 `## ` 헤딩 전까지). 헤딩 없음 → None."""
    m = _SUMMARY_HEADING_RE.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"(?m)^##[ \t]", rest)
    return rest[:nxt.start()] if nxt else rest


def _check_note(path, root, run_id=None, language=None):
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
        print(tr(language, "cli.retro.msg01", path=path), file=sys.stderr)
        return 2
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(tr(language, "cli.retro.msg02", arg=type(e).__name__, e=e), file=sys.stderr)
        return 2
    problems = []
    summary_heading = tr(language, "cli.retro.heading_summary")
    proposals_heading = tr(language, "cli.retro.heading_proposals")

    # run 결속: 파일명에 run_id 가 없으므로 같은 stem/날짜의 *이전* run 노트가 재사용될 수 있다.
    # 그 노트는 이미 채워져 있어 검사를 통과 → 이번 run 은 회고 없이 완료 처리된다(게이트 우회).
    # 노트가 run 을 선언했는데 --run-id 를 안 주면 결속 검사가 통째로 꺼지므로, 생략 자체를 실패로 본다.
    noted = frontmatter_value(text, "run_id")
    if run_id:
        if noted != run_id:
            problems.append(tr(language, "cli.retro.problem_run_id_mismatch", noted=noted, run_id=run_id))
    elif noted:
        problems.append(tr(language, "cli.retro.problem_run_id_missing", noted=noted))

    body = _summary_body(text)
    if body is None:
        problems.append(tr(language, "cli.retro.problem_summary_heading_missing", summary_heading=summary_heading))
    else:
        # placeholder 는 ko/en 어느 catalog 값이든(--lang 과 무관하게) 검출한다 — 노트 구조 판정은
        # 표시 언어가 아니라 노트가 실제로 어떤 언어로 쓰였는지에 매인다.
        placeholders = [CATALOGS[lang]["cli.retro.summary_placeholder"] for lang in CATALOGS]
        prose = "\n".join(l for l in body.splitlines()
                          if l.strip() and not any(p in l for p in placeholders)).strip()
        if not prose:
            problems.append(tr(language, "cli.retro.problem_summary_empty", summary_heading=summary_heading))

    proposals, err = _extract_proposals(text, language)
    if err:
        problems.append(tr(language, "cli.retro.problem_proposals_unparseable",
                           proposals_heading=proposals_heading, err=err))
    else:
        for i, p in enumerate(proposals):
            if not isinstance(p, dict):
                problems.append(tr(language, "cli.retro.problem_proposal_not_object", i=i, p=p))
                continue
            if p.get("target") not in _PROPOSAL_TARGETS:
                problems.append(tr(language, "cli.retro.problem_proposal_bad_target", i=i,
                                   target=p.get("target"), targets=list(_PROPOSAL_TARGETS)))
            if not str(p.get("proposed_change") or "").strip():
                problems.append(tr(language, "cli.retro.problem_proposal_empty_change", i=i))

    if problems:
        print(tr(language, "cli.retro.msg03", os_path=os.path.basename(path)), file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        print(tr(language, "cli.retro.msg04", summary_heading=summary_heading,
                 proposals_heading=proposals_heading), file=sys.stderr)
        return 1

    n = len(proposals)
    print(f"== sage retro --check ({os.path.basename(path)}) — OK ==")
    print(tr(language, "cli.retro.msg05", n=n) + (tr(language, 'cli.retro.all_valid_target') if n else ""))
    if n == 0:
        print(tr(language, "cli.retro.msg06"))

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
            print(tr(language, "cli.retro.msg07", arg=type(e).__name__, e=e), file=sys.stderr)
            return 2

    print(tr(language, "cli.retro.msg08"))
    return 0


def run(args):
    root = os.path.abspath(args.root) if args.root else _find_project_root(os.getcwd())
    if args.check:
        return _check_note(args.check, root, args.run_id, language_of(args))

    language = language_of(args)
    profile, broken_layers = _load_profile(root)
    if broken_layers is not None:
        # 쓰기 전에 멈춘다. 읽지 못한 설정으로 고른 언어와 경로는 노트 안에 그대로 굳고,
        # 증거는 나중에 고쳐 쓰지 않는다.
        detail = "; ".join(render_issue(language, message)
                          for severity, message in broken_layers.issues if severity == "FAIL")
        print(tr(language, "cli.retro.blocker_profile_unreadable", detail=detail,
                 shared=broken_layers.shared_path, local=broken_layers.local_path), file=sys.stderr)
        return 2
    la = _load_loop_audit(root)

    rid, audit_lines = _fmt_audit(la, root, args.run_id, language)

    # 05 리뷰 문서 수집(finding 텍스트 원천) — approve phase 글롭. --feature 로 경로 필터.
    pattern = os.path.join(root, _approve_glob(profile))
    docs = sorted(glob.glob(pattern, recursive=True))
    if args.feature:
        # 파일명(basename)에서 -/_/. 로 구분된 토큰 경계 매치(codex S4 P3). raw 부분문자열은
        # 'loop' 이 'preloop' 이나 부모 디렉토리 세그먼트까지 오매치 → 무관 05 문서가 증거에 섞임.
        feat_re = re.compile(r"(^|[-_.])" + re.escape(args.feature) + r"([-_.]|$)")
        docs = [d for d in docs if feat_re.search(os.path.basename(d))]

    integ = la.integrity_issues(root)

    doc_language, blocker = _cycle_document_language(root, profile, la, args.feature, rid, language,
                                                     docs)
    if blocker:
        # 쓰기 전에 멈춘다. 노트를 남기고 나서 알려주면 이미 한 언어를 골라 쓴 뒤다.
        print(blocker, file=sys.stderr)
        return 2
    # 노트 안으로 들어가는 문자열은 선언 언어를 따른다. 미선언이면 표시 언어로 쓰되 언어를
    # 단언하지는 않는다 — 그 차이는 아래 [LANGUAGE] 한 줄이 말한다.
    note_language = doc_language or language

    # 본문 1회 구성 → stdout + (vault 활성 시) human-gate 노트 공용.
    out = [tr(language, "cli.retro.header"), "",
           tr(language, "cli.retro.section_audit"), *audit_lines, "",
           tr(language, "cli.retro.section_docs")]
    if docs:
        out += [f"  · {os.path.relpath(d, root)}" for d in docs]
    else:
        out.append(tr(language, "cli.retro.no_docs_matched", pattern=os.path.relpath(pattern, root)))
    # _DISTILLER_PROMPT/_APPLY_PATH 는 (c) LLM 프롬프트 — host AI 대상 고정 지시문이라 표시 언어와
    # 무관하게 항상 원문(한국어)을 유지한다([LANGUAGE] 계약). 언어 신호는 부록 한 줄만 담당하고,
    # 그 한 줄은 표시 언어가 아니라 **선언 언어**를 말한다 — distiller 가 노트에 채울 산문의
    # 언어를 정하는 지시문이라, 표시 언어로 렌더하면 문장이 사실과 반대가 된다.
    out += ["", tr(language, "cli.retro.section_distiller"), _DISTILLER_PROMPT,
            (tr(doc_language, "cli.retro.distiller_language_directive") if doc_language
             else tr(language, "cli.retro.distiller_language_undeclared")),
            _APPLY_PATH]
    if integ:
        # 문구 자체의 이관은 retro 배치에서 하고, 여기서는 하부 감사 진단만 렌더한다 —
        # 진단을 문자열로 두면 이 줄이 어느 언어로 나갈지 호출부가 고를 수 없다.
        out += ["", tr(language, "cli.retro.integrity_warning_header")]
        out += [f"   - {render_issue(language, i)}" for i in integ]

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
                print(tr(language_of(args), "cli.retro.msg09", args_run_id=args.run_id), file=sys.stderr)
                return 2
            target = args.run_id
        elif len(real_runs) == 1:
            target = real_runs[0]   # 단일 run 자동 결속
        elif len(real_runs) >= 2:
            print(tr(language_of(args), "cli.retro.msg10", count=len(real_runs)), file=sys.stderr)
            return 2
        else:
            # 결속할 run 자체가 없음(단발 리뷰 등) — 게이트는 06 Loop-Run 결속으로만 판정하므로 skip 불필요.
            print(tr(language_of(args), "cli.retro.msg11"), file=sys.stderr)
        if target:
            try:
                _load_retro_audit().record_skip(root, target, reason="no_vault")
            except Exception as e:
                print(tr(language_of(args), "cli.retro.msg12", arg=type(e).__name__, e=e), file=sys.stderr)
                return 2
    else:
        vault_arg = args.vault
        if vault_arg is None and kc.get("retro_note") is True:
            vault_arg = ""   # profile vault_path 사용(자동 활성)
    if vault_arg is not None:
        raw_stem, stem_hint = _derive_stem(args.feature, docs, rid, language)
        if stem_hint:
            print(f"  ℹ️  {stem_hint}", file=sys.stderr)
        _write_vault_note(profile, root, rid, raw_stem, out, vault_arg or None, language,
                          note_language)
    return 0


def _write_vault_note(profile, root, rid, raw_stem, out_lines, override, language=None,
                      note_language=None):
    """retro 패킷을 vault 에 human-gate 노트(approved:false)로 작성. 사람이 Obsidian 에서 검토·승인.

    두 언어를 받는다. `language` 는 이 실행의 화면(stderr 안내·경고)이고 `note_language` 는 노트
    파일 안에 남는 문자열(헤딩·안내문·placeholder)이다. 헤딩 이름이 화면 안내에 인용될 때는
    화면 문장 안에 노트의 실제 헤딩이 들어간다 — 그래야 사용자가 그 이름으로 찾을 수 있다.
    """
    note_language = note_language or language
    from sage.commands import _vault
    vault, folder = _vault.vault_target(profile, override, root)
    if not vault:
        print(tr(language, "cli.retro.msg13"), file=sys.stderr)
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
                prev_rid = frontmatter_value(Path(prior).read_text(encoding="utf-8"), "run_id")
            except (OSError, UnicodeDecodeError):
                prev_rid = None
            if prev_rid and prev_rid != rid:
                fname = _note_filename(profile, "TECH", f"{name} retro {stem} {today} {rid}")
                print(tr(language, "cli.retro.msg14", prev_rid=prev_rid),
                      file=sys.stderr)
    dash_name = _dashboard_filename(profile)
    fm = {"tags": ["sage", "retro", "loop-c"], "approved": False, "run_id": rid or "",
          "date": today, "status": "pending-review"}
    summary_heading = tr(note_language, "cli.retro.heading_summary")
    proposals_heading = tr(note_language, "cli.retro.heading_proposals")
    note_arg = tr(note_language, "cli.retro.note_arg_placeholder")
    check_cmd = f"sage retro --check {note_arg}" + (f" --run-id {rid}" if rid else "")
    intro = tr(note_language, "cli.retro.note_intro", summary_heading=summary_heading,
              proposals_heading=proposals_heading, check_cmd=check_cmd, note_arg=note_arg)
    related = tr(note_language, "cli.retro.note_related_audit", wiki_stem=_wiki_stem(dash_name))
    proposals_line = tr(note_language, "cli.retro.note_proposals_heading_line", proposals_heading=proposals_heading)
    evidence_summary = tr(note_language, "cli.retro.note_evidence_summary", proposals_heading=proposals_heading)
    placeholder = tr(note_language, "cli.retro.summary_placeholder")
    body = (f"{intro}\n\n"
            f"{related}\n\n"
            f"## {summary_heading}\n"
            f"{placeholder}\n\n"
            f"{proposals_line}\n"
            "```json\n[]\n```\n\n"
            "---\n"
            f"<details>\n<summary>{evidence_summary}</summary>\n\n"
            "```\n" + "\n".join(out_lines) + "\n```\n\n</details>\n")
    # create-only: 같은 날 재실행이 사람이 검토/승인(approved:true)한 노트를 덮어쓰지 않게(codex S5 P2).
    path = _vault.write_note(vault, folder, fname, fm, body, create_only=True)
    if path is None:
        path = os.path.join(vault, folder, fname)
        print(tr(language, "cli.retro.msg15", path=path), file=sys.stderr)
    else:
        print(tr(language, "cli.retro.msg16", path=path), file=sys.stderr)
    # 노트는 빈 템플릿으로 나간다 — 채우는 건 host 몫이므로, 검산 명령을 여기서 못박아 전달한다.
    # --run-id 를 포함해 출력한다: 빠뜨리면 run 결속 검사가 꺼져 남의 노트로 통과할 수 있다.
    rid_arg = f' --run-id {rid}' if rid else ""
    print(tr(language, "cli.retro.msg17", path=path, rid_arg=rid_arg,
             summary_heading=summary_heading, proposals_heading=proposals_heading), file=sys.stderr)
    try:
        _write_vault_dashboard(_load_loop_audit(root), root, override)
    except Exception as e:
        print(tr(language, "cli.retro.msg18", arg=type(e).__name__, e=e), file=sys.stderr)
