"""asset_paths — 자산(hook/agent/skill) 파일 경로의 단일 로케이터.

배경: "id(kebab)↔core(snake)↔spec(.md)↔adapter(.sh)" 경로 조립이 generate/validate/absorb
세 명령에 각각 재구현돼 있어(외부검토 P2-6), 디렉토리 규약을 바꾸면 여러 곳을 수동 동기화해야 했다.
이 모듈로 수렴시켜 규약 변경이 1파일에서 끝나게 한다. 순수 경로 계산(IO 0, 결정론).

core/native/adapter 는 hook 전용(core_adapter/native form). agent/skill 은 interpretive 라
spec/claims 만 의미가 있다. 경로 문자열은 기존 각 사이트의 조립 결과와 바이트 동일해야 한다(무위험 리팩터).
"""
import contextlib
import contextvars
import os
import stat
from dataclasses import dataclass

# 소비 프로젝트의 **기계 소유 트리**. SAGE 가 덮어쓰는 것은 전부 이 하나 아래에 있다.
#
# 이전에는 실행 자산이 `scripts/sage_harness/` 에, schema 가 `schema/` 에 나뉘어 있었다. 둘 다
# 프로젝트가 이미 쓰는 이름이라, 공유 디렉터리 안에서 SAGE 것과 남의 것이 섞였다. 트리를 하나로
# 모으면 소유 규칙도 하나가 된다 — "여기 있는 것은 SAGE 가 덮어쓴다".
#
# `docs/sage_harness/`(사람이 편집하는 spec)와 같은 토큰을 쓴다. 새 어휘를 만들지 않는다.
SAGE_TREE = "sage_harness"

_HOOKS_REL = os.path.join(SAGE_TREE, "hooks")
_SCHEMA_REL = os.path.join(SAGE_TREE, "schema")
_VERIFY_REL = os.path.join(SAGE_TREE, "verify-changes.sh")
_DOCS_REL = os.path.join("docs", "sage_harness")

# --- 이행·호환 전용 --------------------------------------------------------
#
# **배치 경로로 쓰지 않는다.** 여기 있는 상수가 배치 자리에 등장하는 순간 구 경로가 다시 정본이
# 된다. 쓰이는 곳은 둘뿐이다 — upgrade 의 레이아웃 이행, 그리고 hook 진입점의 구 경로 해석.
LEGACY_SAGE_TREE = os.path.join("scripts", "sage_harness")
LEGACY_HOOKS_REL = os.path.join(LEGACY_SAGE_TREE, "hooks")
LEGACY_SCHEMA_REL = "schema"
LEGACY_VERIFY_REL = os.path.join("scripts", "verify-changes.sh")
# 이행 뒤 비었을 때만 정리하는 부모. SAGE 가 만든 적 없는 사용자 파일이 남으면 보존한다.
LEGACY_PARENTS = ("scripts", "schema")


# --- 레이아웃 판정 ------------------------------------------------------------
#
# **경로 계산은 파일시스템을 보지 않는다.** 이전에는 경로 property 가 "신 경로에 runtime/ 이
# 있으면 신 경로, 없으면 구 경로" 로 폴백했는데, 그 property 를 읽기 전용이라고 적어 두고도
# `generate` 의 adapter 쓰기 목록이 같은 값을 받아 갔다. 구 레이아웃 프로젝트에서 조용히 구
# 경로에 쓰는 통로였고, 전체 테스트가 통과해도 남는 구멍이었다.
#
# 그래서 판정을 **한 번** 하고 그 결과를 불변값으로 넘긴다. 어느 레이아웃인지 아는 것은 명령의
# 일이고, 경로 조립은 그 값을 받아 계산만 한다.

LAYOUT_ENGINE = "engine"                    # SAGE 엔진 저장소 — 소스가 scripts/sage_harness/
LAYOUT_CONSUMER_CURRENT = "consumer"        # 소비 프로젝트 신 레이아웃 — sage_harness/
LAYOUT_CONSUMER_LEGACY = "consumer-legacy"  # 소비 프로젝트 구 레이아웃 — scripts/sage_harness/
LAYOUT_CONFLICT = "conflict"                # 구·신 공존 — 어느 쪽이 정본인지 도구가 정할 수 없다

_LAYOUT_HOOKS_REL = {
    LAYOUT_ENGINE: LEGACY_HOOKS_REL,
    LAYOUT_CONSUMER_CURRENT: _HOOKS_REL,
    LAYOUT_CONSUMER_LEGACY: LEGACY_HOOKS_REL,
}
_LAYOUT_SCHEMA_REL = {
    LAYOUT_ENGINE: LEGACY_SCHEMA_REL,
    LAYOUT_CONSUMER_CURRENT: _SCHEMA_REL,
    LAYOUT_CONSUMER_LEGACY: LEGACY_SCHEMA_REL,
}


