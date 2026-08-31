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
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from sage import __version__

from sage import _resources   # 번들 리소스 경로 단일 해석(env override + repo fallback — 재배치/설치 대비)
from sage.diagnostics import Diagnostic
from sage.runtime_api import HOOK_RUNTIME_API
from sage import overlay_common   # 오버레이 관리 블록 프리미티브(base_of 로 렌더 base 대조)
from sage import manifest_contract as _manifest_contract
from sage import overlay_materialize   # CORE 렌더 오버레이 물리화 + core_renders 앵커
from sage import install_transaction as _tx
from sage import managed_assets as _managed
from sage.i18n import exception_text, language_of, render_issue, tr

# CORE roster (중립 6인) + CORE hook 7종(form) + CORE skill 13종. 도메인값 아님 = framework 메타.
# skill 3분할: sage-cycle(00~06 우산) → sage-plan(00~02 기획) → sage-team(03~06 개발).
# sage-asset-override: CORE 자산 오버레이(sage/asset_overrides/**) 저작 — CORE 렌더 직접수정 대체 경로.
# roster 정본은 `sage.managed_assets` 다. 여기서는 목록을 다시 쓰지 않고 이름만 빌려 온다 —
# 기존 소비자(`generate`·`validate`·테스트)가 이 이름들을 import 하므로 이름은 유지한다.
# list() 로 감싸는 것은 기존 호출부가 list 를 기대하기 때문이고, 의미는 바뀌지 않는다.
_CORE_AGENTS = list(_managed.CORE_AGENTS)
_CORE_SKILLS = list(_managed.CORE_SKILLS)
_CORE_BOOTSTRAP_SKILLS = list(_managed.CORE_BOOTSTRAP_SKILLS)
_LEGACY_CORE_SKILLS = list(_managed.LEGACY_CORE_SKILLS)
_LEGACY_SKILL_SIGNATURE = _managed.LEGACY_SKILL_SIGNATURE
_LOCAL_PROFILE_IGNORE_START = "# >>> SAGE LOCAL PROFILE"
_LOCAL_PROFILE_IGNORE_END = "# <<< SAGE LOCAL PROFILE"
_LOCAL_PROFILE_IGNORE_ENTRY = "/sage/project-profile.local.yaml"
_LOCAL_STATE_IGNORE_START = "# >>> SAGE LOCAL STATE"
_LOCAL_STATE_IGNORE_END = "# <<< SAGE LOCAL STATE"
_LOCAL_STATE_IGNORE_ENTRIES = (
    "!/.sage/",
    "/.sage/*",
    "!/.sage/override.jsonl",
    "!/.sage/acceptance-waivers.jsonl",
    "!/.sage/loop_audit.jsonl",
    "!/.sage/fast_cycle.jsonl",
)
_RETRO_AUDIT_REL = os.path.join(".sage", "retro_audit.jsonl")
_CORE_HOOKS = [tuple(entry) for entry in _managed.CORE_HOOKS]
_SKIP_DIRS = {"tests", "__pycache__"}


def _exception_text(language, exc):
    """`sage.i18n.exception_text` 의 이 모듈용 이름. 문장 조립 규칙은 한 곳에만 둔다."""
    return exception_text(language, exc)


def register(sub, context):
    p = sub.add_parser(
        "install",
        help=tr(context, "cli.install.install"),
        add_help=False,
        usage="sage install --host {claude,codex} [--skill-scope {global,project-local}] [--prefix PREFIX] [--dest DEST] [--force] [--help]",
    )
    p.add_argument("--help", action="help", help=tr(context, "cli.install.help"))
    p.add_argument("--host", choices=["claude", "codex"], required=True,
                   help=tr(context, "cli.install.host"))
    p.add_argument("--prefix", default="sage", help=tr(context, "cli.install.prefix"))
    p.add_argument("--dest", default=".", help=tr(context, "cli.install.dest"))
    p.add_argument("--force", action="store_true", help=tr(context, "cli.install.force"))
    p.add_argument("--skill-scope", choices=["global", "project-local"], default=None,
                   help=tr(context, "cli.install.skill_scope"))
    p.add_argument("--no-global-skill", action="store_true",
                   help=tr(context, "cli.install.no_global_skill"))
    p._optionals.title = tr(context, "cli.install.optionals_title")
    p.set_defaults(func=run)


def _atomic_write(path, content, executable=False, transaction=None):
    """Write one leaf atomically, optionally preserving its pre-run object in a journal."""
    previous_mode = None
    try:
        previous_stat = os.lstat(path)
        if stat.S_ISREG(previous_stat.st_mode):
            previous_mode = stat.S_IMODE(previous_stat.st_mode)
    except FileNotFoundError:
        pass
    if executable:
        desired_mode = 0o755
    elif previous_mode is not None:
        desired_mode = previous_mode
    else:
        desired_mode = None
    if transaction is not None:
        transaction.stage_write(path)
        transaction.declare_file_output(path, content, desired_mode)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    overlay_common.write_text_lf(path, content, mode=desired_mode)
    if transaction is not None:
        transaction.record_output(path)


def _write(path, content, force, created, skipped, executable=False, transaction=None):
    if os.path.lexists(path) and not force:
        skipped.append(path)
        return
    _atomic_write(path, content, executable=executable, transaction=transaction)
    created.append(path)


def _copy_file(src, dst, force, created, skipped, transaction=None):
    if not os.path.exists(src):
        return
    executable = src.endswith(".sh")
    _write(dst, Path(src).read_text(encoding="utf-8"), force, created, skipped, executable,
           transaction=transaction)


def _render_gitignore_block(current, start_marker, end_marker, entries, label,
                            blank_before=True):
    """Preserve user entries while replacing one deterministic managed block."""
    text = current.replace("\r\n", "\n").replace("\r", "\n")
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)
    if start_count != end_count or start_count > 1:
        raise _tx.InstallDriftError(Diagnostic("install.gitignore_marker_corrupt", label=label))
    block = f"{start_marker}\n" + "\n".join(entries) + f"\n{end_marker}\n"
    if start_count == 1:
        start = text.index(start_marker)
        end_start = text.index(end_marker)
        if end_start < start:
            raise _tx.InstallDriftError(Diagnostic("install.gitignore_marker_corrupt", label=label))
        end = end_start + len(end_marker)
        text = text[:start] + block + text[end:].lstrip("\n")
    else:
        text = text.rstrip("\n")
        separator = "\n\n" if blank_before else "\n"
        text = f"{text}{separator}{block}" if text else block
    return text.rstrip("\n") + "\n"


def _render_local_profile_gitignore(current):
    """Install deterministic local-profile and local-state ignore policies."""
    rendered = _render_gitignore_block(
        current,
        _LOCAL_PROFILE_IGNORE_START,
        _LOCAL_PROFILE_IGNORE_END,
        (_LOCAL_PROFILE_IGNORE_ENTRY,),
        "SAGE LOCAL PROFILE",
    )
    return _render_gitignore_block(
        rendered,
        _LOCAL_STATE_IGNORE_START,
        _LOCAL_STATE_IGNORE_END,
        _LOCAL_STATE_IGNORE_ENTRIES,
        "SAGE LOCAL STATE",
        blank_before=False,
    )


def _write_local_profile_gitignore(dest, created, skipped, transaction):
    path = os.path.join(dest, ".gitignore")
    if os.path.lexists(path):
        mode = os.lstat(path).st_mode
        if not stat.S_ISREG(mode):
            raise _tx.InstallDriftError(Diagnostic("install.gitignore_not_regular_file", path=path))
        current = Path(path).read_text(encoding="utf-8")
    else:
        current = ""
    rendered = _render_local_profile_gitignore(current)
    if rendered == current:
        skipped.append(path)
        return
    _atomic_write(path, rendered, transaction=transaction)
    created.append(path)


