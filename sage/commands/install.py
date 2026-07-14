"""sage install — host 택1 + CORE 하네스 부트스트랩 (결정론 복사).

마스터 §13 + CORE 카탈로그 §1·§4: install 은 동작하는 CORE 하네스를 배치한다.
- framework 템플릿(중립): AGENT_GUIDE.md, {wrapper}, verification-protocol.md,
  scripts/verify-changes.sh, docs/agent/*
- CORE hook: spec(docs/sage_harness/hooks/*.md) + 정본(scripts/sage_harness/hooks: core+adapter+strategy+native)
- CORE roster agent spec(중립): leader/implementer-a/implementer-b/qa/reviewer/convention-checker
- profile(빈 스키마, host/prefix 치환) + spec 템플릿 + schema + manifest(CORE hook 등록)
배치 후: profile 값 채움 → `sage generate --kind hook --write`(등록 산출물 + manifest 스탬프).
독립(제약 #2): 복사 리소스는 전부 도메인값 0(중립). 프로젝트 값은 profile 로만.
멱등: 기존 파일 skip(--force 로 덮어쓰기). AI 생성 아님(고정 템플릿 복사).
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

from sage import __version__

from sage import _resources   # 번들 리소스 경로 단일 해석(env override + repo fallback — 재배치/설치 대비)

# CORE roster (중립 6인) + CORE hook 7종(form) + CORE skill 7종. 도메인값 아님 = framework 메타.
# skill 3분할: sage-cycle(00~06 우산) → sage-plan(00~02 기획) → sage-team(03~06 개발).
# sage-asset-override: CORE 자산 오버레이(sage/asset_overrides/**) 저작 — CORE 렌더 직접수정 대체 경로.
_CORE_AGENTS = ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]
_CORE_SKILLS = ["sage-cycle", "sage-plan", "sage-team", "sage-review", "sage-asset", "sage-profile-modify", "sage-asset-override"]
_CORE_BOOTSTRAP_SKILL = "sage-init"
# 은퇴한 CORE skill 이름 — install 시 잔존 사본을 정리(rename 수렴). 이름이 바뀌면 옛 이름을 여기 추가.
# sage-pdca-start → sage-plan 으로 3분할 rename(옛 이름 잔존 사본 정리). pdca-start 는 그 이전 rename.
_LEGACY_CORE_SKILLS = ["pdca-start", "sage-pdca-start"]
# SAGE 가 hand-ship 하는 모든 CORE skill SKILL.md 에 들어있는 마커. 정리 전 SAGE 자산 확인용
# (codex 전역처럼 공유 공간에서 동명의 사용자 skill 을 오삭제하지 않도록).
_LEGACY_SKILL_SIGNATURE = "CORE framework bootstrap asset"
_CORE_HOOKS = [
    ("capture-declared-risk", "core_adapter"),
    ("post-tool-logger", "core_adapter"),
    ("pre-implementation-gate", "core_adapter"),
    ("pre-phase4-checklist-gate", "core_adapter"),
    ("session-start-snapshot", "core_adapter"),
    ("stop-compliance-report", "core_adapter"),
    ("generated-artifact-write-guard", "native"),
]
_SKIP_DIRS = {"tests", "__pycache__"}


def register(sub):
    p = sub.add_parser(
        "install",
        help="현재 프로젝트에 SAGE 기본 파일을 설치합니다",
        add_help=False,
        usage="sage install --host {claude,codex} [--prefix PREFIX] [--dest DEST] [--force] [--no-global-skill] [--help]",
    )
    p.add_argument("--help", action="help", help="도움말을 보여주고 종료합니다")
    p.add_argument("--host", choices=["claude", "codex"], required=True,
                   help="SAGE를 설치할 AI 도구를 선택합니다: claude 또는 codex (필수)")
    p.add_argument("--prefix", default="sage", help="자산 네이밍 prefix (선택, 기본값: sage)")
    p.add_argument("--dest", default=".", help="설치 대상 프로젝트 루트 (선택, 기본값: 현재 디렉토리)")
    p.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기 (기본: skip)")
    p.add_argument("--no-global-skill", action="store_true",
                   help="codex host: CORE 스킬($sage-init/$sage-cycle/$sage-plan/$sage-team/$sage-review/$sage-asset/$sage-profile-modify/$sage-asset-override)의 전역(~/.codex/skills) 설치를 건너뜁니다 (CI/샌드박스용)")
    p._optionals.title = "옵션"
    p.set_defaults(func=run)


def _write(path, content, force, created, skipped, executable=False):
    if os.path.exists(path) and not force:
        skipped.append(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if executable:
        os.chmod(path, 0o755)
    created.append(path)


def _copy_file(src, dst, force, created, skipped):
    if not os.path.exists(src):
        return
    executable = src.endswith(".sh")
    _write(dst, Path(src).read_text(encoding="utf-8"), force, created, skipped, executable)


def _prune_legacy_skill(skill_dir, pruned):
    """은퇴한 CORE skill 사본을 제거(rename 수렴). codex 전역 $CODEX_HOME/skills 는 공유 공간이라
    SKILL.md 에 SAGE hand-ship 시그니처가 있을 때만 삭제 — 같은 이름의 사용자 skill 오삭제 방지(codex R2-P2).
    비치명적: 권한/읽기전용/비-UTF-8 실패는 install 을 깨지 않는다(전역 home 쓰기와 동일 철학)."""
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(skill_md):
        return
    try:
        if _LEGACY_SKILL_SIGNATURE not in Path(skill_md).read_text(encoding="utf-8"):
            return   # SAGE 가 ship 한 자산 아님 → 사용자 skill 로 보고 보존
        shutil.rmtree(skill_dir)
        pruned.append(skill_dir)
    except (OSError, UnicodeError):
        pass


def _copy_tree(src_dir, dst_dir, force, created, skipped):
    """src_dir 하위 전체 복사(tests/__pycache__ 제외, .sh 는 실행권한)."""
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            s = os.path.join(root, fn)
            d = os.path.join(dst_dir, os.path.relpath(s, src_dir))
            _copy_file(s, d, force, created, skipped)


def _installed_profile(dest):
    """dest 의 인스턴스 profile → (profile, error). install 은 profile 을 --force 로도 덮지 않으므로,
    `sage-init` 로 채운 뒤 `sage install --force` 를 다시 돌리면 그 값으로 에이전트가 재렌더된다.

    파싱 실패를 `{}` 로 삼키면 **설정이 조용히 무시된 채 기본 렌더가 배포된다** → error 를 돌려
    호출자가 무변경 exit 1 하게 한다(codex 5R). 파일 부재는 첫 install 이라 정상.
    """
    path = os.path.join(dest, "sage", "project-profile.yaml")
    if not os.path.exists(path):
        return {}, None
    try:
        import yaml
    except ImportError:
        return {}, f"pyyaml 미설치 — {path} 를 읽을 수 없어 에이전트 렌더를 결정할 수 없습니다 (pip install pyyaml)"
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        return {}, f"profile 파싱 실패: {path} ({type(e).__name__}: {e})"
    if data is None:
        return {}, None   # 빈 파일 = 미설정
    if not isinstance(data, dict):
        return {}, f"profile 최상위가 매핑이 아님: {path} (받음: {type(data).__name__})"
    return data, None


def _copy_agent_renders(src_dir, dst_dir, profile, force, created, skipped):
    """CORE 에이전트 렌더 배치. claude host 만 profile 의 model/effort 를 frontmatter 로 주입한다
    (codex 는 .codex/agents/<id>.md 를 model/effort 로 해석하는 기전이 없어 주입해도 무동작)."""
    for fn in sorted(os.listdir(src_dir)) if os.path.isdir(src_dir) else []:
        if not fn.endswith(".md"):
            continue
        src = os.path.join(src_dir, fn)
        dst = os.path.join(dst_dir, fn)
        overrides = agent_frontmatter_overrides(profile, fn[:-3])
        _write(dst, render_core_agent(Path(src).read_text(encoding="utf-8"), overrides),
               force, created, skipped)


def _codex_skills_root():
    """codex 스킬 전역 루트 = $CODEX_HOME/skills (미설정 시 ~/.codex/skills). codex 바이너리 규약.

    codex 는 repo-스코프 스킬을 자동발견하지 않고 이 전역 디렉토리만 스캔하므로(codex 협의 실증),
    codex host 의 $sage-init 스킬은 여기로 설치한다(claude 의 repo .claude/skills 와 비대칭)."""
    base = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(base, "skills")


def _codex_global_skill_path(skill_id):
    return os.path.join(_codex_skills_root(), skill_id, "SKILL.md")


def _core_skill_source(skill_id):
    """hand-shipped CORE skill render source. The same source is used for Claude repo skills
    and Codex global skills, so install/doctor must compare against this exact artifact."""
    return os.path.join(_resources.core_dir(), "framework", ".claude", "skills", skill_id, "SKILL.md")


def core_skill_ids():
    """CORE skill ids that `sage install --host codex` installs into the Codex global skill dir."""
    return [_CORE_BOOTSTRAP_SKILL, *_CORE_SKILLS]


def _core_agent_source(agent_id):
    """hand-shipped CORE roster agent render source. Both hosts render from the same
    framework `.claude/agents/<id>.md` (install copies it to `.claude/agents` for claude
    and `.codex/agents` for codex — run() 5c), so install/doctor must compare against
    this exact artifact."""
    return os.path.join(_resources.core_dir(), "framework", ".claude", "agents", f"{agent_id}.md")


def core_agent_ids():
    """CORE roster agent ids that `sage install` hand-ships into the host agents dir."""
    return list(_CORE_AGENTS)


# claude 에이전트 frontmatter 가 실제로 받는 reasoning effort(claude 바이너리 스키마 실측:
# effort = enum(low|medium|high|xhigh|max) | int). model 은 free string(alias 또는 full id).
AGENT_EFFORTS = ("low", "medium", "high", "xhigh", "max")
AGENT_MODEL_ALIASES = ("opus", "sonnet", "haiku", "fable", "inherit")
# 전체 문자열 앵커 — prefix 검사만 하면 `claude-x\nname: replaced` 가 통과해 frontmatter 에 키를 주입한다.
_MODEL_ID_RE = re.compile(r"\Aclaude-[A-Za-z0-9._-]+\Z")

# effort 미설정 시 CORE 에이전트가 받는 값. host CLI 기본값에 맡기지 않는 이유: SAGE 의 PDCA 는
# 설계·리뷰 중심이라 추론 강도가 조용히 낮아지면 게이트 품질이 함께 떨어진다.
DEFAULT_AGENT_EFFORT = "high"

# model 은 기본값을 두지 않는다 — 미설정이면 host CLI 가 고른 모델을 그대로 쓴다(조용한 다운그레이드 방지).
_DEFAULT_AGENT_FRONTMATTER = {"effort": DEFAULT_AGENT_EFFORT}

# 실행 바인딩은 `team.core.<role>.runtime` 아래에만 둔다. 역할 바로 아래의 `model` 은 옛 프로필이
# 쓰던 죽은 필드(어떤 코드도 읽지 않았고 템플릿이 reviewer/qa 에 sonnet 을 박아두었다) — 여기서
# 승격하면 업그레이드만으로 Phase 05 리뷰어가 조용히 다운그레이드된다. 그래서 이름을 분리했다.
_RUNTIME_KEY = "runtime"
_LEGACY_ROLE_KEYS = ("model", "effort")
# 역할 객체가 가질 수 있는 키. 미지 키를 흘려보내면 `runtim: {...}` 오타가 조용히 기본 렌더로 흡수된다.
_ROLE_KEYS = frozenset({"enabled", "owns", "cross_model", _RUNTIME_KEY, *_LEGACY_ROLE_KEYS})


def _role_runtime(profile, agent_id):
    """profile.team.core.<role>.runtime (dict 아니면 {})."""
    if not isinstance(profile, dict):
        return {}
    team = profile.get("team")
    core = team.get("core") if isinstance(team, dict) else None
    spec = core.get(agent_id) if isinstance(core, dict) else None
    rt = spec.get(_RUNTIME_KEY) if isinstance(spec, dict) else None
    return rt if isinstance(rt, dict) else {}


def agent_frontmatter_issue(overrides):
    """주입 직전 최종 관문 — 잘못된 값이 에이전트 파일에 박히면 그 에이전트가 로드되지 않는다.
    `sage validate` 를 거치지 않고 `sage install --force` 만 돌린 경우를 위해 install 도 직접 검사한다."""
    model, effort = overrides.get("model"), overrides.get("effort")
    if model is not None and not (isinstance(model, str)
                                  and (model in AGENT_MODEL_ALIASES or _MODEL_ID_RE.match(model))):
        return (f"team.core.*.runtime.model={model!r} 는 알 수 없는 값 "
                f"(허용: {', '.join(AGENT_MODEL_ALIASES)} 또는 claude-* 전체 id)")
    if effort is not None and not (effort in AGENT_EFFORTS
                                   or (isinstance(effort, int) and not isinstance(effort, bool) and effort > 0)):
        return (f"team.core.*.runtime.effort={effort!r} 는 알 수 없는 값 "
                f"(허용: {', '.join(AGENT_EFFORTS)} 또는 양의 정수)")
    return None


def team_runtime_issues(profile):
    """team.core 전체를 검사해 [(severity, message)] 반환. `sage validate` 와 `sage install` 의 **단일 소스**.

    install 이 주입 직전의 `overrides` 만 봤을 때는 오타 키(`runtime.modle`)나 오타 역할(`reviewerr`)이
    기본값으로 축소돼 통과했다 — validate 를 건너뛰면 설정이 조용히 무시된 채 설치가 성공한다.
    그래서 구조(역할명·runtime 키)까지 여기서 함께 본다.

    - 역할명 오타 / runtime 키 오타 / 잘못된 값 → FAIL (install 이 거부)
    - 역할 바로 아래 model·effort → WARN. 옛 프로필의 죽은 필드이며, 승격하면 업그레이드만으로
      reviewer/qa 가 조용히 다운그레이드된다(템플릿이 sonnet 을 박아뒀었다).
    - codex host 에서의 설정 → WARN (해석 기전 없음)
    """
    if not isinstance(profile, dict):
        return []
    team = profile.get("team")
    if team in (None, ""):
        return []
    if not isinstance(team, dict):
        return [("FAIL", f"team 은 매핑이어야 함 (받음: {type(team).__name__})")]
    core = team.get("core")
    if core in (None, ""):
        return []
    if not isinstance(core, dict):
        return [("FAIL", f"team.core 는 매핑이어야 함 (받음: {type(core).__name__})")]
    rt_prof = profile.get("runtime")
    host = rt_prof.get("host", "claude") if isinstance(rt_prof, dict) else "claude"
    issues = []
    for role, spec in core.items():
        # 키가 비-str 일 수 있다(YAML `1: {...}`) → 어떤 입력에도 크래시 없이 FAIL 로 떨어져야 한다.
        if role not in _CORE_AGENTS:
            issues.append(("FAIL", f"team.core.{role!s} 는 알 수 없는 역할 — 오타면 조용히 무시된다 "
                                   f"(CORE 로스터: {', '.join(_CORE_AGENTS)})"))
            continue
        if not isinstance(spec, dict):
            # 조용히 넘기면 이 역할의 설정 전체가 무시된 채 기본 렌더가 배포된다.
            issues.append(("FAIL", f"team.core.{role} 은 매핑이어야 함 (받음: {type(spec).__name__})"))
            continue
        stray = [k for k in spec if k not in _ROLE_KEYS]
        if stray:
            # `runtim:` 오타는 아무도 안 읽어 기본 렌더가 나간다 — 설정한 model 이 조용히 사라진다.
            issues.append(("FAIL", f"team.core.{role} 의 알 수 없는 키: "
                                   f"{', '.join(sorted(str(k) for k in stray))} "
                                   f"(허용: {', '.join(sorted(_ROLE_KEYS))})"))
        legacy = [k for k in ("model", "effort") if spec.get(k) not in (None, "")]
        if legacy:
            issues.append(("WARN", f"team.core.{role}.{'/'.join(legacy)} 는 무동작 — 실행 바인딩은 "
                                   f"team.core.{role}.runtime.{{model,effort}} 로 옮기세요"))
        rt = spec.get(_RUNTIME_KEY)
        if rt in (None, ""):
            continue
        if not isinstance(rt, dict):
            issues.append(("FAIL", f"team.core.{role}.runtime 은 매핑이어야 함 (받음: {type(rt).__name__})"))
            continue
        unknown = [k for k in rt if k not in ("model", "effort")]
        if unknown:
            issues.append(("FAIL", f"team.core.{role}.runtime 의 알 수 없는 키: "
                                   f"{', '.join(sorted(str(k) for k in unknown))} (허용: model, effort)"))
        issue = agent_frontmatter_issue({k: rt[k] for k in ("model", "effort") if rt.get(k) not in (None, "")})
        if issue:
            issues.append(("FAIL", issue.replace("team.core.*", f"team.core.{role}")))
        if host == "codex" and any(rt.get(k) not in (None, "") for k in ("model", "effort")):
            issues.append(("WARN", f"team.core.{role}.runtime 의 model/effort 는 codex host 에서 무동작 "
                                   f"(.codex/agents/*.md 는 해석 기전 없음)"))
    return issues


def agent_frontmatter_overrides(profile, agent_id):
    """이 CORE 에이전트 렌더에 주입할 {model, effort}. team.core.<role>.runtime 이 기본값을 덮는다.

    effort 는 미설정이어도 DEFAULT_AGENT_EFFORT 가 들어간다. model 은 미설정이면 빠진다.
    codex host 는 .codex/agents/<id>.md 가 이 키들을 해석하는 기전이 없어 호출자가 주입하지 않는다.
    """
    if agent_id not in _CORE_AGENTS:
        return {}
    out = dict(_DEFAULT_AGENT_FRONTMATTER)
    rt = _role_runtime(profile, agent_id)
    for key in ("model", "effort"):
        val = rt.get(key)
        if val is not None and val != "":
            out[key] = val
    return out


def _is_fm_boundary(line):
    """frontmatter 구분선은 컬럼 0 의 `---` 뿐(뒤 공백 허용). 들여쓴 `---` 는 블록 스칼라 본문이다."""
    return line.rstrip() == "---" and not line[:1].isspace()


def _is_top_level_key(line, names):
    """컬럼 0 에서 시작하는 `<name>:` 만 최상위 키. 들여쓴 줄은 블록 스칼라 본문이라 건드리지 않는다.
    `model : x` / `"model": x` 같은 정상 YAML 표기도 같은 키로 본다 — 안 그러면 제거를 놓쳐 중복 키가 된다."""
    if not line or line[:1].isspace() or ":" not in line:
        return False
    key = line.split(":", 1)[0].strip().strip("'\"")
    return key in names


def render_core_agent(src_text, overrides):
    """CORE 에이전트 렌더에 model/effort frontmatter 를 주입. overrides 가 비면 원문 그대로.

    install 이 쓰는 내용과 doctor 가 drift 를 대조하는 기준이 같은 함수여야 한다 — 아니면
    설정된 에이전트가 모두 영구 stale 로 뜬다.
    """
    if not overrides:
        return src_text
    lines = src_text.split("\n")
    if not lines or not _is_fm_boundary(lines[0]):
        return src_text   # frontmatter 없는 렌더는 건드리지 않는다
    try:
        close = next(i for i in range(1, len(lines)) if _is_fm_boundary(lines[i]))
    except StopIteration:
        return src_text
    injected = [f"{k}: {overrides[k]}" for k in ("model", "effort") if k in overrides]
    kept = [ln for ln in lines[1:close] if not _is_top_level_key(ln, ("model", "effort"))]
    return "\n".join(["---", *kept, *injected, *lines[close:]])


def core_render_status(src, dst, overrides=None):
    """Compare a hand-shipped CORE render (src) with its installed copy (dst).

    status ∈ {ok, missing, stale, source_missing, error}. Shared by skill/agent and
    claude/codex so drift detection cannot diverge per host. (`codex_core_skill_status`
    stays as the codex-global-skill convenience wrapper over the same comparison.)

    `overrides` 가 있으면 src 원문이 아니라 `render_core_agent(src, overrides)` 결과와 대조한다 —
    profile 이 정한 model/effort 주입이 drift 로 오판되지 않도록.
    """
    if not os.path.exists(src):
        return ("source_missing", None)
    if not os.path.exists(dst):
        return ("missing", dst)
    try:
        expected = render_core_agent(Path(src).read_text(encoding="utf-8"), overrides)
        return ("ok" if Path(dst).read_text(encoding="utf-8") == expected else "stale", dst)
    except (OSError, UnicodeError) as e:
        return ("error", f"{dst} ({e})")


def codex_core_skill_status(skill_id):
    """Read-only status for a hand-shipped Codex CORE skill.

    status ∈ {ok, missing, stale, source_missing, error}. This intentionally mirrors the
    comparison used by `_install_codex_global_skill` so `sage doctor` cannot drift from
    install's stale detection semantics.
    """
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_-]+$", skill_id):
        return ("error", f"unsafe skill_id: {skill_id!r}")
    src = _core_skill_source(skill_id)
    if not os.path.exists(src):
        return ("source_missing", None)
    dst = _codex_global_skill_path(skill_id)
    if not os.path.exists(dst):
        return ("missing", dst)
    try:
        src_text = Path(src).read_text(encoding="utf-8")
        cur = Path(dst).read_text(encoding="utf-8")
        return ("ok" if cur == src_text else "stale", dst)
    except (OSError, UnicodeError) as e:
        return ("error", f"{dst} ({e})")


def _install_codex_global_skill(src_skill_md, force, skill_id="sage-init"):
    """codex 스킬을 $CODEX_HOME/skills/{skill_id}/SKILL.md 에 전역 설치.

    반환: (status, dst) — status ∈ {installed, skipped, stale, missing, error}. create-only(force 면 덮어쓰기).
    repo-스코프(--dest) 밖 전역 쓰기이므로 created/skipped 리스트가 아닌 별도 상태로 보고한다.
    - 비치명적(codex R1-P0): 전역 home 쓰기 실패(read-only/정책잠금)는 install 을 깨지 않고 error 반환
      → 호출부가 경고+수동 폴백(AGENTS.md) 안내. repo-로컬 산출물은 정상 배치된다.
    - drift 경고(codex R1-P1): 기존 파일이 현재 번들과 다르면(구버전/로컬수정) stale 반환 → --force 안내."""
    if not os.path.exists(src_skill_md):
        return ("missing", None)
    # defense-in-depth(codex 리뷰 P2): skill_id 가 전역 경로에 직접 조립되므로 경로 안전 토큰만 허용.
    # 호출부(generate)가 이미 검증하지만 helper 자체도 / · .. 등을 차단(독립 안전).
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_-]+$", skill_id):
        return ("error", f"unsafe skill_id: {skill_id!r}")
    dst = _codex_global_skill_path(skill_id)
    try:
        src_text = Path(src_skill_md).read_text(encoding="utf-8")
        if os.path.exists(dst) and not force:
            cur = Path(dst).read_text(encoding="utf-8")
            return ("skipped" if cur == src_text else "stale", dst)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        Path(dst).write_text(src_text, encoding="utf-8")
        return ("installed", dst)
    except (OSError, UnicodeError) as e:
        # 비치명적: 권한/읽기전용(OSError) + 비-UTF-8 기존 전역 스킬(UnicodeError, codex R2-P1).
        return ("error", f"{dst} ({e})")


def _profile_with_host(host, prefix):
    """templates/project-profile.yaml 을 읽어 host/prefix 만 치환(나머지는 빈 스키마 유지)."""
    src = os.path.join(_resources.templates_dir(), "project-profile.yaml")
    text = Path(src).read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("host: ") and "claude | codex" in line:
            out.append(line.split("host:")[0] + f"host: {host}                   # claude | codex — 설치 시 택1")
        elif s.startswith('prefix:'):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f'{indent}prefix: "{prefix}"')
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def _load_manifest(dest):
    """기존 manifest 를 dict 로 읽어 반환(없거나 손상 시 None). --force 재설치가 인스턴스 등록 자산을
    보존하는 데 쓰인다 — 못 읽으면 새 스켈레톤으로 폴백해 install 을 깨지 않는다(부트스트랩 fail-open)."""
    path = os.path.join(dest, "docs", "sage_harness", ".manifest.json")
    if not os.path.isfile(path):
        return None
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return m if isinstance(m, dict) else None


def _manifest(host, existing=None):
    """CORE hook 7종을 등록한 manifest(스켈레톤). hash/conformance 는 generate 가 스탬프.

    existing 이 주어지면(--force 재설치) 그 manifest 가 등록한 인스턴스 자산(sage generate 가 stamp 한
    mcps/agents/skills 및 사용자 추가 hook)을 보존하고 CORE hook 항목만 미스탬프 스켈레톤으로 되돌린다.
    CORE hook 은 엔진 자산이라 업그레이드 시 재스탬프 대상이지만, 다른 kind 는 인스턴스 소유라 profile.yaml
    과 같은 보존 정책을 따라야 한다 — 안 그러면 --force 가 등록을 지워 다음 validate 부터 orphan drift 가
    난다. 최초 install(existing=None)은 빈 스켈레톤(동작 불변)."""
    assets = {}
    if isinstance(existing, dict) and isinstance(existing.get("assets"), dict):
        # 인스턴스 등록 자산(mcps/agents/skills 및 사용자 추가 hook)만 보존한다. 값이 dict 가 아닌 손상
        # 항목은 버린다 — 보존하면 --force 뒤 sage validate 가 그 항목에서 .get() 크래시로 게이트가 죽는다.
        # 버려도 실물 spec 이 남아 있으면 validate 가 orphan(WARN)으로 잡아 --force 이전 거동과 동일하다.
        assets = {k: v for k, v in existing["assets"].items() if isinstance(v, dict)}
    for hid, form in _CORE_HOOKS:
        # CORE hook 은 엔진 자산 → 항상 미스탬프 스켈레톤으로 리셋(generate --write 가 hash/PASS 재스탬프).
        assets[f"hooks/{hid}"] = {
            "form": form, "conformance": "UNKNOWN", "risk": [], "unresolved": [],
        }
    return {
        # 설치를 만든 SAGE 패키지 버전을 그대로 스탬프(sage --version 과 일치).
        # template_version 은 manifest 포맷 버전이라 패키지 버전과 독립적으로 고정.
        "sage_version": __version__, "generator_version": __version__, "template_version": "1",
        "host_runtime": host,
        # 설치 인스턴스 마커(다중 신호) — 부트스트랩 게이트가 AGENT_GUIDE 분실 시에도 설치를 인식(codex R2-P0).
        "installed_instance": True,
        "assets": assets,
    }


def run(args) -> int:
    dest = os.path.abspath(args.dest)
    created, skipped = [], []
    pruned = []                 # 은퇴한 CORE skill 잔존 사본 정리 결과(5d)
    wrapper = "CLAUDE.md" if args.host == "claude" else "CODEX.md"
    core = _resources.core_dir()
    fw = os.path.join(core, "framework")
    # 첫 install 은 profile 이 없어 빈 dict. 주입은 claude host 만(아래 5c) — codex 는 해석 기전이 없다.
    # 단 구조 검사는 host 무관: 오타 역할/키는 어느 host 에서든 설정을 조용히 죽인다.
    _profile, _perr = _installed_profile(dest)
    if _perr:
        print(f"❌ {_perr}", file=sys.stderr)
        return 1
    agent_profile = _profile if args.host == "claude" else {}
    # 잘못된 값이 frontmatter 에 박히면 그 에이전트가 로드되지 않고, 오타 키/역할은 설정을 조용히 죽인다.
    # validate 와 **같은 검사**로 아무것도 쓰기 전에 멈춘다.
    _fails = [m for sev, m in team_runtime_issues(_profile) if sev == "FAIL"]
    if _fails:
        for _m in _fails:
            print(f"❌ {_m}", file=sys.stderr)
        print("   sage/project-profile.yaml 의 team.core 를 고친 뒤 다시 실행하세요 (`sage validate` 로 확인).",
              file=sys.stderr)
        return 1

    # 1. profile — 인스턴스 커스터마이즈 SSOT(위험분류/pdca/team 등). F5: 엔진 자산이 아니므로
    #    --force(엔진 업그레이드)여도 절대 덮어쓰지 않는다 — 덮으면 프로젝트 값 소실로 클린 업그레이드 불가.
    #    create-only: 새 설치 때만 빈 스키마 배치. reset 필요 시 사용자가 수동 삭제 후 재설치.
    prof_dst = os.path.join(dest, "sage", "project-profile.yaml")
    if os.path.exists(prof_dst):
        print("보존: sage/project-profile.yaml (인스턴스 profile — --force 라도 덮어쓰지 않음)")
    else:
        _write(prof_dst, _profile_with_host(args.host, args.prefix), args.force, created, skipped)

    # 2. framework 템플릿(중립): AGENT_GUIDE, {wrapper}, verification-protocol, verify-changes.sh, docs/agent/*
    _copy_file(os.path.join(fw, "AGENT_GUIDE.md"), os.path.join(dest, "AGENT_GUIDE.md"), args.force, created, skipped)
    _copy_file(os.path.join(fw, wrapper), os.path.join(dest, wrapper), args.force, created, skipped)
    _copy_file(os.path.join(fw, "verification-protocol.md"),
               os.path.join(dest, "verification-protocol.md"), args.force, created, skipped)
    _copy_file(os.path.join(fw, "scripts", "verify-changes.sh"),
               os.path.join(dest, "scripts", "verify-changes.sh"), args.force, created, skipped)
    _copy_tree(os.path.join(fw, "docs", "agent"), os.path.join(dest, "docs", "agent"), args.force, created, skipped)

    # 2b. 대화형 부트스트랩 트리거 — profile 을 대화로 채우는 설계상 진입점(런타임별 발견 메커니즘 상이).
    agents_md_collision = False
    codex_skill_status = None   # (status, dst) — codex host 전역 $sage-init 설치 결과
    core_skill_status = []      # [(id, (status, dst))] — codex host 전역 CORE skill 설치 결과(5c)
    skill_src_md = _core_skill_source(_CORE_BOOTSTRAP_SKILL)   # 단일 소스(중립 내용)
    if args.host == "claude":
        # claude: repo .claude/skills/ 자동발견 → /sage-init 스킬 배치.
        _copy_tree(os.path.join(fw, ".claude", "skills", "sage-init"),
                   os.path.join(dest, ".claude", "skills", "sage-init"), args.force, created, skipped)
        # claude: CORE 6인 에이전트 렌더 → .claude/agents/ (Claude Code 자동발견 경로)
        _copy_agent_renders(os.path.join(fw, ".claude", "agents"),
                            os.path.join(dest, ".claude", "agents"), agent_profile,
                            args.force, created, skipped)
    else:
        # codex: ① repo-스코프 스킬 자동발견 불가 → $sage-init 스킬을 전역($CODEX_HOME/skills)에 설치
        #           (--no-global-skill 로 opt-out — CI/샌드박스/타repo 검사용, codex R1-P1).
        #        ② codex 가 auto-read 하는 AGENTS.md 라우터(세션 시작 시 부트스트랩 안내, CODEX.md 는
        #           codex auto-read 아님). create-only: 기존 AGENTS.md 보존+경고(codex 협의 R4).
        if not getattr(args, "no_global_skill", False):
            codex_skill_status = _install_codex_global_skill(skill_src_md, args.force)
        else:
            codex_skill_status = ("disabled", None)
        agents_dst = os.path.join(dest, "AGENTS.md")
        if os.path.exists(agents_dst) and not args.force:
            agents_md_collision = True
        else:
            _copy_file(os.path.join(fw, "AGENTS.md"), agents_dst, args.force, created, skipped)
        # codex: CORE 6인 에이전트 렌더 → repo .codex/agents/ (claude host 가 .claude/agents/ 받듯
        #   codex host 도 자기 렌더를 받음 — 리소스 생성 시 codex 누락 금지, 사용자 지침).
        #   codex 는 에이전트 네이티브 자동발견이 없으나 SAGE 설계상 .codex/agents/<id>.md 가 자산 정본
        #   (write-guard·reverse_extract·CODEX.md). codex AI 는 AGENTS.md 라우팅으로 역할 정의를 참조.
        #   claude 렌더와 동일 소스 재사용(skill 전역배포와 같은 단일소스 패턴).
        _copy_tree(os.path.join(fw, ".claude", "agents"),
                   os.path.join(dest, ".codex", "agents"), args.force, created, skipped)

    # 3. CORE hook spec(중립 7종) → docs/sage_harness/hooks/
    specs = _resources.hook_specs_dir()
    for hid, _form in _CORE_HOOKS:
        _copy_file(os.path.join(specs, f"{hid}.md"),
                   os.path.join(dest, "docs", "sage_harness", "hooks", f"{hid}.md"), args.force, created, skipped)

    # 4. CORE hook 정본(core+adapter+strategy+native) → scripts/sage_harness/hooks/ (도메인값 0)
    _copy_tree(_resources.hooks_src_dir(), os.path.join(dest, "scripts", "sage_harness", "hooks"), args.force, created, skipped)

    # 5. CORE roster agent spec(중립 6인) → docs/sage_harness/agents/
    for aid in _CORE_AGENTS:
        _copy_file(os.path.join(core, "agents", f"{aid}.md"),
                   os.path.join(dest, "docs", "sage_harness", "agents", f"{aid}.md"), args.force, created, skipped)

    # 5b. CORE skill spec(중립 6종) → docs/sage_harness/skills/ (host 무관 — CORE agent spec 과 대칭).
    #     CORE 부트스트랩 자산이라 sage-init/CORE agent spec 과 동일하게 manifest 비추적(reference spec).
    #     manifest 추적 skill(spec+claims+render hash)은 generate/extract 흐름이 소유한다.
    for sid in _CORE_SKILLS:
        _copy_file(os.path.join(core, "skills", f"{sid}.md"),
                   os.path.join(dest, "docs", "sage_harness", "skills", f"{sid}.md"), args.force, created, skipped)

    # 5c. CORE skill 렌더 — 런타임별 발견 메커니즘(sage-init 과 동일 비대칭):
    #     claude=repo .claude/skills/ 자동발견, codex=전역 $CODEX_HOME/skills (repo-스코프 미발견).
    if args.host == "claude":
        for sid in _CORE_SKILLS:
            _copy_tree(os.path.join(fw, ".claude", "skills", sid),
                       os.path.join(dest, ".claude", "skills", sid), args.force, created, skipped)
    elif not getattr(args, "no_global_skill", False):
        for sid in _CORE_SKILLS:
            src_md = os.path.join(fw, ".claude", "skills", sid, "SKILL.md")
            core_skill_status.append((sid, _install_codex_global_skill(src_md, args.force, skill_id=sid)))

    # 5d. 은퇴한 CORE skill 잔존 사본 정리 — 옛 이름이 새 이름과 함께 남아 호출되는 혼선 방지.
    #     설치한 host 의 발견 경로만 정리(claude=repo .claude/skills, codex=전역 $CODEX_HOME/skills).
    for legacy in _LEGACY_CORE_SKILLS:
        if args.host == "claude":
            _prune_legacy_skill(os.path.join(dest, ".claude", "skills", legacy), pruned)
        elif not getattr(args, "no_global_skill", False):
            _prune_legacy_skill(os.path.join(_codex_skills_root(), legacy), pruned)

    # 6. manifest (CORE hook 등록 — generate 가 hash 스탬프). --force 재설치는 기존 manifest 의
    #    인스턴스 등록 자산(mcps/agents/skills)을 보존하고 CORE hook 만 리셋(profile.yaml 과 동일 보존 정책).
    _write(os.path.join(dest, "docs", "sage_harness", ".manifest.json"),
           json.dumps(_manifest(args.host, _load_manifest(dest)), ensure_ascii=False, indent=2) + "\n",
           args.force, created, skipped)

    # 7. spec 템플릿(사람 작성 참고) + schema(validate 참조)
    templates = _resources.templates_dir()
    for t in ("agent.spec.md", "hook.spec.md", "skill.spec.md", "claims.yml"):
        _copy_file(os.path.join(templates, t), os.path.join(dest, "sage", "templates", t), args.force, created, skipped)
    # manifest + profile 스키마 모두 vendor — profile 스키마는 project-profile 구조검증과
    # 오타 키 방어가 번들 폴백에 의존하지 않고 프로젝트 안에서 자립하도록.
    for s in ("manifest.schema.json", "profile.schema.json"):
        _copy_file(os.path.join(_resources.schema_dir(), s),
                   os.path.join(dest, "schema", s), args.force, created, skipped)

    # 보고
    print(f"== sage install (host={args.host}, prefix={args.prefix}) → {dest} ==")
    print(f"생성 {len(created)}건 (framework + CORE hook {len(_CORE_HOOKS)} + roster agent {len(_CORE_AGENTS)} + CORE agent render {len(_CORE_AGENTS)} + CORE skill {len(_CORE_SKILLS)}):")
    for p in sorted(created):
        print(f"  + {os.path.relpath(p, dest)}")
    if skipped:
        print(f"skip {len(skipped)}건 (이미 존재 — --force 로 덮어쓰기):")
        for p in sorted(skipped):
            print(f"  = {os.path.relpath(p, dest)}")
    if pruned:
        print(f"정리 {len(pruned)}건 (은퇴한 CORE skill 잔존 사본 제거):")
        for p in sorted(pruned):
            print(f"  - {p}")
    # --force(업그레이드) 재설치는 CORE 자산을 갱신하므로, 인스턴스가 등록한 kind(mcp/agent/skill)
    #    가 manifest 와 어긋나지 않았는지 설치 직후 바로 확인하도록 안내한다(현재는 사람이 별도 validate
    #    를 돌려야만 orphan drift 를 발견).
    if args.force:
        print("")
        print("   ℹ️  --force 재설치 완료. CORE hook 은 `sage generate --kind hook --write` 로 재스탬프하기")
        print("       전까지 STALE 이 정상입니다. 등록 자산(mcp/agent/skill) 보존 여부는 아래로 확인:")
        print("         sage validate --check --kind all")

    # 다음 단계 안내 — 설계상 진입점은 "AI 대화로 profile 채우기"다(직접 편집 아님).
    # profile 미부트스트랩(project.name 빈값) 상태에선 sage generate 가 BLOCK 된다(강제 게이트).
    runner = "claude" if args.host == "claude" else "codex"
    init_cmd = "/sage-init" if args.host == "claude" else "$sage-init"
    gen_cmd = "sage generate --kind hook --write" + ("" if args.host == "claude" else " --target codex")
    print("")
    print("다음 단계:")
    print(f"  1) 이 폴더에서 {runner} 실행 → `{init_cmd}` 입력")
    print("     AI 가 인터뷰로 sage/project-profile.yaml 을 채웁니다.")
    print(f"  2) 완료되면: {gen_cmd} → sage validate")
    print("")
    print("   설정을 마치기 전에는 `sage generate` 가 차단됩니다 (거버넌스 게이트).")

    if args.host == "claude":
        # CORE 렌더(skill/agent)는 create-only 라 --force 없이는 기존 사본이 skip 된다 →
        # 번들과 달라져도 조용히 stale 로 남을 수 있음. drift 확인 진입점을 안내(codex 전역 요약과 대칭).
        skipped_core = [p for p in skipped
                        if os.sep + ".claude" + os.sep in p and (os.sep + "skills" + os.sep in p
                                                                 or os.sep + "agents" + os.sep in p)]
        if skipped_core and not args.force:
            print("")
            print(f"   ℹ️  기존 CORE 렌더 {len(skipped_core)}건 skip(이미 존재). 번들과 다를 수 있으니 "
                  "`sage doctor` 로 drift 확인 — 갱신은 `sage install --host claude --force`.")
    if args.host == "codex":
        _print_codex_skill_summary(codex_skill_status, core_skill_status,
                                   getattr(args, "no_global_skill", False))
        if agents_md_collision:
            print("")
            print("   ⚠️  기존 AGENTS.md 가 있어 codex 부트스트랩 라우터를 배치하지 못했습니다.")
            print("       --force 로 교체하거나 templates 의 AGENTS.md 부트스트랩 섹션을 수동 병합하세요.")
    return 0


def _print_codex_skill_summary(codex_skill_status, core_skill_status, no_global_skill):
    """codex 전역 스킬 설치 결과를 상태별 카운트로 요약(개별 나열 대신). stale/error 만 갱신 안내."""
    if no_global_skill and not core_skill_status and (not codex_skill_status or codex_skill_status[0] == "disabled"):
        print("")
        print("   전역 CORE 스킬 설치 생략(--no-global-skill). 부트스트랩은 AGENTS.md 라우터로 안내됩니다.")
        return

    # (id, status) 전체 수집 — sage-init + CORE 스킬.
    entries = []
    if codex_skill_status:
        entries.append(("sage-init", codex_skill_status[0]))
    entries.extend((sid, st) for sid, (st, _dst) in core_skill_status)
    if not entries:
        return

    from collections import Counter
    counts = Counter(st for _sid, st in entries)
    total = len(entries)
    ok = counts.get("installed", 0) + counts.get("skipped", 0)
    stale = counts.get("stale", 0)
    err = counts.get("error", 0) + counts.get("missing", 0)

    print("")
    print(f"   전역 스킬 {total}종: 최신 {ok}" + (f", 갱신필요 {stale}" if stale else "") + (f", 실패 {err}" if err else ""))
    if stale:
        stale_ids = ", ".join(f"${sid}" for sid, st in entries if st == "stale")
        print(f"   ⚠️  갱신 필요: {stale_ids}")
        print("       → `sage install --host codex --force` (로컬 수정은 덮어써집니다)")
    if err:
        err_ids = ", ".join(f"${sid}" for sid, st in entries if st in ("error", "missing"))
        print(f"   ⚠️  설치 실패: {err_ids} (권한/읽기전용 home 또는 번들 손상?)")
