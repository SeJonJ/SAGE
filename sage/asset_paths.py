"""asset_paths — 자산(hook/agent/skill) 파일 경로의 단일 로케이터.

배경: "id(kebab)↔core(snake)↔spec(.md)↔adapter(.sh)" 경로 조립이 generate/validate/absorb
세 명령에 각각 재구현돼 있어(외부검토 P2-6), 디렉토리 규약을 바꾸면 여러 곳을 수동 동기화해야 했다.
이 모듈로 수렴시켜 규약 변경이 1파일에서 끝나게 한다. 순수 경로 계산(IO 0, 결정론).

core/native/adapter 는 hook 전용(core_adapter/native form). agent/skill 은 interpretive 라
spec/claims 만 의미가 있다. 경로 문자열은 기존 각 사이트의 조립 결과와 바이트 동일해야 한다(무위험 리팩터).
"""
import os
from dataclasses import dataclass

_HOOKS_REL = os.path.join("scripts", "sage_harness", "hooks")
_DOCS_REL = os.path.join("docs", "sage_harness")


def hook_runtime_files(root: str) -> dict[str, list[str]]:
    """hook 공용 런타임 파일 그룹.

    manifest 에 per-hook 으로 중복 스탬프하지 않고 top-level hook_runtime_hash 로 한 번만 추적한다.
    """
    runtime = os.path.join(root, _HOOKS_REL, "runtime")
    policies = os.path.join(root, _HOOKS_REL, "policies")
    strategies = os.path.join(root, _HOOKS_REL, "strategies", "pre_implementation_gate")
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
            os.path.join(root, _HOOKS_REL, "cycle_binding.py"),
            os.path.join(runtime, "run_hook.py"),
            os.path.join(runtime, "hook_runtime.py"),
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

    # --- hook 전용 (scripts/sage_harness/hooks 하위) ---
    @property
    def core(self) -> str:
        # 결정론 알고리즘 pure core. snake 변환은 파일명 규약(aaa-hook → aaa_hook_core.py).
        return os.path.join(self.root, _HOOKS_REL, f"{self.snake}_core.py")

    @property
    def native(self) -> str:
        # form:native hook 의 단일 .sh(어댑터 분리 없음).
        return os.path.join(self.root, _HOOKS_REL, f"{self.id}.sh")

    def adapter(self, runtime: str) -> str:
        # form:core_adapter hook 의 런타임별 얇은 어댑터.
        return os.path.join(self.root, _HOOKS_REL, "adapters", runtime, f"{self.id}.sh")