def _warn_if_retro_audit_tracked(dest, language=None):
    """Report the one-time index migration without changing Git or local audit bytes."""
    try:
        result = subprocess.run(
            ["git", "-C", dest, "ls-files", "--error-unmatch", "--", _RETRO_AUDIT_REL],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        return
    print(
        tr(language, 'cli.install.msg01'),
        file=sys.stderr,
    )


def _prune_legacy_skill(skill_dir, pruned, transaction=None):
    """은퇴한 CORE skill 사본을 제거(rename 수렴). codex 전역 $CODEX_HOME/skills 는 공유 공간이라
    SKILL.md 에 SAGE hand-ship 시그니처가 있을 때만 삭제 — 같은 이름의 사용자 skill 오삭제 방지(codex R2-P2).
    비치명적: 권한/읽기전용/비-UTF-8 실패는 install 을 깨지 않는다(전역 home 쓰기와 동일 철학)."""
    skill_md = os.path.join(skill_dir, "SKILL.md")
    try:
        dir_mode = os.lstat(skill_dir).st_mode
        marker_mode = os.lstat(skill_md).st_mode
    except OSError:
        return
    if not stat.S_ISDIR(dir_mode) or not stat.S_ISREG(marker_mode):
        return
    try:
        if _LEGACY_SKILL_SIGNATURE not in Path(skill_md).read_text(encoding="utf-8"):
            return   # SAGE 가 ship 한 자산 아님 → 사용자 skill 로 보고 보존
        if transaction is not None:
            transaction.stage_remove_tree(skill_dir)
        else:
            shutil.rmtree(skill_dir)
        pruned.append(skill_dir)
    except (OSError, UnicodeError):
        pass


def _prune_legacy_native_write_guard(dest, pruned, transaction=None):
    """Remove the retired shell canonical source during a force upgrade."""
    path = os.path.join(
        dest, "scripts", "sage_harness", "hooks",
        "generated-artifact-write-guard.sh")
    if not os.path.lexists(path):
        return
    if transaction is not None:
        transaction.stage_remove_tree(path)
    elif os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.unlink(path)
    pruned.append(path)


def _copy_tree(src_dir, dst_dir, force, created, skipped, transaction=None):
    """src_dir 하위 전체 복사(tests/__pycache__ 제외, .sh 는 실행권한)."""
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            s = os.path.join(root, fn)
            d = os.path.join(dst_dir, os.path.relpath(s, src_dir))
            _copy_file(s, d, force, created, skipped, transaction=transaction)


def _installed_profile(dest):
    """dest 의 인스턴스 profile → (profile, error). install 은 profile 을 --force 로도 덮지 않으므로,
    `sage-init` 로 채운 뒤 `sage install --force` 를 다시 돌리면 그 값으로 에이전트가 재렌더된다.

    파싱 실패를 `{}` 로 삼키면 **설정이 조용히 무시된 채 기본 렌더가 배포된다** → error 를 돌려
    호출자가 무변경 exit 1 하게 한다(codex 5R). 파일 부재는 첫 install 이라 정상.
    """
    return overlay_materialize.load_profile(dest)


def _copy_agent_renders(src_dir, dst_dir, profile, force, created, skipped, transaction=None):
    """CORE 에이전트 렌더 배치. claude host 만 profile 의 model/effort 를 frontmatter 로 주입한다
    (codex 는 .codex/agents/<id>.md 를 model/effort 로 해석하는 기전이 없어 주입해도 무동작)."""
    for fn in sorted(os.listdir(src_dir)) if os.path.isdir(src_dir) else []:
        if not fn.endswith(".md"):
            continue
        src = os.path.join(src_dir, fn)
        dst = os.path.join(dst_dir, fn)
        overrides = agent_frontmatter_overrides(profile, fn[:-3])
        _write(dst, render_core_agent(Path(src).read_text(encoding="utf-8"), overrides),
               force, created, skipped, transaction=transaction)


def _codex_skills_root():
    """Codex global skill root = $CODEX_HOME/skills (or ~/.codex/skills).

    This is only the `global` install scope. `project-local` is rooted at the target
    repository's `.codex/skills`; callers must never infer one scope from CODEX_HOME."""
    base = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(base, "skills")


def _codex_global_skill_path(skill_id):
    return os.path.join(_codex_skills_root(), skill_id, "SKILL.md")


def _codex_project_skill_path(dest, skill_id):
    return os.path.join(os.path.abspath(dest), ".codex", "skills", skill_id, "SKILL.md")


def _resolve_skill_scope(args, language=None):
    """Return the effective CORE skill scope, or an actionable CLI-contract error."""
    scope = getattr(args, "skill_scope", None)
    disabled = bool(getattr(args, "no_global_skill", False))
    if args.host == "claude":
        if scope is not None:
            return None, tr(language, "cli.install.skill_scope_claude_not_allowed")
        return "project-local", None
    if disabled and scope is not None:
        return None, tr(language, "cli.install.skill_scope_conflicts_no_global")
    if disabled:
        return "disabled", None
    if scope not in ("global", "project-local"):
        return None, tr(language, "cli.install.skill_scope_codex_required")
    return scope, None


def _core_skill_source(skill_id):
    """hand-shipped CORE skill render source. The same source is used for Claude repo skills
    and Codex global skills, so install/doctor must compare against this exact artifact."""
    return os.path.join(_resources.core_dir(), "framework", ".claude", "skills", skill_id, "SKILL.md")


def core_skill_ids():
    """CORE skill ids installed into the explicitly selected host discovery surface."""
    return [*_CORE_BOOTSTRAP_SKILLS, *_CORE_SKILLS]


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


def agent_frontmatter_issue(overrides, scope="team.core.*"):
    """주입 직전 최종 관문 — 잘못된 값이 에이전트 파일에 박히면 그 에이전트가 로드되지 않는다.
    `sage validate` 를 거치지 않고 `sage install --force` 만 돌린 경우를 위해 install 도 직접 검사한다.

    `scope` 는 메시지에 실릴 경로 접두사다 — 호출부가 실제 역할을 알면 넘기고(예: `team.core.reviewer`),
    모르면 기본값(`team.core.*`)을 그대로 쓴다. 이전에는 반환 문자열을 호출부가 `.replace()` 로
    후처리했는데, Diagnostic 은 완성 문장이 아니라 인자를 들고 있어 후처리 자체가 성립하지 않는다."""
    model, effort = overrides.get("model"), overrides.get("effort")
    if model is not None and not (isinstance(model, str)
                                  and (model in AGENT_MODEL_ALIASES or _MODEL_ID_RE.match(model))):
        return Diagnostic("install.team_runtime_model_invalid", scope=scope, model=repr(model),
                          aliases=", ".join(AGENT_MODEL_ALIASES))
    if effort is not None and not (effort in AGENT_EFFORTS
                                   or (isinstance(effort, int) and not isinstance(effort, bool) and effort > 0)):
        return Diagnostic("install.team_runtime_effort_invalid", scope=scope, effort=repr(effort),
                          efforts=", ".join(AGENT_EFFORTS))
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
        return [("FAIL", Diagnostic("install.team_not_mapping", type_name=type(team).__name__))]
    core = team.get("core")
    if core in (None, ""):
        return []
    if not isinstance(core, dict):
        return [("FAIL", Diagnostic("install.team_core_not_mapping", type_name=type(core).__name__))]
    from sage.runtime_hosts import active_host
    host = active_host(profile)
    issues = []
    for role, spec in core.items():
        # 키가 비-str 일 수 있다(YAML `1: {...}`) → 어떤 입력에도 크래시 없이 FAIL 로 떨어져야 한다.
        if role not in _CORE_AGENTS:
            issues.append(("FAIL", Diagnostic("install.team_unknown_role", role=str(role),
                                              roster=", ".join(_CORE_AGENTS))))
            continue
        if not isinstance(spec, dict):
            # 조용히 넘기면 이 역할의 설정 전체가 무시된 채 기본 렌더가 배포된다.
            issues.append(("FAIL", Diagnostic("install.team_role_not_mapping", role=role,
                                              type_name=type(spec).__name__)))
            continue
        stray = [k for k in spec if k not in _ROLE_KEYS]
        if stray:
            # `runtim:` 오타는 아무도 안 읽어 기본 렌더가 나간다 — 설정한 model 이 조용히 사라진다.
            issues.append(("FAIL", Diagnostic("install.team_role_unknown_keys", role=role,
                                              keys=", ".join(sorted(str(k) for k in stray)),
                                              allowed=", ".join(sorted(_ROLE_KEYS)))))
        legacy = [k for k in ("model", "effort") if spec.get(k) not in (None, "")]
        if legacy:
            issues.append(("WARN", Diagnostic("install.team_role_legacy_fields", role=role,
                                              legacy="/".join(legacy))))
        rt = spec.get(_RUNTIME_KEY)
        if rt in (None, ""):
            continue
        if not isinstance(rt, dict):
            issues.append(("FAIL", Diagnostic("install.team_runtime_not_mapping", role=role,
                                              type_name=type(rt).__name__)))
            continue
        unknown = [k for k in rt if k not in ("model", "effort")]
        if unknown:
            issues.append(("FAIL", Diagnostic("install.team_runtime_unknown_keys", role=role,
                                              keys=", ".join(sorted(str(k) for k in unknown)))))
        issue = agent_frontmatter_issue({k: rt[k] for k in ("model", "effort") if rt.get(k) not in (None, "")},
                                        scope=f"team.core.{role}")
        if issue:
            issues.append(("FAIL", issue))
        if host == "codex" and any(rt.get(k) not in (None, "") for k in ("model", "effort")):
            issues.append(("WARN", Diagnostic("install.team_runtime_codex_inert", role=role)))
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
        # 오버레이 물리화 이후 설치본은 base + 관리 블록일 수 있다. drift 는 **base 만** 대조한다
        # (블록 반영/변조는 overlay_materialize.check 가 별도 담당) — 정당한 오버레이가 stale 오판되지 않도록.
        exp_base, _ = overlay_common.base_of(expected)
        installed, rerr = overlay_common.read_text_lf(dst)
        if rerr:
            return ("error", rerr)
        got_base, berr = overlay_common.base_of(installed)
        if berr:
            return ("error", Diagnostic("install.render_marker_error", path=dst, reason=berr))
        return ("ok" if got_base == exp_base else "stale", dst)
    except (OSError, UnicodeError) as e:
        return ("error", f"{dst} ({e})")


def codex_core_skill_status(skill_id, dest=None, scope="global"):
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
    if scope == "global":
        dst = _codex_global_skill_path(skill_id)
    elif scope == "project-local" and dest is not None:
        dst = _codex_project_skill_path(dest, skill_id)
        return core_render_status(src, dst)
    else:
        return ("error", f"invalid Codex CORE skill scope: {scope!r}")
    if not os.path.exists(dst):
        return ("missing", dst)
    try:
        src_text = Path(src).read_text(encoding="utf-8")
        cur = Path(dst).read_text(encoding="utf-8")
        return ("ok" if cur == src_text else "stale", dst)
    except (OSError, UnicodeError) as e:
        return ("error", f"{dst} ({e})")


def codex_core_skill_surfaces(root, skill_id):
    """Inspect every known Codex-visible CORE skill surface without choosing precedence."""
    src = _core_skill_source(skill_id)
    return {
        "global": codex_core_skill_status(skill_id, scope="global"),
        "project-local": codex_core_skill_status(skill_id, dest=root, scope="project-local"),
        "agents-local": core_render_status(
            src, os.path.join(os.path.abspath(root), ".agents", "skills", skill_id, "SKILL.md")),
    }


def _install_codex_skill_at(src_skill_md, dst, force, skill_id="sage-init", transaction=None):
    """Install one bundled CORE skill at an already selected trusted root."""
    if not os.path.exists(src_skill_md):
        return ("missing", None)
    import re as _re
    if not _re.match(r"^[A-Za-z0-9_-]+$", skill_id):
        return ("error", f"unsafe skill_id: {skill_id!r}")
    try:
        src_text = Path(src_skill_md).read_text(encoding="utf-8")
        if os.path.exists(dst) and not force:
            cur = Path(dst).read_text(encoding="utf-8")
            return ("skipped" if cur == src_text else "stale", dst)
        _atomic_write(dst, src_text, transaction=transaction)
        return ("installed", dst)
    except (OSError, UnicodeError) as e:
        if transaction is not None:
            try:
                transaction.restore_path(dst)
            except (OSError, _tx.InstallDriftError) as restore_error:
                # 이 함수의 다른 오류 문자열(위 unsafe skill_id 등)도 이미 영어 고정이다 — 같은 표면.
                raise RuntimeError(f"CORE skill write and rollback both failed: {dst} ({restore_error})") from e
        return ("error", f"{dst} ({e})")


def _install_codex_global_skill(src_skill_md, force, skill_id="sage-init", transaction=None):
    """codex 스킬을 $CODEX_HOME/skills/{skill_id}/SKILL.md 에 전역 설치.

    반환: (status, dst) — status ∈ {installed, skipped, stale, missing, error}. create-only(force 면 덮어쓰기).
    repo-스코프(--dest) 밖 전역 쓰기이므로 created/skipped 리스트가 아닌 별도 상태로 보고한다.
    - 비치명적(codex R1-P0): 전역 home 쓰기 실패(read-only/정책잠금)는 install 을 깨지 않고 error 반환
      → 호출부가 경고+수동 폴백(AGENTS.md) 안내. repo-로컬 산출물은 정상 배치된다.
    - drift 경고(codex R1-P1): 기존 파일이 현재 번들과 다르면(구버전/로컬수정) stale 반환 → --force 안내."""
    dst = _codex_global_skill_path(skill_id)
    return _install_codex_skill_at(src_skill_md, dst, force, skill_id, transaction)


def _install_codex_project_skill(dest, src_skill_md, force, skill_id="sage-init", transaction=None):
    dst = _codex_project_skill_path(dest, skill_id)
    return _install_codex_skill_at(src_skill_md, dst, force, skill_id, transaction)


def _profile_with_host(host, prefix, language=None):
    """templates/project-profile.yaml 을 읽어 version/host/prefix 만 치환한다.

    주석 3줄은 생성 산출물 본문(b-2 정책) — 아직 어느 cycle 에도 안 묶인 최초 스캐폴드라
    Document-Language 마커가 없다. display 언어(`--lang`)를 폴백으로 쓴다(cycle.py 의
    `_document_language()` 와 같은 원칙)."""
    src = os.path.join(_resources.templates_dir(), "project-profile.yaml")
    text = Path(src).read_text(encoding="utf-8")
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("required_version:"):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f'{indent}required_version: "{__version__}" '
                       f'# {tr(language, "cli.install.profile_comment_required_version")}')
        elif s.startswith("installed_hosts:"):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f"{indent}installed_hosts: [{host}]       "
                       f'# {tr(language, "cli.install.profile_comment_installed_hosts")}')
        elif s.startswith("active_host:"):
            # auto 가 기본이다. 어느 host 로 일하는지는 개발자별·세션별 사실인데 이 파일은 커밋되고
            # local profile 이 이 키를 덮을 수 없어서(profile_layers._SECTION_KEYS), 값을 박아두면
            # host 를 옮길 때마다 공유 파일을 고쳐야 한다 — 이 파일은 게이트 정책 소스라 L2 다.
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f"{indent}active_host: auto               "
                       f'# {tr(language, "cli.install.profile_comment_active_host")}')
        elif s.startswith('prefix:'):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f'{indent}prefix: "{prefix}"')
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def _load_manifest(dest):
    """기존 manifest 를 dict 로 읽어 반환(없거나 손상 시 None).

    호출자는 경로 존재 여부를 별도로 확인해 non-force 손상을 fail-closed 처리하고, 명시적 --force만
    새 스켈레톤 recovery를 허용한다.
    """
    path = os.path.join(dest, "docs", "sage_harness", ".manifest.json")
    if os.path.lexists(path):
        issue = overlay_materialize._project_path_issue(dest, path, leaf_kind="file")
        if issue:
            return None
    if not os.path.isfile(path):
        return None
    try:
        m = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return m if isinstance(m, dict) else None