# 레이아웃이 **살아 있다**는 표시. 디렉터리가 아니라 이 파일 하나가 기준이다.
#
# 디렉터리 존재로 판정하면 두 가지가 깨진다. 첫째, 이행이 SAGE 코어를 지운 뒤 사용자 파일이
# 한 장 남으면 그 폴더 때문에 영영 공존으로 읽힌다. 둘째, 배치가 끝나기 전의 미완성 트리가
# 이미 정본으로 보인다 — 그 순간 반쪽짜리 게이트가 선다.
#
# `hook_entry` 가 코어를 고를 때 보는 것과 **같은 파일**이어야 한다. 판정과 해석이 다른 질문을
# 하면, 도구가 "여기가 정본" 이라고 말하는 자리와 실제로 도는 자리가 갈린다.
SENTINEL_REL = os.path.join("runtime", "run_hook.py")


def is_reparse(path: str) -> bool:
    """이 이름이 **다른 곳을 가리키는가.**

    `os.path.islink()` 로는 부족하다 — Windows 에서 **junction 에 False 를 낸다.** junction 은
    symlink 가 아니라 별도의 reparse point 이고, 실기 검증에서 그대로 드러났다.

        os.path.islink        : False
        FILE_ATTRIBUTE_REPARSE: True
        st_reparse_tag        : 0xa0000003

    조상 하나가 junction 이면 그 아래 경로로 하는 삭제가 프로젝트 밖에 닿는다. 이 저장소가
    Windows 용 mutation backend 를 따로 가진 이유가 그것이고, 판정도 같은 것을 봐야 한다.
    """
    if os.path.islink(path):
        return True
    try:
        info = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def escapes_root(root: str, path: str) -> bool:
    """`root` 에서 `path` 까지 가는 길에 **다른 곳을 가리키는 성분**이 있는가.

    leaf 만 보는 것으로는 부족하다 — 조상 하나가 밖을 가리키면 leaf 는 멀쩡한 정규 파일로
    보이고, 그 경로로 하는 삭제가 프로젝트 밖에 닿는다. 레이아웃 이행에서 실제로 그렇게
    프로젝트 밖 파일이 지워졌고, `--unregister` 의 adapter 제거에서 같은 일이 반복됐다.

    `is_reparse` 와 같은 자리에 둔다. 둘 다 답하는 질문이 "이 경로를 우리 것으로 취급해도
    되는가" 이고, 그 질문은 삭제 구현이 아니라 **판정**에 속한다.
    """
    base = os.path.abspath(root)
    cursor = base
    for part in os.path.relpath(os.path.abspath(path), base).split(os.sep):
        if part in ("", "."):
            continue
        if part == "..":
            return True
        cursor = os.path.join(cursor, part)
        if is_reparse(cursor):
            return True
    return False


def layout_is_active(hooks_dir_path: str, root: str = None) -> bool:
    """그 hook 트리에서 게이트가 실제로 설 수 있는가.

    symlink 는 인정하지 않는다. 링크는 대상이 프로젝트 밖일 수 있고, 그러면 "어느 코드가
    게이트인가" 를 프로젝트 밖이 정하게 된다.

    **leaf 만 보는 것으로는 부족하다.** 조상 디렉터리 하나가 밖을 가리키면 sentinel 은 정상
    파일로 보인다. `root` 를 주면 거기까지 가는 길 전체를 본다 — 판정이 곧 삭제 대상 선정으로
    이어지므로, 여기서 놓치면 프로젝트 밖 파일이 삭제 계획에 오른다.
    """
    sentinel = os.path.join(hooks_dir_path, SENTINEL_REL)
    if not os.path.isfile(sentinel) or is_reparse(sentinel):
        return False
    if root is None:
        return True
    return not escapes_root(root, sentinel)


# 이행 중에만 열리는 **명시적 범위.** 전환 구간에는 구·신 sentinel 이 둘 다 있어 판정이
# `CONFLICT` 인데, 이행을 끝내려면 배치·재생성·검증이 신 레이아웃을 보고 돌아야 한다.
#
# 조용한 폴백이 아니다 — 비어 있으면 판정이 그대로 선다. 여는 자리는 `upgrade` 하나이고,
# `with` 를 벗어나면 반드시 닫힌다. 인자로 8개 모듈에 실어 나르는 대신 이 방식을 고른 이유는,
# 그 인자가 닿지 않는 leaf 가 하나라도 남으면 **거기서 조용히 다른 트리를 보기** 때문이다.
_OVERRIDE = contextvars.ContextVar("sage_layout_override", default=None)


