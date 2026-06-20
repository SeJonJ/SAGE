"""서브커맨드 공통 헬퍼."""

import os
import re
import sys

_CV_RE = re.compile(r'^CONTRACT_VERSION\s*=\s*["\']([^"\']+)["\']', re.M)


def contract_version_of(core_path: str):
    """core 모듈 소스에서 CONTRACT_VERSION 값을 정규식으로 읽는다(import 부작용 회피, 결정론).

    외부검토 R3/P1-3: generate 가 manifest.adapter_contract_version 을 이 값으로 스탬프하고
    validate 가 대조 → core.decide() 인터페이스(계약) 드리프트를 hash 드리프트와 별개로 잡는
    두 번째 방어선. 파일 없음/패턴 없음 → None(검사 skip)."""
    try:
        with open(core_path, encoding="utf-8") as f:
            m = _CV_RE.search(f.read())
        return m.group(1) if m else None
    except Exception:
        return None

# stub(미구현) 명령만 not_implemented 가 참조. validate/review/change/doctor 는 구현됨(여기 미포함).
STEP = {
    "install": "부트스트랩(host 택1 + 빈 스키마 배치) — v1 stub",
    "generate": "spec → 산출물 렌더. agent/skill render 는 interpretive(런타임 AI) — v1 stub",
    "absorb": "직접수정 diff → spec patch 제안 (§5 M3) — v1 stub",
}


def not_implemented(command: str, detail: str = "") -> int:
    """아직 로직이 없는 명령을 정직하게 알린다 (조용한 실패 금지)."""
    print(f"[sage {command}] 스캐폴드 단계 — 아직 미구현입니다.", file=sys.stderr)
    print(f"  진행 단계: {STEP.get(command, 'N/A')}", file=sys.stderr)
    if detail:
        print(f"  예정 동작: {detail}", file=sys.stderr)
    return 2


def _project_name(profile: dict) -> str:
    if not isinstance(profile, dict):
        return ""
    return str((profile.get("project") or {}).get("name") or "").strip()


def is_bootstrapped(profile: dict) -> bool:
    """profile 이 대화형 부트스트랩(/sage-init)으로 '실효성 있게' 채워졌는지 결정론 판정.

    강한 신호(codex 리뷰 P0-2): project.name 만으론 약하다 — name 만 채우고 risk/components
    가 비면 거버넌스가 여전히 무력(toothless)하다. 따라서 (1) name 비어있지 않음 AND
    (2) risk 분류 글롭(l0~l3) 중 하나라도 있거나 components 가 있음 을 요구한다. /sage-init
    인터뷰는 이 값들을 채우고 핸드오프하므로 generate 시점엔 충족된다. 의존성 0(dict 조회만)."""
    if _project_name(profile) == "":
        return False
    risk = profile.get("risk") or {}
    has_risk = any(
        risk.get(k) for k in ("l0_pass_globs", "l1_path_globs", "l2_path_globs", "l3_filename_globs")
    )
    has_components = bool(profile.get("components"))
    return bool(has_risk or has_components)


def _profile_path(root, dest):
    """설치된 profile.yaml 경로(dest 우선, 없으면 root). 둘 다 없으면 None."""
    for base in (dest, root):
        if base:
            p = os.path.join(base, "sage", "project-profile.yaml")
            if os.path.exists(p):
                return p
    return None


def _manifest_marks_installed(base):
    """manifest 에 install 이 스탬프한 installed_instance:true 가 있으면 True."""
    mp = os.path.join(base, "docs", "sage_harness", ".manifest.json")
    if not os.path.exists(mp):
        return False
    try:
        import json
        with open(mp, encoding="utf-8") as f:
            return bool(json.load(f).get("installed_instance"))
    except Exception:
        return False


# install 이 항상 배치하는 루트 파일들(설치 마커 후보). 레거시 설치(installed_instance 스탬프 이전)도
# wrapper/AGENT_GUIDE 는 갖고 있어 견고. framework repo 루트·테스트 픽스처엔 이 중 무엇도 없다.
_INSTALL_MARKER_FILES = ("AGENT_GUIDE.md", "CLAUDE.md", "CODEX.md")