def _asset_entry_issue(value, language=None):
    """자산 항목 하나의 문제를 문장으로. 판정은 `manifest_contract` 가 소유한다."""
    broken = _manifest_contract.asset_entry_violation(value)
    if broken is None:
        return None
    fields = {name: item for name, item in broken.items() if name not in ("kind", "code")}
    return tr(language, f"cli.install.{broken['code']}", **fields)


def _valid_asset_entry(value):
    return _manifest_contract.asset_entry_violation(value) is None


def _valid_core_receipt(receipt):
    return _manifest_contract.core_render_receipt_violation("", receipt) is None


def _valid_core_skill_receipt(receipt):
    return _manifest_contract.core_skill_receipt_shape(receipt)


def _manifest_structure_issue(manifest, language=None):
    """Return a fail-closed issue for fields install would otherwise normalize or discard.

    판정은 `manifest_contract` **하나**가 한다. 같은 파일을 uninstall 도 소유권 증거로 읽는데,
    읽는 쪽마다 기준을 따로 두면 **가장 느슨한 쪽이 실제 기준**이 된다. 실제로 그렇게 갈라진
    적이 있다 — 여기서는 `core_renders` receipt 의 SHA-256 을 대조했고 uninstall 은 그것이
    dict 인지만 봤다. 그래서 빈 receipt 를 가진 manifest 가 install 에서는 거부되고 uninstall
    에서는 소유권 증거로 통과해, 사용자가 자기 내용으로 바꿔 둔 파일이 `DELETE` 됐다.

    이 함수에 남은 일은 **code 를 문장으로 만드는 것뿐**이다. 판정을 여기 한 줄이라도 남기면
    그 줄이 다음 갈라짐의 씨앗이 된다.
    """
    broken = _manifest_contract.violation(manifest)
    if broken is None:
        return None
    asset = broken.get("asset")
    fields = {name: value for name, value in broken.items()
              if name not in ("kind", "code", "asset")}
    message = tr(language, f"cli.install.{broken['code']}", **fields)
    return f"assets/{asset}/{message}" if asset is not None else message