@contextlib.contextmanager
def layout_override(root: str, layout: str):
    """이행 중 `detect_layout` 의 답을 고정한다. **`upgrade` 전용.**

    `root` 에 결속한다. 결속하지 않으면 이 범위 안에서 **다른 프로젝트를 판정하는 호출까지**
    같은 답을 받는다 — 이행 중 하위 명령이 전역 skill 경로나 다른 트리를 건드리는 순간
    그쪽 배치가 엉뚱한 레이아웃으로 간다.
    """
    token = _OVERRIDE.set((os.path.abspath(root), layout))
    try:
        yield
    finally:
        _OVERRIDE.reset(token)


def detect_layout(root: str) -> str:
    """`root` 가 어느 레이아웃인가. **파일시스템을 보는 유일한 자리.**

    빈 디렉터리(신규 install 대상)는 `CONSUMER_CURRENT` 다 — 아직 아무것도 없다는 것은 구
    레이아웃이라는 뜻이 아니다. 구·신 공존은 판정하지 않고 `CONFLICT` 로 돌려 호출부가
    fail-closed 하게 한다.

    공존은 **이행 중 정상 상태**이기도 하다. 그것을 갈라 보는 것은 `upgrade` 하나이고, 다른
    호출부에게는 그냥 `CONFLICT` 다 — 이행을 아는 명령만 이행 상태를 다룬다.
    """
    override = _OVERRIDE.get()
    if override is not None and override[0] == os.path.abspath(root):
        return override[1]
    from sage import _resources
    if _resources.is_engine_source_tree(root):
        return LAYOUT_ENGINE
    current = layout_is_active(os.path.join(root, _HOOKS_REL), root)
    legacy = layout_is_active(os.path.join(root, LEGACY_HOOKS_REL), root)
    if current and legacy:
        return LAYOUT_CONFLICT
    if legacy:
        return LAYOUT_CONSUMER_LEGACY
    return LAYOUT_CONSUMER_CURRENT


def layout_hooks_dir(root: str, layout: str) -> str:
    """판정된 레이아웃의 hook 코어 위치. `CONFLICT` 는 경로를 내지 않는다."""
    if layout == LAYOUT_CONFLICT:
        raise ValueError("layout conflict: both consumer layouts exist")
    return os.path.join(root, _LAYOUT_HOOKS_REL[layout])


def layout_schema_dir(root: str, layout: str) -> str:
    if layout == LAYOUT_CONFLICT:
        raise ValueError("layout conflict: both consumer layouts exist")
    return os.path.join(root, _LAYOUT_SCHEMA_REL[layout])


_LAYOUT_VERIFY_REL = {
    LAYOUT_ENGINE: LEGACY_VERIFY_REL,
    LAYOUT_CONSUMER_CURRENT: _VERIFY_REL,
    LAYOUT_CONSUMER_LEGACY: LEGACY_VERIFY_REL,
}


def layout_verify_script(root: str, layout: str) -> str:
    if layout == LAYOUT_CONFLICT:
        raise ValueError("layout conflict: both consumer layouts exist")
    return os.path.join(root, _LAYOUT_VERIFY_REL[layout])


def sage_tree(root: str) -> str:
    """소비 프로젝트의 기계 소유 트리 절대경로."""
    return os.path.join(root, SAGE_TREE)


def hooks_dir(root: str) -> str:
    return os.path.join(root, _HOOKS_REL)


def schema_dir(root: str) -> str:
    return os.path.join(root, _SCHEMA_REL)


def verify_script(root: str) -> str:
    return os.path.join(root, _VERIFY_REL)


def legacy_hooks_dir(root: str) -> str:
    """구 레이아웃의 hook 코어 위치. 이행과 호환 해석에만 쓴다."""
    return os.path.join(root, LEGACY_HOOKS_REL)


