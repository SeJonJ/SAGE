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
import shutil
from pathlib import Path

from sage import __version__

from sage import _resources   # 번들 리소스 경로 단일 해석(env override + repo fallback — 재배치/설치 대비)

# CORE roster (중립 6인) + CORE hook 6종(form) + CORE skill 5종. 도메인값 아님 = framework 메타.
_CORE_AGENTS = ["leader", "implementer-a", "implementer-b", "qa", "reviewer", "convention-checker"]
_CORE_SKILLS = ["sage-pdca-start", "sage-team", "sage-review", "sage-asset", "sage-profile-modify"]
_CORE_BOOTSTRAP_SKILL = "sage-init"
# 은퇴한 CORE skill 이름 — install 시 잔존 사본을 정리(rename 수렴). 이름이 바뀌면 옛 이름을 여기 추가.
_LEGACY_CORE_SKILLS = ["pdca-start"]
# SAGE 가 hand-ship 하는 모든 CORE skill SKILL.md 에 들어있는 마커. 정리 전 SAGE 자산 확인용
# (codex 전역처럼 공유 공간에서 동명의 사용자 skill 을 오삭제하지 않도록).
_LEGACY_SKILL_SIGNATURE = "CORE framework bootstrap asset"
_CORE_HOOKS = [
    ("capture-declared-risk", "core_adapter"),
    ("post-tool-logger", "core_adapter"),
    ("pre-implementation-gate", "core_adapter"),
    ("pre-phase4-checklist-gate", "core_adapter"),
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
                   help="codex host: CORE 스킬($sage-init/$sage-pdca-start/$sage-team/$sage-review/$sage-asset/$sage-profile-modify)의 전역(~/.codex/skills) 설치를 건너뜁니다 (CI/샌드박스용)")
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


def _manifest(host):
    """CORE hook 6종을 등록한 manifest(스켈레톤). hash/conformance 는 generate 가 스탬프."""
    assets = {}
    for hid, form in _CORE_HOOKS:
        # 미스탬프 상태(install 직후): conformance=UNKNOWN(schema 준수). generate --write 가 hash/PASS 스탬프.
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
        _copy_tree(os.path.join(fw, ".claude", "agents"),
                   os.path.join(dest, ".claude", "agents"), args.force, created, skipped)
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

    # 3. CORE hook spec(중립 6종) → docs/sage_harness/hooks/
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

    # 5b. CORE skill spec(중립 5종) → docs/sage_harness/skills/ (host 무관 — CORE agent spec 과 대칭).
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

    # 6. manifest (CORE hook 등록 — generate 가 hash 스탬프)
    _write(os.path.join(dest, "docs", "sage_harness", ".manifest.json"),
           json.dumps(_manifest(args.host), ensure_ascii=False, indent=2) + "\n", args.force, created, skipped)

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
    # 다음 단계 안내 — 설계상 진입점은 "AI 대화로 profile 채우기"다(직접 편집 아님).
    # profile 미부트스트랩(project.name 빈값) 상태에선 sage generate 가 BLOCK 된다(강제 게이트).
    print("")
    print("다음 단계 (대화형 부트스트랩 — 설계상 진입점):")
    if args.host == "claude":
        print("  1) 이 디렉토리에서 claude 를 실행")
        print("  2) `/sage-init` 입력 → AI 가 인터뷰로 sage/project-profile.yaml 을 채움")
        print("  3) 승인 후 핸드오프: `sage generate --kind hook --write` → `sage validate --check --schema`")
    else:
        print("  1) 이 디렉토리에서 codex 를 실행")
        print("  2) `$sage-init` 입력 → AI 가 인터뷰로 sage/project-profile.yaml 을 채움")
        print("     (codex 가 AGENTS.md 를 자동으로 읽어 부트스트랩을 안내하기도 함)")
        print("  3) 승인 후 핸드오프: `sage generate --kind hook --write --target codex` → `sage validate --check --schema`")
        if codex_skill_status:
            status, dst = codex_skill_status
            if status == "installed":
                print(f"  ✅ 전역 $sage-init 스킬 설치: {dst}")
            elif status == "skipped":
                print(f"  = 전역 $sage-init 스킬 최신(동일 내용): {dst}")
            elif status == "stale":
                print(f"  ⚠️  전역 $sage-init 스킬이 현재 SAGE 버전과 다릅니다(구버전 또는 로컬수정): {dst}")
                print("     최신으로 갱신하려면 `sage install --host codex --force` (로컬수정은 덮어써짐).")
            elif status == "error":
                print(f"  ⚠️  전역 $sage-init 스킬 설치 실패(권한/읽기전용 home?): {dst}")
                print("     codex 에서 `$sage-init` 미동작 시 AGENTS.md/bootstrap-authoring.md 프로토콜을 수동 사용하세요.")
            elif status == "missing":
                print("  ⚠️  $sage-init 스킬 소스를 찾지 못해 전역 설치를 건너뜀(번들 손상?).")
            elif status == "disabled":
                print("  = 전역 $sage-init 스킬 설치 생략(--no-global-skill). codex 부트스트랩은 AGENTS.md 라우터로 안내됩니다.")
        for sid, (status, dst) in core_skill_status:
            if status == "installed":
                print(f"  ✅ 전역 ${sid} 스킬 설치: {dst}")
            elif status == "skipped":
                print(f"  = 전역 ${sid} 스킬 최신(동일 내용): {dst}")
            elif status == "stale":
                print(f"  ⚠️  전역 ${sid} 스킬이 현재 SAGE 버전과 다릅니다(구버전 또는 로컬수정): {dst}")
                print("     최신으로 갱신하려면 `sage install --host codex --force`.")
            elif status == "error":
                print(f"  ⚠️  전역 ${sid} 스킬 설치 실패(권한/읽기전용 home?): {dst}")
            elif status == "missing":
                print(f"  ⚠️  ${sid} 스킬 소스를 찾지 못해 전역 설치를 건너뜀(번들 손상?).")
        if not core_skill_status and getattr(args, "no_global_skill", False):
            print(f"  = 전역 CORE 스킬({', '.join(_CORE_SKILLS)}) 설치 생략(--no-global-skill).")
        if agents_md_collision:
            print("  ⚠️  기존 AGENTS.md 가 있어 codex 부트스트랩 라우터를 자동 배치하지 못했습니다.")
            print("     templates 의 AGENTS.md 부트스트랩 섹션을 수동 병합하거나 --force 로 교체하세요.")
    print("")
    print("⚠️  부트스트랩 전(project.name + risk/components 미설정)에는 `sage generate` 가 차단됩니다 — 거버넌스 게이트가 무력화되지 않도록 강제.")
    return 0