def _manifest(host, existing=None, core_renders=None, skill_scope=None):
    """CORE hook 7종을 등록한 manifest(스켈레톤). hash/conformance 는 generate 가 스탬프.

    existing 이 주어지면(--force 재설치) 그 manifest 가 등록한 인스턴스 자산(sage generate 가 stamp 한
    mcps/agents/skills 및 사용자 추가 hook)을 보존하고 CORE hook 항목만 미스탬프 스켈레톤으로 되돌린다.
    CORE hook 은 엔진 자산이라 업그레이드 시 재스탬프 대상이지만, 다른 kind 는 인스턴스 소유라 profile.yaml
    과 같은 보존 정책을 따라야 한다 — 안 그러면 --force 가 등록을 지워 다음 validate 부터 orphan drift 가
    난다. 최초 install(existing=None)은 빈 스켈레톤(동작 불변).

    core_renders 는 엔진 소유 최상위 맵(오버레이 base drift 영수증). CORE hook 처럼 인스턴스 보존
    대상이 아니라 매 install 마다 최종 base 로 전량 재계산한다 — preserved 옛 앵커가 새 버전과 공존해
    skew 를 감추지 못하도록(assets 보존에서 제외)."""
    assets = {}
    if isinstance(existing, dict) and isinstance(existing.get("assets"), dict):
        # 인스턴스 등록 자산(mcps/agents/skills 및 사용자 추가 hook)만 보존한다. 값이 dict 가 아닌 손상
        # 항목은 버린다 — 보존하면 --force 뒤 sage validate 가 그 항목에서 .get() 크래시로 게이트가 죽는다.
        # 버려도 실물 spec 이 남아 있으면 validate 가 orphan(WARN)으로 잡아 --force 이전 거동과 동일하다.
        assets = {k: v for k, v in existing["assets"].items()
                  if isinstance(k, str) and _valid_asset_entry(v)}
    for hid, form in _CORE_HOOKS:
        # CORE hook 은 엔진 자산 → 항상 미스탬프 스켈레톤으로 리셋(generate --write 가 hash/PASS 재스탬프).
        assets[f"hooks/{hid}"] = {
            "form": form, "conformance": "UNKNOWN", "risk": [], "unresolved": [],
        }
    previous_primary = existing.get("host_runtime") if isinstance(existing, dict) else None
    previous_hosts = existing.get("installed_hosts") if isinstance(existing, dict) else None
    if not isinstance(previous_hosts, list):
        previous_hosts = []
    if previous_primary in ("claude", "codex"):
        previous_hosts = [previous_primary, *previous_hosts]
    installed_hosts = list(dict.fromkeys([h for h in previous_hosts + [host]
                                          if h in ("claude", "codex")]))
    from sage.build_identity import source_identity
    identity = source_identity()
    merged_core_renders = {}
    if isinstance(existing, dict) and isinstance(existing.get("core_renders"), dict):
        merged_core_renders = {key: value for key, value in existing["core_renders"].items()
                               if (isinstance(key, str) and not key.startswith(host + "/")
                                   and _valid_core_receipt(value))}
    if isinstance(core_renders, dict):
        merged_core_renders.update(core_renders)
    receipts = {}
    if isinstance(existing, dict) and isinstance(existing.get("core_skill_receipts"), dict):
        receipts = {key: value for key, value in existing["core_skill_receipts"].items()
                    if key in ("claude", "codex") and _valid_core_skill_receipt(value)}
    effective_scope = skill_scope or ("project-local" if host == "claude" else None)
    if effective_scope in ("global", "project-local", "disabled"):
        receipts[host] = {"scope": effective_scope, "sage_version": __version__}
    # AGENT_GUIDE is one physical render shared by both hosts. Refresh every installed host's
    # receipt together so a force upgrade cannot preserve a knowingly stale other-host hash.
    shared_key = f"{host}/framework/AGENT_GUIDE"
    shared_receipt = merged_core_renders.get(shared_key)
    if isinstance(shared_receipt, dict):
        for installed_host in installed_hosts:
            merged_core_renders[f"{installed_host}/framework/AGENT_GUIDE"] = dict(shared_receipt)
    return {
        # 설치를 만든 SAGE 패키지 버전을 그대로 스탬프(sage --version 과 일치).
        # template_version 은 manifest 포맷 버전이라 패키지 버전과 독립적으로 고정.
        "sage_version": __version__, "generator_version": __version__, "template_version": "1",
        # 이 설치가 요구하는 hook runtime API. `generator_version` 과 같은 자리에 스탬프하는
        # 이유는 둘이 같은 사실의 두 면이기 때문이다 — 어느 package 가 만들었고, 그 package 의
        # hook 이 어떤 runtime 을 필요로 하는가. 갈라 두면 한쪽만 갱신되는 상태가 생긴다.
        "runtime_api": {"required": HOOK_RUNTIME_API},
        "host_runtime": previous_primary if previous_primary in ("claude", "codex") else host,
        "installed_hosts": installed_hosts,
        **identity,
        # 설치 인스턴스 마커(다중 신호) — 부트스트랩 게이트가 AGENT_GUIDE 분실 시에도 설치를 인식(codex R2-P0).
        "installed_instance": True,
        "assets": assets,
        "core_skill_receipts": receipts,
        # 엔진 소유(인스턴스 자산 아님) — 매 install 재계산, 보존 안 함.
        "core_renders": merged_core_renders,
    }


def _core_render_expected_base(host, kind, asset_id, profile):
    """Return the canonical base shipped for one overlay_materialize render target."""
    fw = os.path.join(_resources.core_dir(), "framework")
    if kind == "framework":
        src = os.path.join(fw, f"{asset_id}.md")
    elif kind == "agents":
        src = os.path.join(fw, ".claude", "agents", f"{asset_id}.md")
    elif kind == "skills":
        src = _core_skill_source(asset_id)
    else:
        return None, Diagnostic("install.unknown_core_render_kind", kind=kind)

    text, read_error = overlay_common.read_text_lf(src)
    if read_error:
        return None, Diagnostic("install.canonical_load_failed", reason=read_error)
    if kind == "agents" and host == "claude":
        text = render_core_agent(text, agent_frontmatter_overrides(profile, asset_id))
    base, marker_error = overlay_common.base_of(text)
    if marker_error:
        return None, Diagnostic("install.canonical_marker_error", path=src, reason=marker_error)
    return base, None


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _core_render_path_issue(dest, path, allow_leaf_symlink=False):
    """Return a deterministic conflict for unsafe filesystem objects below dest."""
    root = os.path.abspath(dest)
    target = os.path.abspath(path)
    try:
        if os.path.commonpath((root, target)) != root:
            return (Diagnostic("install.core_render_path_outside_root"),
                    _sha256_text(f"outside:{target}"))
    except ValueError:
        return (Diagnostic("install.core_render_path_filesystem_mismatch"),
                _sha256_text(f"outside:{target}"))

    rel_parts = Path(os.path.relpath(target, root)).parts
    cursor = root
    for index, part in enumerate(rel_parts):
        cursor = os.path.join(cursor, part)
        is_leaf = index == len(rel_parts) - 1
        try:
            mode = os.lstat(cursor).st_mode
        except FileNotFoundError:
            return None
        except OSError as exc:
            return Diagnostic("install.core_render_path_stat_failed", cursor=cursor, exc=exc), "unavailable"

        rel_cursor = os.path.relpath(cursor, root)
        if stat.S_ISLNK(mode):
            if is_leaf and allow_leaf_symlink:
                return None
            try:
                link_value = os.readlink(cursor)
                actual_sha = _sha256_text(f"symlink:{rel_cursor}:{link_value}")
            except OSError:
                actual_sha = "unavailable"
            location = "leaf" if is_leaf else "ancestor"
            return (Diagnostic("install.core_render_path_symlink_untrusted",
                               location=location, rel_cursor=rel_cursor), actual_sha)
        if not is_leaf and not stat.S_ISDIR(mode):
            return (Diagnostic("install.core_render_path_ancestor_not_dir", rel_cursor=rel_cursor),
                    _sha256_text(f"ancestor-mode:{rel_cursor}:{stat.S_IFMT(mode):o}"))
        if is_leaf and not stat.S_ISREG(mode):
            return (Diagnostic("install.core_render_path_not_regular_file", rel_cursor=rel_cursor),
                    _sha256_text(f"leaf-mode:{rel_cursor}:{stat.S_IFMT(mode):o}"))
    return None