def hook_runtime_files(root: str, layout: str = LAYOUT_CONSUMER_CURRENT) -> dict[str, list[str]]:
    """hook 공용 런타임 파일 그룹.

    manifest 에 per-hook 으로 중복 스탬프하지 않고 top-level hook_runtime_hash 로 한 번만 추적한다.
    """
    base = layout_hooks_dir(root, layout)
    runtime = os.path.join(base, "runtime")
    policies = os.path.join(base, "policies")
    strategies = os.path.join(base, "strategies", "pre_implementation_gate")
    required_strategies = [os.path.join(strategies, name) for name in (
        "claude_grep_first.py", "codex_feature_signal.py", "cycle_domain_review.py")]
    strategy_files = list(required_strategies)
    if os.path.isdir(strategies):
        strategy_files.extend(
            os.path.join(strategies, name) for name in sorted(os.listdir(strategies))
            if name.endswith(".py") and os.path.isfile(os.path.join(strategies, name))
            and os.path.join(strategies, name) not in required_strategies)
    return {
        "shared": [
            os.path.join(base, "cycle_binding.py"),
            # risk_declaration.py: Phase 00 Risk 선언을 읽는 유일한 정본. 게이트와 hook_runtime 이
            # 둘 다 import 하므로 누락되면 설치본에서 hook 이 import 단계에서 죽는다. 추적하지
            # 않으면 이 파일만 바꿔 tier 를 낮춰 읽게 만들어도 hook_runtime_hash 가 PASS 한다.
            os.path.join(base, "risk_declaration.py"),
            # path_risk.py: 경로 기준 위험도 하한의 유일한 정본. 게이트와 `sage explain` 이
            # 둘 다 이 함수를 부른다. 누락되면 설치본에서 게이트가 import 단계에서 죽고,
            # 추적하지 않으면 이 파일의 glob 순서만 바꿔 위험도를 낮춰도 hash 가 PASS 한다.
            os.path.join(base, "path_risk.py"),
            os.path.join(runtime, "run_hook.py"),
            os.path.join(runtime, "hook_runtime.py"),
            # checklist_contract.py: profile 검증과 pre-phase4 runtime이 공유하는 경로 봉쇄 계약.
            # 누락/표류하면 유효성 판정과 실제 filesystem 읽기 경계가 갈린다.
            os.path.join(runtime, "checklist_contract.py"),
            # loop_audit.py: hook_runtime.build_snapshot 가 audit_summary 를 호출하는 전이 의존이자
            # 게이트가 신뢰하는 감사 트레일 로직. 추적 안 하면 감사 무결성 코드가 validate 미감지로
            # 표류(7차 배치3, codex R1b P2 수용).
            os.path.join(runtime, "loop_audit.py"),
            # retro_audit.py: retro_gate_result 가 신뢰하는 Loop C 감사 트레일. loop_audit.py 와
            # 동일 근거로 추적 — 이 파일 없이는 retro_gate 의 BLOCK 판정 자체가 성립 안 한다(9-C v1).
            os.path.join(runtime, "retro_audit.py"),
            # acceptance_waiver.py: build_snapshot 과 report gate가 신뢰하는 L3 waiver 감사/검증 정본.
            # 미추적 시 이 파일만 변조해도 hook_runtime_hash가 PASS하여 acceptance enforce를 우회할 수 있다.
            os.path.join(runtime, "acceptance_waiver.py"),
            # override_audit.py: BLOCK 을 실제로 들어올리는 판정(is_override_active/active_grants)과
            # 그 감사 정본. 미추적 시 이 파일만 변조해도 hook_runtime_hash 가 PASS 하여 **모든 우회
            # 가능 게이트가 상시 열린다**(10-e 에서 변조 실험으로 확인). acceptance_waiver 와 같은
            # 근거이고, 우회 판정 그 자체라 오히려 더 직접적이다.
            os.path.join(runtime, "override_audit.py"),
            # policies/retro_gate.py: enforce 판정 그 자체(BLOCK/WARN). 파일이 없으면 Stop 오케스트레이터가
            # import 실패를 INFO skip 으로 낮춰 **enforce 가 조용히 무동작**한다 → validate 가 못 잡으면
            # 설치본에서 이 파일만 빠진 rolling upgrade 가 게이트를 은밀히 해제한다(codex 구현리뷰 2R P0).
            # knowledge_capture/output_contract 는 advisory-only 라 부재해도 리포트 한 줄이 빠질 뿐이지만,
            # retro_gate 는 enforcement 라 반드시 추적한다.
            os.path.join(policies, "retro_gate.py"),
            # policies/writeback_depth_gate.py: retro_gate 와 동일한 enforcement 판정(BLOCK/WARN).
            # 파일 부재 시 Stop 오케스트레이터가 INFO skip 으로 낮춰 enforce 가 조용히 무동작하므로,
            # rolling upgrade 에서 이 파일만 빠져도 게이트가 은밀히 해제되지 않게 반드시 추적한다.
            os.path.join(policies, "writeback_depth_gate.py"),
            # messages.py: io_claude/io_codex 가 import 하는 게이트/컴플라이언스 문구 SSOT(5-3).
            # 추적 안 하면 사용자 대상 게이트 문구가 validate 미감지로 표류(loop_audit 과 동일 논리).
            os.path.join(runtime, "messages.py"),
            # recovery.py: BLOCK 마다 다음 행동을 붙이는 표. `messages.py` 가 import 하므로
            # 누락되면 게이트 렌더가 import 단계에서 죽는다. 추적하지 않으면 복구 명령을
            # 조용히 바꿔도 hook_runtime_hash 가 PASS 한다.
            os.path.join(runtime, "recovery.py"),
            # cycle_state.py: 게이트가 "이 편집이 어느 사이클인가" 를 읽는 선언 파일의 해석 정본.
            # 미추적 시 이 파일만 변조해도 hook_runtime_hash 가 PASS 하는데, read_declaration 이
            # 항상 빈 stem 을 돌려주게 바꾸면 선언이 조용히 사라지고, 반대로 고정 stem 을 돌려주게
            # 바꾸면 완결 사이클 차단이 통째로 무력화된다. override_audit 과 같은 근거다.
            os.path.join(runtime, "cycle_state.py"),
            # document_language.py: 사이클 문서 언어 충돌 판정 그 자체. 미추적 시 이 파일만
            # 변조해도 hook_runtime_hash 가 PASS 하는데, `consistency_issues` 가 항상 빈 목록을
            # 돌려주게 바꾸면 언어 충돌 차단이 통째로 사라지고 아무 표시도 남지 않는다.
            # cycle_state 와 같은 근거다 — 게이트가 읽는 해석 정본은 전부 추적한다.
            os.path.join(runtime, "document_language.py"),
            # prose_language.py: marker 아래 **본문**이 선언 언어를 지키는가의 판정 정본.
            # document_language 와 같은 근거이고, 게이트가 import 실패를 fail-closed 로 받는
            # 것과 짝을 이룬다 — 차단은 되지만 그 상태가 왜 생겼는지는 validate 가 짚어줘야 한다.
            os.path.join(runtime, "prose_language.py"),
        ] + strategy_files,
        "claude": [os.path.join(runtime, "io_claude.py")],
        "codex": [os.path.join(runtime, "io_codex.py")],
    }


