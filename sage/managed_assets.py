"""SAGE 가 설치·제거하는 자산의 **정본 roster**.

## 왜 이 모듈이 있는가

같은 목록이 두 곳에 있었다. `install._CORE_*` 가 배치할 것을 말하고 `overlay_classify.CORE_IDS`
가 오버레이 자격을 말했는데, 둘은 같은 자산을 가리키면서 서로를 참조하지 않았다. 지금까지는
대조 테스트가 둘의 어긋남을 잡아 줬다 — 즉 **검사가 없으면 갈라지는 구조**였고, 실제로 은퇴한
skill 이름 하나가 한쪽에만 남아 있었다.

uninstall 이 세 번째 소비자로 들어오면 그 구조는 버티지 못한다. 지우는 쪽이 배치하는 쪽보다
좁으면 자산이 남고, 넓으면 사용자 파일을 지운다. 둘 다 조용하다.

그래서 목록을 여기 하나로 옮긴다. **통합은 세 번째 목록을 만드는 것이 아니라 두 개를 하나로
줄이는 것**이므로, 이 모듈은 값을 새로 쓰지 않고 기존 값을 그대로 들고 온다. 소비자는 여기를
참조만 한다.

## 무엇을 알고 무엇을 모르는가

이 모듈은 **이름과 경로 규칙**만 안다. 파일이 실제로 있는지, 내용이 무엇인지, 지워도 되는지는
모른다 — 그 판정은 소유권 증명을 가진 쪽(`uninstall_plan`)의 일이다. 여기서 경로를 만든다는
것이 그 경로를 지워도 된다는 뜻이 아니다.
"""
import os

# --- roster 정본 -------------------------------------------------------------

# 중립 6인. 도메인 값이 아니라 framework 메타다.
CORE_AGENTS = ("leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker")

# 은퇴한 agent 이름. skill 쪽 `LEGACY_CORE_SKILLS` 와 같은 자리이며, **이름이 바뀌면 옛 이름을
# 여기 추가한다** — 여기 없으면 옛 렌더가 host agents 디렉터리에 영구히 남는다. 지금은 rename
# 이력이 없어 비어 있지만, 자리를 비워 두는 것과 자리가 없는 것은 다르다.
LEGACY_CORE_AGENTS = ()

# skill 3분할: sage-cycle(00~06 우산) → sage-plan(00~02 기획) → sage-team(03~06 개발).
# sage-asset-override: CORE 렌더 직접수정을 대체하는 오버레이 저작 경로.
# sage-feedback: 완료 사이클 코드의 의문 마커 해소 — 사이클 밖 독립 실행.
CORE_SKILLS = ("sage-cycle", "sage-plan", "sage-team", "sage-review", "sage-asset",
               "sage-profile-modify", "sage-asset-override", "sage-feedback",
               "sage-cycle-fast", "sage-plan-fast", "sage-team-fast")

# 부트스트랩 skill 은 설치 직후 profile 을 세우는 용도라 CORE 목록과 수명이 다르다. 그래서
# 목록을 합치지 않고 나란히 둔다 — 합치면 "부트스트랩만" 다뤄야 하는 자리에서 다시 갈라진다.
CORE_BOOTSTRAP_SKILLS = ("sage-init", "sage-init-local")

# 은퇴한 CORE skill 이름. install 은 잔존 사본을 정리(rename 수렴)하고 uninstall 은 삭제
# 후보에 넣는다. **이름이 바뀌면 옛 이름을 여기 추가한다** — 여기 없으면 옛 사본이 영구히 남는다.
# sage-pdca-start → sage-plan 3분할 rename, pdca-start 는 그 이전 rename 이다.
LEGACY_CORE_SKILLS = ("pdca-start", "sage-pdca-start")

# SAGE 가 hand-ship 하는 모든 CORE skill `SKILL.md` 에 들어 있는 마커. 공유 공간(codex 전역)에서
# 동명의 사용자 skill 을 오삭제하지 않기 위한 소유권 근거다.
LEGACY_SKILL_SIGNATURE = "CORE framework bootstrap asset"

CORE_HOOKS = (
    ("capture-declared-risk", "core_adapter"),
    ("post-tool-logger", "core_adapter"),
    ("pre-implementation-gate", "core_adapter"),
    ("pre-phase4-checklist-gate", "core_adapter"),
    ("session-start-snapshot", "core_adapter"),
    ("stop-compliance-report", "core_adapter"),
    ("generated-artifact-write-guard", "core_adapter"),
)

# 최상위 공유 문서. **설치 전 소유권을 증명할 수 없어 uninstall 이 절대 지우지 않는 넷**이다.
# 여기 이름이 있다는 것은 SAGE 가 쓴다는 뜻이지 SAGE 가 소유한다는 뜻이 아니다.
FRAMEWORK_DOCS = ("AGENT_GUIDE", "CLAUDE", "CODEX", "AGENTS")


def all_skill_ids():
    """CORE + 부트스트랩. 오버레이 자격과 설치 배치가 같은 범위를 쓴다."""
    return tuple(CORE_SKILLS) + tuple(CORE_BOOTSTRAP_SKILLS)


def core_ids():
    """`overlay_classify.CORE_IDS` 가 소비하는 형태.

    frozenset 으로 돌려주는 이유는 소비자가 실수로 목록을 늘리지 못하게 하기 위해서다. 늘려야
    하면 이 모듈을 고쳐야 하고, 그러면 install·uninstall 이 함께 따라온다.
    """
    return {
        "agents": frozenset(CORE_AGENTS),
        "skills": frozenset(all_skill_ids()),
        "framework": frozenset(FRAMEWORK_DOCS),
    }