def _core_trust_conflicts(dest, host, profile, existing_manifest, allow_base_replacement=False,
                          codex_skill_scope=None):
    """Read-only CORE render trust preflight for non-force install.

    An existing file is anchor-eligible only when its canonical base still matches any previous
    receipt and exactly matches the render shipped by the current package/profile.
    """
    anchors = existing_manifest.get("core_renders") if isinstance(existing_manifest, dict) else None
    anchors = anchors if isinstance(anchors, dict) else {}
    conflicts = []

    for kind, asset_id, path in overlay_materialize.render_targets(
            dest, host, codex_skill_scope):
        key = overlay_materialize.anchor_key(host, kind, asset_id)
        expected, expected_error = _core_render_expected_base(host, kind, asset_id, profile)
        expected_sha = _sha256_text(expected) if expected is not None else "unavailable"
        if expected_error:
            conflicts.append({"key": key, "path": path, "reason": expected_error,
                              "expected_sha": expected_sha, "actual_sha": "unavailable"})
            continue
        path_issue = _core_render_path_issue(dest, path, allow_leaf_symlink=allow_base_replacement)
        if path_issue:
            reason, actual_sha = path_issue
            conflicts.append({"key": key, "path": path, "reason": reason,
                              "expected_sha": expected_sha, "actual_sha": actual_sha})
            continue
        if allow_base_replacement:
            continue
        if not os.path.lexists(path):
            continue

        installed, read_error = overlay_common.read_text_lf(path)
        if read_error:
            conflicts.append({"key": key, "path": path, "reason": read_error,
                              "expected_sha": expected_sha, "actual_sha": "unavailable"})
            continue
        actual_base, marker_error = overlay_common.base_of(installed)
        actual_sha = _sha256_text(actual_base if marker_error is None else installed)
        if marker_error:
            conflicts.append({"key": key, "path": path,
                              "reason": Diagnostic("install.installed_marker_error",
                                                   reason=marker_error),
                              "expected_sha": expected_sha, "actual_sha": actual_sha})
            continue

        anchor = anchors.get(key)
        if anchor is not None:
            anchor_sha = anchor.get("base_sha256") if isinstance(anchor, dict) else None
            if not isinstance(anchor_sha, str) or anchor_sha != actual_sha:
                conflicts.append({"key": key, "path": path,
                                  "reason": Diagnostic("install.anchor_base_mismatch"),
                                  "expected_sha": expected_sha, "actual_sha": actual_sha})
                continue
        if actual_sha != expected_sha:
            reason = (Diagnostic("install.anchor_matches_but_base_changed")
                      if anchor is not None else
                      Diagnostic("install.untrusted_render_base_mismatch"))
            conflicts.append({"key": key, "path": path, "reason": reason,
                              "expected_sha": expected_sha, "actual_sha": actual_sha})
    return conflicts


def _materialized_anchor_conflicts(dest, host, profile, core_renders, codex_skill_scope=None):
    """Bind the exact base snapshot read by plan_materialize to the current shipped render."""
    anchors = core_renders if isinstance(core_renders, dict) else {}
    conflicts = []
    for kind, asset_id, path in overlay_materialize.render_targets(
            dest, host, codex_skill_scope):
        key = overlay_materialize.anchor_key(host, kind, asset_id)
        expected, expected_error = _core_render_expected_base(host, kind, asset_id, profile)
        expected_sha = _sha256_text(expected) if expected is not None else "unavailable"
        path_issue = _core_render_path_issue(dest, path)
        if expected_error or path_issue:
            reason, actual_sha = (path_issue if path_issue else (expected_error, "unavailable"))
            conflicts.append({"key": key, "path": path, "reason": reason,
                              "expected_sha": expected_sha, "actual_sha": actual_sha})
            continue
        anchor = anchors.get(key)
        actual_sha = anchor.get("base_sha256") if isinstance(anchor, dict) else "unavailable"
        if actual_sha != expected_sha:
            reason = (Diagnostic("install.materialization_anchor_missing")
                      if actual_sha == "unavailable" else
                      Diagnostic("install.materialization_base_mismatch"))
            conflicts.append({"key": key, "path": path, "reason": reason,
                              "expected_sha": expected_sha, "actual_sha": actual_sha})
    return conflicts


def _print_core_trust_conflicts(dest, conflicts, language=None):
    print(tr(language, 'cli.install.msg02'), file=sys.stderr)
    for item in sorted(conflicts, key=lambda value: (value["key"], value["path"])):
        print(f"  - [{item['key']}] {os.path.relpath(item['path'], dest)}", file=sys.stderr)
        print(f"      reason: {render_issue(language, item['reason'])}", file=sys.stderr)
        print(f"      expected_sha256: {item['expected_sha']}", file=sys.stderr)
        print(f"      actual_sha256:   {item['actual_sha']}", file=sys.stderr)
    print(tr(language, 'cli.install.msg03'), file=sys.stderr)
    print(tr(language, 'cli.install.msg04'),
          file=sys.stderr)
    print(tr(language, 'cli.install.msg05'), file=sys.stderr)
    print(tr(language, 'cli.install.msg06'), file=sys.stderr)


def _cleanup_blocked_core_renders(dest, host, codex_skill_scope=None, language=None):
    """Remove safely identifiable legacy blocked blocks before non-force install preflights."""
    plans, errors = overlay_materialize.plan_blocked_cleanup(
        dest, host, path_guard=lambda path: _core_render_path_issue(dest, path),
        codex_skill_scope=codex_skill_scope)
    changed = overlay_materialize.apply_materialization(plans)
    for path in sorted(changed):
        print(tr(language, 'cli.install.msg07', os_path=os.path.relpath(path, dest)))
    for path, message in errors:
        print(tr(language, 'cli.install.msg08', os_path=os.path.relpath(path, dest),
                 message=render_issue(language, message)), file=sys.stderr)
    if errors:
        print(tr(language, 'cli.install.msg09'),
              file=sys.stderr)
    return errors


def _onboarding_text(host, skill_scope):
    if host == "claude":
        detail = (
            "Claude CORE skills are repository-local under `.claude/skills` and can be committed with the project.\n"
            "A teammate still installs the SAGE CLI/runtime separately to run `sage`, `sage-hook`, hooks, and validation."
        )
    elif skill_scope == "project-local":
        detail = (
            "Project-local CORE skills live under `.codex/skills`. When these files are committed, a teammate can "
            "discover the prompts after cloning the repository.\n"
            "This repository content does not install the `sage` or `sage-hook` executable. Each teammate still "
            "installs the SAGE CLI/runtime separately and runs `sage doctor`."
        )
    elif skill_scope == "global":
        detail = (
            "Global CORE skills live under the effective `$CODEX_HOME/skills` and are not carried by the repository.\n"
            "The SAGE CLI/runtime and CORE skill install are per-user: each teammate installs the CLI, then runs "
            "`sage install --host codex --skill-scope global --dest <repo>`."
        )
    else:
        detail = (
            "CORE skill installation is disabled for this CI/sandbox receipt. The repository router may explain the "
            "workflow, but no `$sage-*` discovery surface is provisioned."
        )
    selected = skill_scope if host == "codex" else "project-local"
    return (
        "# SAGE Team Onboarding\n\n"
        f"Host: `{host}`\n"
        f"Selected Codex CORE skill scope: `{selected}`\n\n"
        f"{detail}\n\n"
        "Run `sage-init` only for the first shared+local bootstrap. When the shared profile is already bootstrapped, "
        "each teammate runs `sage-init-local` to create only `sage/project-profile.local.yaml`.\n\n"
        "Do not keep duplicate global, `.codex/skills`, and `.agents/skills` copies of the same `$sage-*` CORE skill. "
        "Run `sage doctor` after installation; the manifest receipt records intent, while host precedence is treated "
        "as ambiguous when duplicate copies exist.\n"
    )


def _install_preconditions(dest, args, manifest_path):
    """Capture trust-relevant inputs used across preflight and apply."""
    paths = {
        os.path.join(dest, "sage", "project-profile.json"),
        os.path.join(dest, "sage", "project-profile.yaml"),
        manifest_path,
        os.path.join(dest, ".gitignore"),
    }
    recursive = {os.path.join(dest, "sage", "asset_overrides")}
    paths.update(recursive)

    skill_scope = getattr(args, "_sage_skill_scope", None)
    render_paths = [path for _kind, _asset_id, path
                    in overlay_materialize.render_targets(dest, args.host, skill_scope)]
    paths.update(render_paths)
    root = os.path.abspath(dest)
    for target in render_paths:
        cursor = os.path.dirname(os.path.abspath(target))
        while cursor and os.path.commonpath((root, cursor)) == root:
            if os.path.lexists(cursor):
                paths.add(cursor)
            if cursor == root:
                break
            cursor = os.path.dirname(cursor)

    if args.host == "codex" and skill_scope == "global":
        codex_home = os.path.dirname(_codex_skills_root())
        for ancestor in (codex_home, _codex_skills_root()):
            if os.path.lexists(ancestor):
                paths.add(ancestor)
        for skill_id in core_skill_ids():
            paths.add(_codex_global_skill_path(skill_id))
        for legacy in _LEGACY_CORE_SKILLS:
            legacy_path = os.path.join(_codex_skills_root(), legacy)
            paths.add(legacy_path)
            if os.path.isdir(legacy_path) and not os.path.islink(legacy_path):
                recursive.add(legacy_path)
    elif args.host == "codex" and skill_scope == "project-local":
        local_root = os.path.join(dest, ".codex", "skills")
        if os.path.lexists(local_root):
            paths.add(local_root)
        for skill_id in core_skill_ids():
            paths.add(_codex_project_skill_path(dest, skill_id))
        for legacy in _LEGACY_CORE_SKILLS:
            legacy_path = os.path.join(local_root, legacy)
            paths.add(legacy_path)
            if os.path.isdir(legacy_path) and not os.path.islink(legacy_path):
                recursive.add(legacy_path)
    elif args.host == "claude":
        for legacy in _LEGACY_CORE_SKILLS:
            legacy_path = os.path.join(dest, ".claude", "skills", legacy)
            paths.add(legacy_path)
            if os.path.isdir(legacy_path) and not os.path.islink(legacy_path):
                recursive.add(legacy_path)
    return _tx.capture_paths(paths, recursive=recursive)