def docs_dir(root: str, kind: str) -> str:
    """kind 별 spec 디렉토리 (docs/sage_harness/{kind}s). spec 파일 없이 디렉토리만 필요할 때
    (존재 확인·목록화) 손조립을 피하기 위한 단일소스(N-R2: 경로 규약을 1파일로)."""
    return os.path.join(root, _DOCS_REL, f"{kind}s")


@dataclass(frozen=True)
class AssetPaths:
    """단일 자산의 표준 경로 집합. kind ∈ {"hook","agent","skill","mcp"}.

    mcp 는 spec(docs/sage_harness/mcps/{id}.md)만 사용(core/native/adapter/claims 무관)."""
    root: str
    kind: str
    id: str
    layout: str = LAYOUT_CONSUMER_CURRENT

    @property
    def snake(self) -> str:
        return self.id.replace("-", "_")

    @property
    def _docs_dir(self) -> str:
        # docs/sage_harness/{hooks|agents|skills|mcps}
        return docs_dir(self.root, self.kind)

    @property
    def spec(self) -> str:
        return os.path.join(self._docs_dir, f"{self.id}.md")

    @property
    def claims(self) -> str:
        return os.path.join(self._docs_dir, f"{self.id}.claims.yml")

    # --- hook 전용 (sage_harness/hooks 하위) ---
    @property
    def _hooks_base(self) -> str:
        """주입된 layout 으로만 계산한다. **파일시스템을 보지 않는다.**

        이전 구현은 여기서 디스크를 보고 구 경로로 폴백했다. property 를 "읽기용" 이라 적어
        두었지만 `generate` 의 adapter 쓰기 목록이 같은 값을 받아 갔고, 구 레이아웃
        프로젝트에서 조용히 구 경로에 쓰는 통로가 됐다. 판정은 호출부가 한 번 하고 넘긴다.
        """
        return layout_hooks_dir(self.root, self.layout)

    @property
    def core(self) -> str:
        # 결정론 알고리즘 pure core. snake 변환은 파일명 규약(aaa-hook → aaa_hook_core.py).
        return os.path.join(self._hooks_base, f"{self.snake}_core.py")

    @property
    def native(self) -> str:
        # form:native hook 의 단일 .sh(어댑터 분리 없음).
        return os.path.join(self._hooks_base, f"{self.id}.sh")

    def adapter(self, runtime: str) -> str:
        # form:core_adapter hook 의 런타임별 얇은 어댑터.
        return os.path.join(self._hooks_base, "adapters", runtime, f"{self.id}.sh")