# --- 경로 규칙 ---------------------------------------------------------------

def codex_global_skills_root(environ=None):
    """Codex **전역** skill root = `$CODEX_HOME/skills` (없으면 `~/.codex/skills`).

    project-local scope 는 대상 저장소의 `.codex/skills` 이고 이것과 무관하다. 한쪽에서 다른
    쪽을 유추하면 scope 격리가 깨지므로 호출자는 둘을 절대 섞지 않는다.
    """
    env = os.environ if environ is None else environ
    base = env.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(base, "skills")


def codex_global_skill_dir(skill_id, environ=None):
    return os.path.join(codex_global_skills_root(environ), skill_id)


def project_skill_dir(dest, host, skill_id):
    """host 별 프로젝트 skill 디렉터리. claude 는 `.claude/skills`, codex 는 `.codex/skills`."""
    host_dir = ".claude" if host == "claude" else ".codex"
    return os.path.join(os.path.abspath(dest), host_dir, "skills", skill_id)


def host_agent_render(dest, host, agent_id):
    """host 가 자동발견하는 agent 렌더 경로. claude 는 `.claude/agents`, codex 는 `.codex/agents`.

    install 이 여기 CORE 6인을 배치하고 manifest `core_renders` 에 `<host>/agents/<id>` 로
    기록한다. 그 기록이 소유권 증명이다.
    """
    host_dir = ".claude" if host == "claude" else ".codex"
    return os.path.join(os.path.abspath(dest), host_dir, "agents", f"{agent_id}.md")


def project_agent_doc(dest, agent_id):
    return os.path.join(os.path.abspath(dest), "docs", "sage_harness", "agents", f"{agent_id}.md")


def project_skill_doc(dest, skill_id):
    return os.path.join(os.path.abspath(dest), "docs", "sage_harness", "skills", f"{skill_id}.md")


# SAGE 전용 namespace. 이 넷은 통째로 SAGE 가 만든 것이라 tree 단위로 다룬다 — 안에 사용자
# 파일이 섞일 수 있는 자리는 여기 넣지 않는다.
SAGE_TREES = (
    os.path.join("sage"),
    os.path.join(".sage"),
    os.path.join("docs", "sage_harness"),
    os.path.join("scripts", "sage_harness"),
)


# framework 배포본. SAGE 전용 namespace 밖이지만 install 이 배치한 것이라 manifest 가 소유권을
# 증명한다. 최상위 네 문서(`FRAMEWORK_DOCS`)와 다른 점은 **설치 전 존재 여부를 알 수 있는가**
# 하나다 — 이 파일들은 SAGE 가 만들기 전에는 없던 이름이라 증명이 성립한다.
FRAMEWORK_FILES = (
    "verification-protocol.md",
    os.path.join("scripts", "verify-changes.sh"),
    os.path.join("schema", "manifest.schema.json"),
    os.path.join("schema", "profile.schema.json"),
    os.path.join("schema", "profile.local.schema.json"),
)

# `docs/agent/` 는 SAGE 전용 디렉터리가 **아니다.** 사용자가 자기 문서를 같은 자리에 둘 수 있고,
# 실제로 그러기를 권하는 구조다. 그래서 tree 째로 다루지 않고 **파일 이름 목록**으로 다룬다 —
# install 이 배치한 이름만 후보이고 나머지 sibling 은 이름조차 후보에 오르지 않는다.
FRAMEWORK_AGENT_GENERATED = ("sage-onboarding.md",)

# 처리 뒤 **실제로 비었을 때만** 정리하는 부모들. 여기 없는 부모는 비어도 손대지 않는다.
PRUNABLE_PARENTS = (
    os.path.join("docs", "agent"),
    os.path.join(".claude", "agents"),
    os.path.join(".codex", "agents"),
    "schema",
    "scripts",
    "docs",
    os.path.join(".claude", "skills"),
    os.path.join(".codex", "skills"),
    # host 설정 디렉터리 자체. install 이 없으면 만들므로 **비었을 때만** 되돌린다. 사용자
    # settings·자기 agent 가 하나라도 남아 있으면 후보에서 빠진다.
    ".claude",
    ".codex",
)


def framework_agent_docs(bundle_dir):
    """`docs/agent/` 의 정본 파일 이름. install 과 uninstall 이 **같은 함수**를 본다.

    번들에서 읽는 이유는 목록을 손으로 두 벌 적지 않기 위해서다. 손으로 적으면 문서가 하나
    늘 때마다 uninstall 쪽을 잊고, 잊은 파일은 영원히 남는다. 반대로 번들에 없는 이름을
    uninstall 이 지우는 일도 없다 — 후보 자체가 이 목록이다.
    """
    source = os.path.join(bundle_dir, "docs", "agent")
    names = []
    if os.path.isdir(source):
        names = [name for name in sorted(os.listdir(source))
                 if os.path.isfile(os.path.join(source, name))]
    for name in FRAMEWORK_AGENT_GENERATED:
        if name not in names:
            names.append(name)
    return tuple(sorted(names))


def sage_tree_paths(dest):
    return tuple(os.path.join(os.path.abspath(dest), rel) for rel in SAGE_TREES)