def run(args) -> int:
    """Acquire every write-surface lock and commit or roll back the install."""
    # 엔진 저장소에 자기 자신을 설치하면 프로필 없는 루트에 게이트 hook 이 등록돼 SAGE 자신의
    # 게이트가 SAGE 개발을 막는다(2026-06-17·07-24 두 번 발생). --dest 기본값이 cwd 라 엔진
    # 저장소에서 무인자 실행이 곧 이 사고다. 예외 플래그를 두지 않는다 — 플래그가 곧 우회로다.
    if _resources.is_engine_source_tree(args.dest):
        print(tr(language_of(args), 'cli.install.msg10'), file=sys.stderr)
        return 2
    skill_scope, scope_error = _resolve_skill_scope(args, language_of(args))
    if scope_error:
        print(f"[sage install] TOOL ERROR: {scope_error}", file=sys.stderr)
        return 2
    args._sage_skill_scope = skill_scope
    lock_targets = [os.path.abspath(args.dest)]
    if args.host == "codex" and skill_scope == "global":
        lock_targets.append(_codex_skills_root())
    locks_by_path = {}
    for target in lock_targets:
        candidate = _tx.DestinationLock(target)
        locks_by_path.setdefault(candidate.path, candidate)
    locks = sorted(locks_by_path.values(), key=lambda item: item.path)
    acquired = []
    transaction = None
    try:
        for lock in locks:
            lock.acquire()
            acquired.append(lock)
    except (_tx.InstallBusyError, _tx.InstallDriftError) as exc:
        print(tr(language_of(args), 'cli.install.msg11',
                 exc=_exception_text(language_of(args), exc)), file=sys.stderr)
        for lock in reversed(acquired):
            lock.release()
        delattr(args, "_sage_skill_scope")
        return 1
    try:
        rc = _run_locked(args)
        transaction = getattr(args, "_sage_install_transaction", None)
        if transaction is not None and rc != 0 and not transaction.committed:
            rollback_errors = transaction.rollback()
            for message in rollback_errors:
                print(tr(language_of(args), 'cli.install.msg12', message=message), file=sys.stderr)
        return rc
    except BaseException as exc:
        transaction = getattr(args, "_sage_install_transaction", transaction)
        rollback_errors = (transaction.rollback()
                           if transaction is not None and not transaction.committed else [])
        print(tr(language_of(args), 'cli.install.msg13', arg=type(exc).__name__, exc=exc), file=sys.stderr)
        if rollback_errors:
            for message in rollback_errors:
                print(tr(language_of(args), 'cli.install.msg14', message=message), file=sys.stderr)
        elif transaction is not None and transaction.committed:
            print(tr(language_of(args), 'cli.install.msg15'),
                  file=sys.stderr)
        elif transaction is not None:
            print(tr(language_of(args), 'cli.install.msg16'), file=sys.stderr)
        else:
            print(tr(language_of(args), 'cli.install.msg17'), file=sys.stderr)
        if not isinstance(exc, Exception):
            raise
        return 1
    finally:
        if hasattr(args, "_sage_install_transaction"):
            delattr(args, "_sage_install_transaction")
        if hasattr(args, "_sage_skill_scope"):
            delattr(args, "_sage_skill_scope")
        for lock in reversed(acquired):
            lock.release()