def is_installed_instance(root, dest):
    """설치 인스턴스(=sage install 이 배치한 프로젝트)인지 다중 신호로 판정(codex 리뷰 R2-P0, R3-P1).

    신호(OR): (1) manifest.installed_instance == true (install 이 스탬프, 신규 설치에서 가장 견고)
              (2) AGENT_GUIDE.md / CLAUDE.md / CODEX.md 존재 (install 이 항상 배치 — 레거시 설치 포함)
    어느 하나만 남아도 설치로 인식 → 단일 파일 삭제로 약한 경로 우회 불가. 레거시 설치
    (installed_instance 스탬프 이전)도 wrapper/AGENT_GUIDE 로 인식된다. framework repo 루트·픽스처는
    이 신호가 전무하므로 '비설치'로 분류돼 기존 폴백/도그푸딩 동작이 보존된다(CI self-validate 무영향)."""
    for base in (dest, root):
        if not base:
            continue
        if any(os.path.exists(os.path.join(base, f)) for f in _INSTALL_MARKER_FILES):
            return True
        if _manifest_marks_installed(base):
            return True
    return False


def _load_profile_yaml(path):
    """profile.yaml → dict. pyyaml 미설치 → "no_yaml"(판정 불가). 파싱 실패 → None(차단 대상)."""
    try:
        import yaml
    except Exception:
        return "no_yaml"
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f.read())
    except Exception:
        return None


# 부트스트랩 게이트 사유 → 사람이 읽는 메시지(generate=차단, validate=경고로 재사용). host-중립(codex 리뷰 P2).
_BOOTSTRAP_HINT = (
    "  대화형 부트스트랩으로 profile 을 작성하세요:\n"
    "    · Claude: 이 디렉토리에서 claude 실행 → `/sage-init`\n"
    "    · Codex:  codex 실행 → `docs/agent/bootstrap-authoring.md` 프로토콜 (CODEX.md 안내)\n"
    "  (수동: sage/project-profile.yaml 의 project.name + risk/components 를 채운 뒤 재실행)"
)
_BOOTSTRAP_MSG = {
    "missing": "profile 미설치 (sage/project-profile.yaml 없음) — 거버넌스 게이트가 무력화됩니다.",
    "parse":   "profile 파싱 실패 (sage/project-profile.yaml) — 손상된 상태로 산출물 생성 차단.",
    "no_yaml": "pyyaml 미설치 — profile 부트스트랩 검증 불가(fail-closed). `pip install pyyaml` 후 재실행.",
    "unbootstrapped": "profile 미부트스트랩 (project.name 비어있거나 risk/components 미설정) — risk globs 0 → 모든 변경 L0 → 거버넌스 무력화.",
}


def bootstrap_gate_reason(root, dest):
    """부트스트랩 게이트 판정 → 사유 키(missing|parse|unbootstrapped) 또는 None(통과).

    - 설치 인스턴스(AGENT_GUIDE 존재): profile 필수 + 파싱 가능 + is_bootstrapped(강함).
    - 비설치(픽스처/framework 폴백): profile 부재는 허용(기존 동작), 단 존재하면 파싱+name 필수.
    - parse 실패는 두 컨텍스트 모두 차단(codex P1-1: mcp fall-through fail-open 봉쇄).
    - pyyaml 미설치(no_yaml)는 판정 불가 → None(generate 의 기존 compile fail-closed 가 처리)."""
    installed = is_installed_instance(root, dest)
    ppath = _profile_path(root, dest)
    if ppath is None:
        return "missing" if installed else None
    prof = _load_profile_yaml(ppath)
    if prof == "no_yaml":
        # 설치 인스턴스에서 pyyaml 부재 = 부트스트랩 검증 불가 → fail-closed 차단(codex R2-P1:
        # mcp 등 비-hook kind 는 후속 compile fail-closed 가 없어 inert 산출물 생성 위험). pyyaml 은
        # sage-harness hard dep 이라 정상 설치엔 늘 존재 — 손상/경량 env 방어용. 비설치는 판정 불가→통과.
        return "no_yaml" if installed else None
    if prof is None or not isinstance(prof, dict):
        return "parse"
    if installed:
        return None if is_bootstrapped(prof) else "unbootstrapped"
    # 비설치 컨텍스트: 약한 신호(name)만 확인 — 픽스처의 폴백/부분 profile 보존.
    return None if _project_name(prof) != "" else "unbootstrapped"


def bootstrap_block_text(reason):
    """generate 차단용 멀티라인 메시지."""
    return f"[sage generate] BLOCK: {_BOOTSTRAP_MSG[reason]}\n{_BOOTSTRAP_HINT}"


def bootstrap_warn_text(reason):
    """validate 경고용 1블록 메시지(읽기전용 → WARN)."""
    return f"⚠️  WARN  {_BOOTSTRAP_MSG[reason]}\n{_BOOTSTRAP_HINT}"