def _run_locked(args) -> int:
    dest = os.path.abspath(args.dest)
    skill_scope = getattr(args, "_sage_skill_scope", "project-local")
    created, skipped = [], []
    pruned = []                 # 은퇴한 CORE skill 잔존 사본 정리 결과(5d)
    wrapper = "CLAUDE.md" if args.host == "claude" else "CODEX.md"
    core = _resources.core_dir()
    fw = os.path.join(core, "framework")
    if args.host == "codex" and skill_scope == "project-local":
        for skill_id in core_skill_ids():
            path = _codex_project_skill_path(dest, skill_id)
            issue = _core_render_path_issue(dest, path)
            if issue:
                print(tr(language_of(args), 'cli.install.msg18', path=path), file=sys.stderr)
                print(f"   reason: {issue[0]}", file=sys.stderr)
                return 1
    # FB12 migration safety: non-force install은 이후 어느 preflight가 실패하더라도 과거
    # gate-bearing managed block을 실행 상태로 남기지 않는다. profile/manifest를 읽기 전에
    # parent/leaf path를 검증하고 exact SAGE marker만 제거한다. force install은 정본 copy가
    # 렌더 자체를 원자 교체하므로 이 pre-step이 없다.
    if not args.force:
        if _cleanup_blocked_core_renders(dest, args.host, skill_scope, language_of(args)):
            return 1
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
            print(f"❌ {render_issue(language_of(args), _m)}", file=sys.stderr)
        print(tr(language_of(args), 'cli.install.msg19'),
              file=sys.stderr)
        return 1

    manifest_path = os.path.join(dest, "docs", "sage_harness", ".manifest.json")
    existing_manifest = _load_manifest(dest)
    manifest_issue = (_manifest_structure_issue(existing_manifest, language_of(args))
                      if existing_manifest is not None
                      else tr(language_of(args), "cli.install.manifest_unreadable_or_not_mapping"))
    if os.path.lexists(manifest_path) and manifest_issue and not args.force:
        print(tr(language_of(args), 'cli.install.msg20', manifest_path=manifest_path), file=sys.stderr)
        print(f"   reason: {manifest_issue}", file=sys.stderr)
        print(tr(language_of(args), 'cli.install.msg21'), file=sys.stderr)
        print(tr(language_of(args), 'cli.install.msg22'), file=sys.stderr)
        return 1

    trust_conflicts = _core_trust_conflicts(
        dest, args.host, agent_profile, existing_manifest, allow_base_replacement=args.force,
        codex_skill_scope=skill_scope)
    if trust_conflicts:
        _print_core_trust_conflicts(dest, trust_conflicts, language_of(args))
        return 1

    overlay_preflight_errors = overlay_materialize.preflight_overlays(dest, _profile)
    for path, message in overlay_preflight_errors:
        print(tr(language_of(args), 'cli.install.msg23', os_path=os.path.relpath(path, dest),
                 message=render_issue(language_of(args), message)), file=sys.stderr)
    if overlay_preflight_errors:
        print(tr(language_of(args), 'cli.install.msg24'), file=sys.stderr)
        return 1

    preconditions = _install_preconditions(dest, args, manifest_path)
    from sage.build_identity import (describe_content_drift, source_core_content_hash,
                                     source_core_content_snapshot)
    # drift 판정은 기존과 똑같이 집계 해시 하나로 한다. 논리경로 맵은 오직 진단용이라
    # 실패해도 판정에 영향을 주지 않는다.
    preflight_source_hash = source_core_content_hash()
    preflight_source_files = source_core_content_snapshot()[1]

    def _drift_detail():
        """drift 시 어느 논리경로가 달라졌는지. 진단만 바꾸고 검사는 그대로 fail-closed 다."""
        try:
            detail = describe_content_drift(preflight_source_files,
                                            source_core_content_snapshot()[1])
        except OSError as exc:   # 인벤토리 재수집 실패까지 원래 오류를 가리지 않게
            # 이 함수의 결과는 항상 영어 고정 raw 문자열(InstallDriftError 의 진단 없는 메시지)로
            # 들어간다 — 감싸는 문장 자체가 언어 배선이 없어 이 조각만 번역하면 오히려 섞인다.
            detail = f"(failed to collect changed paths: {exc})"
        return f" — {detail}" if detail else ""

    confirmed_profile, confirmed_profile_error = _installed_profile(dest)
    confirmed_manifest = _load_manifest(dest)
    confirmed_overlay_errors = overlay_materialize.preflight_overlays(dest, confirmed_profile)
    confirmed_trust_conflicts = _core_trust_conflicts(
        dest, args.host, confirmed_profile if args.host == "claude" else {}, confirmed_manifest,
        allow_base_replacement=args.force, codex_skill_scope=skill_scope)
    if (confirmed_profile_error or confirmed_profile != _profile
            or confirmed_manifest != existing_manifest
            or confirmed_overlay_errors or confirmed_trust_conflicts):
        raise _tx.InstallDriftError(
            "install inputs changed while establishing the preflight snapshot")
    write_roots = [dest]
    if args.host == "codex" and getattr(args, "_sage_skill_scope", None) == "global":
        write_roots.append(os.path.dirname(_codex_skills_root()))
    transaction = _tx.InstallTransaction(expected=preconditions, write_roots=write_roots)
    transaction.verify_unconsumed()
    args._sage_install_transaction = transaction

    # 1. profile — 인스턴스 커스터마이즈 SSOT(위험분류/pdca/team 등). F5: 엔진 자산이 아니므로
    #    --force(엔진 업그레이드)여도 절대 덮어쓰지 않는다 — 덮으면 프로젝트 값 소실로 클린 업그레이드 불가.
    #    create-only: 새 설치 때만 빈 스키마 배치. reset 필요 시 사용자가 수동 삭제 후 재설치.
    prof_dst = os.path.join(dest, "sage", "project-profile.yaml")
    existing_profile_path = next((os.path.join(dest, "sage", name)
                                  for name in ("project-profile.yaml", "project-profile.json")
                                  if os.path.lexists(os.path.join(dest, "sage", name))), None)
    if existing_profile_path is not None:
        print(tr(language_of(args), 'cli.install.msg25', os_path=os.path.relpath(existing_profile_path, dest)))
    else:
        _write(prof_dst, _profile_with_host(args.host, args.prefix, language_of(args)), args.force, created,
               skipped, transaction=transaction)
    _write_local_profile_gitignore(dest, created, skipped, transaction)

    # 2. framework 템플릿(중립): AGENT_GUIDE, {wrapper}, verification-protocol, verify-changes.sh, docs/agent/*
    _copy_file(os.path.join(fw, "AGENT_GUIDE.md"), os.path.join(dest, "AGENT_GUIDE.md"), args.force,
               created, skipped, transaction=transaction)
    _copy_file(os.path.join(fw, wrapper), os.path.join(dest, wrapper), args.force, created, skipped,
               transaction=transaction)
    _copy_file(os.path.join(fw, "verification-protocol.md"),
               os.path.join(dest, "verification-protocol.md"), args.force, created, skipped,
               transaction=transaction)
    verify_dst = os.path.join(dest, "scripts", "verify-changes.sh")
    project_local_script = ((_profile.get("verification") or {}).get("project_local_script")
                            if isinstance(_profile.get("verification"), dict) else None)
    if project_local_script == "scripts/verify-changes.sh" and os.path.isfile(verify_dst):
        print(tr(language_of(args), 'cli.install.msg26'))
        skipped.append(verify_dst)
    else:
        _copy_file(os.path.join(fw, "scripts", "verify-changes.sh"),
                   verify_dst, args.force, created, skipped, transaction=transaction)
    # tree 째 복사하지 않고 정본 목록으로 배치한다. uninstall 이 같은 함수를 보므로, 배치한
    # 것과 지우는 것이 같은 목록이라는 사실이 코드에서 성립한다 — 대조 테스트가 아니라 구조로.
    for _agent_doc in _managed.framework_agent_docs(fw):
        _agent_src = os.path.join(fw, "docs", "agent", _agent_doc)
        if os.path.isfile(_agent_src):
            _copy_file(_agent_src, os.path.join(dest, "docs", "agent", _agent_doc), args.force,
                       created, skipped, transaction=transaction)

    # 2b. 대화형 부트스트랩 트리거 — profile 을 대화로 채우는 설계상 진입점(런타임별 발견 메커니즘 상이).
    agents_md_collision = False
    bootstrap_skill_status = []  # [(id, (status, dst))] — full/local init 배치 결과
    core_skill_status = []      # [(id, (status, dst))] — selected Codex scope의 CORE skill 결과(5c)
    _write(os.path.join(dest, "docs", "agent", "sage-onboarding.md"),
           _onboarding_text(args.host, skill_scope), True, created, skipped,
           transaction=transaction)
    if args.host == "claude":
        # claude: repo .claude/skills/ 자동발견 → full/local init 스킬 배치.
        for skill_id in _CORE_BOOTSTRAP_SKILLS:
            _copy_tree(os.path.join(fw, ".claude", "skills", skill_id),
                       os.path.join(dest, ".claude", "skills", skill_id), args.force,
                       created, skipped, transaction=transaction)
        # claude: CORE 6인 에이전트 렌더 → .claude/agents/ (Claude Code 자동발견 경로)
        _copy_agent_renders(os.path.join(fw, ".claude", "agents"),
                            os.path.join(dest, ".claude", "agents"), agent_profile,
                            args.force, created, skipped, transaction=transaction)
    else:
        # codex: ① 사용자가 선택한 global 또는 project-local discovery surface에 $sage-init 설치.
        #           deprecated --no-global-skill은 CI/샌드박스 호환을 위해 disabled receipt로만 보존한다.
        #        ② codex 가 auto-read 하는 AGENTS.md 라우터(세션 시작 시 부트스트랩 안내, CODEX.md 는
        #           codex auto-read 아님). create-only: 기존 AGENTS.md 보존+경고(codex 협의 R4).
        for skill_id in _CORE_BOOTSTRAP_SKILLS:
            skill_src_md = _core_skill_source(skill_id)
            if skill_scope == "global":
                status = _install_codex_global_skill(
                    skill_src_md, args.force, skill_id=skill_id, transaction=transaction)
            elif skill_scope == "project-local":
                status = _install_codex_project_skill(
                    dest, skill_src_md, args.force, skill_id=skill_id, transaction=transaction)
            else:
                status = ("disabled", None)
            bootstrap_skill_status.append((skill_id, status))
        agents_dst = os.path.join(dest, "AGENTS.md")
        if os.path.exists(agents_dst) and not args.force:
            agents_md_collision = True
        else:
            _copy_file(os.path.join(fw, "AGENTS.md"), agents_dst, args.force, created, skipped,
                       transaction=transaction)
        # codex: CORE 6인 에이전트 렌더 → repo .codex/agents/ (claude host 가 .claude/agents/ 받듯
        #   codex host 도 자기 렌더를 받음 — 리소스 생성 시 codex 누락 금지, 사용자 지침).
        #   codex 는 에이전트 네이티브 자동발견이 없으나 SAGE 설계상 .codex/agents/<id>.md 가 자산 정본
        #   (write-guard·reverse_extract·CODEX.md). codex AI 는 AGENTS.md 라우팅으로 역할 정의를 참조.
        #   claude 렌더와 동일 소스 재사용(skill 전역배포와 같은 단일소스 패턴).
        _copy_tree(os.path.join(fw, ".claude", "agents"),
                   os.path.join(dest, ".codex", "agents"), args.force, created, skipped,
                   transaction=transaction)

    # 3. CORE hook spec(중립 7종) → docs/sage_harness/hooks/
    specs = _resources.hook_specs_dir()
    for hid, _form in _CORE_HOOKS:
        _copy_file(os.path.join(specs, f"{hid}.md"),
                   os.path.join(dest, "docs", "sage_harness", "hooks", f"{hid}.md"), args.force,
                   created, skipped, transaction=transaction)

    # 4. CORE hook 정본(core+adapter+strategy) → scripts/sage_harness/hooks/ (도메인값 0)
    if args.force:
        _prune_legacy_native_write_guard(dest, pruned, transaction=transaction)
    _copy_tree(_resources.hooks_src_dir(), os.path.join(dest, "scripts", "sage_harness", "hooks"),
               args.force, created, skipped, transaction=transaction)

    # 5. CORE roster agent spec(중립 6인) → docs/sage_harness/agents/
    for aid in _CORE_AGENTS:
        _copy_file(os.path.join(core, "agents", f"{aid}.md"),
                   os.path.join(dest, "docs", "sage_harness", "agents", f"{aid}.md"), args.force,
                   created, skipped, transaction=transaction)

    # 5b. CORE skill 중립 spec → docs/sage_harness/skills/ (host 무관 — CORE agent spec 과 대칭).
    #     CORE 부트스트랩 자산이라 CORE agent spec 과 동일하게 manifest 비추적(reference spec).
    #     manifest 추적 skill(spec+claims+render hash)은 generate/extract 흐름이 소유한다.
    #     부트스트랩 skill 도 같은 정본을 갖는다 — 렌더만 배포하면 그 두 개만 canonical source 가
    #     없어 영어 의미 정본 대조에서 빠진다.
    for sid in core_skill_ids():
        _copy_file(os.path.join(core, "skills", f"{sid}.md"),
                   os.path.join(dest, "docs", "sage_harness", "skills", f"{sid}.md"), args.force,
                   created, skipped, transaction=transaction)

    # 5c. CORE skill 렌더 — claude는 repo local, codex는 명시적으로 선택한 scope를 사용한다.
    if args.host == "claude":
        for sid in _CORE_SKILLS:
            _copy_tree(os.path.join(fw, ".claude", "skills", sid),
                       os.path.join(dest, ".claude", "skills", sid), args.force, created, skipped,
                       transaction=transaction)
    elif skill_scope in ("global", "project-local"):
        for sid in _CORE_SKILLS:
            src_md = os.path.join(fw, ".claude", "skills", sid, "SKILL.md")
            installer = (_install_codex_global_skill if skill_scope == "global"
                         else lambda src, force, skill_id, transaction: _install_codex_project_skill(
                             dest, src, force, skill_id=skill_id, transaction=transaction))
            core_skill_status.append((sid, installer(
                src_md, args.force, skill_id=sid, transaction=transaction)))

    # 5d. 은퇴한 CORE skill 잔존 사본 정리 — 옛 이름이 새 이름과 함께 남아 호출되는 혼선 방지.
    #     설치한 host 의 발견 경로만 정리(claude=repo .claude/skills, codex=전역 $CODEX_HOME/skills).
    for legacy in _LEGACY_CORE_SKILLS:
        if args.host == "claude":
            _prune_legacy_skill(os.path.join(dest, ".claude", "skills", legacy), pruned,
                                transaction=transaction)
        elif skill_scope in ("global", "project-local"):
            skill_root = (_codex_skills_root() if skill_scope == "global"
                          else os.path.join(dest, ".codex", "skills"))
            _prune_legacy_skill(os.path.join(skill_root, legacy), pruned,
                                transaction=transaction)

    # 5e. 오버레이 물리화 + core_renders 앵커 — CORE 렌더 base 에 (a)/(b) 오버레이 블록을 물리 삽입하고
    #     (c)/미분류는 블록 없이 base 앵커만 기록. install·sync·L1·validate 가 같은 로직(overlay_materialize)을 경유.
    core_renders, materialization_plans, overlay_errors = overlay_materialize.plan_materialize(
        dest, args.host, skill_scope)
    for p, msg in overlay_errors:
        print(tr(language_of(args), 'cli.install.msg27', os_path=os.path.relpath(p, dest),
                 msg=render_issue(language_of(args), msg)), file=sys.stderr)
    if overlay_errors:
        print(tr(language_of(args), 'cli.install.msg28'), file=sys.stderr)
        return 1
    anchor_conflicts = _materialized_anchor_conflicts(
        dest, args.host, agent_profile, core_renders, skill_scope)
    if anchor_conflicts:
        _print_core_trust_conflicts(dest, anchor_conflicts, language_of(args))
        return 1
    transaction.verify_unconsumed()
    overlay_changed = overlay_materialize.apply_materialization(
        materialization_plans,
        writer=lambda path, text: _atomic_write(path, text, transaction=transaction))
    for p in sorted(overlay_changed):
        print(tr(language_of(args), 'cli.install.msg29', os_path=os.path.relpath(p, dest)))

    # 6. manifest (CORE hook 등록 — generate 가 hash 스탬프 + core_renders 앵커). --force 재설치는 기존
    #    manifest 의 인스턴스 등록 자산(mcps/agents/skills)을 보존하고 CORE hook·core_renders 만 리셋.
    next_manifest = _manifest(args.host, existing_manifest, core_renders,
                              skill_scope=skill_scope)
    if next_manifest.get("source_core_content_hash") != preflight_source_hash:
        raise _tx.InstallDriftError(
            "SAGE source resources changed during install" + _drift_detail())
    _write(manifest_path,
           json.dumps(next_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
           True, created, skipped, transaction=transaction)

    # 7. spec 템플릿(사람 작성 참고) + schema(validate 참조)
    templates = _resources.templates_dir()
    for t in ("agent.spec.md", "hook.spec.md", "skill.spec.md", "claims.yml"):
        _copy_file(os.path.join(templates, t), os.path.join(dest, "sage", "templates", t), args.force,
                   created, skipped, transaction=transaction)
    # manifest + profile 스키마 모두 vendor — profile 스키마는 project-profile 구조검증과
    # 오타 키 방어가 번들 폴백에 의존하지 않고 프로젝트 안에서 자립하도록.
    for s in ("manifest.schema.json", "profile.schema.json", "profile.local.schema.json"):
        _copy_file(os.path.join(_resources.schema_dir(), s),
                   os.path.join(dest, "schema", s), args.force, created, skipped,
                   transaction=transaction)

    if source_core_content_hash() != preflight_source_hash:
        raise _tx.InstallDriftError(
            "SAGE source resources changed before install commit" + _drift_detail())
    transaction.verify_unconsumed()
    transaction.verify_outputs()
    cleanup_errors = transaction.commit()
    for message in cleanup_errors:
        print(tr(language_of(args), 'cli.install.msg30', message=message), file=sys.stderr)
    _warn_if_retro_audit_tracked(dest, language_of(args))

    # 보고
    print(f"== sage install (host={args.host}, prefix={args.prefix}) → {dest} ==")
    print(tr(language_of(args), 'cli.install.msg31', count=len(created), count2=len(_CORE_HOOKS), count3=len(_CORE_AGENTS), count4=len(_CORE_AGENTS), count5=len(core_skill_ids())))
    for p in sorted(created):
        print(f"  + {os.path.relpath(p, dest)}")
    if skipped:
        print(tr(language_of(args), 'cli.install.msg32', count=len(skipped)))
        for p in sorted(skipped):
            print(f"  = {os.path.relpath(p, dest)}")
    if pruned:
        print(tr(language_of(args), 'cli.install.msg33', count=len(pruned)))
        for p in sorted(pruned):
            print(f"  - {p}")
    # --force(업그레이드) 재설치는 CORE 자산을 갱신하므로, 인스턴스가 등록한 kind(mcp/agent/skill)
    #    가 manifest 와 어긋나지 않았는지 설치 직후 바로 확인하도록 안내한다(현재는 사람이 별도 validate
    #    를 돌려야만 orphan drift 를 발견).
    if args.force:
        print("")
        print(tr(language_of(args), 'cli.install.msg34'))
        print(tr(language_of(args), 'cli.install.msg35'))
        print("         sage validate --check --kind all")

    # 다음 단계 안내 — 설계상 진입점은 "AI 대화로 profile 채우기"다(직접 편집 아님).
    # profile 미부트스트랩(project.name 빈값) 상태에선 sage generate 가 BLOCK 된다(강제 게이트).
    runner = "claude" if args.host == "claude" else "codex"
    init_cmd = "/sage-init" if args.host == "claude" else "$sage-init"
    gen_cmd = "sage generate --kind hook --write" + ("" if args.host == "claude" else " --target codex")
    print("")
    print(tr(language_of(args), 'cli.install.msg36'))
    print(tr(language_of(args), 'cli.install.msg37', runner=runner, init_cmd=init_cmd))
    print(tr(language_of(args), 'cli.install.msg38'))
    print(tr(language_of(args), 'cli.install.msg39', gen_cmd=gen_cmd))
    print("")
    print(tr(language_of(args), 'cli.install.msg40'))

    if args.host == "claude":
        # CORE 렌더(skill/agent)는 create-only 라 --force 없이는 기존 사본이 skip 된다 →
        # 번들과 달라져도 조용히 stale 로 남을 수 있음. drift 확인 진입점을 안내(codex 전역 요약과 대칭).
        skipped_core = [p for p in skipped
                        if os.sep + ".claude" + os.sep in p and (os.sep + "skills" + os.sep in p
                                                                 or os.sep + "agents" + os.sep in p)]
        if skipped_core and not args.force:
            print("")
            print(tr(language_of(args), 'cli.install.msg41', count=len(skipped_core)))
    if args.host == "codex":
        _print_codex_skill_summary(bootstrap_skill_status, core_skill_status,
                                   skill_scope, language_of(args))
        if agents_md_collision:
            print("")
            print(tr(language_of(args), 'cli.install.msg42'))
            print(tr(language_of(args), 'cli.install.msg43'))
    return 0


def _print_codex_skill_summary(bootstrap_skill_status, core_skill_status, skill_scope, language=None):
    """Summarize the selected Codex CORE skill discovery surface."""
    if (skill_scope == "disabled" and not core_skill_status
            and all(status[0] == "disabled" for _skill_id, status in bootstrap_skill_status)):
        print("")
        print(tr(language, 'cli.install.msg44'))
        return

    # (id, status) 전체 수집 — full/local init + CORE 스킬.
    entries = [(sid, status[0]) for sid, status in bootstrap_skill_status]
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
    scope_label = tr(language, "cli.install.scope_global" if skill_scope == "global"
                     else "cli.install.scope_project_local")
    print(tr(language, 'cli.install.msg45', scope_label=scope_label, total=total, ok=ok) + (tr(language, 'cli.install.stale_suffix', stale=stale) if stale else "") + (tr(language, "cli.install.failed_suffix", err=err) if err else ""))
    if stale:
        stale_ids = ", ".join(f"${sid}" for sid, st in entries if st == "stale")
        print(tr(language, 'cli.install.msg46', stale_ids=stale_ids))
        print(tr(language, 'cli.install.msg47', skill_scope=skill_scope))
    if err:
        err_ids = ", ".join(f"${sid}" for sid, st in entries if st in ("error", "missing"))
        print(tr(language, 'cli.install.msg48', err_ids=err_ids))
