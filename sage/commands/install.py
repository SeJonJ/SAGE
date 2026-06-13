"""sage install — host 택1 + CORE 하네스 부트스트랩 (결정론 복사).

마스터 §13 + CORE 카탈로그 §1·§4: install 은 동작하는 CORE 하네스를 배치한다.
- framework 템플릿(중립): AGENT_GUIDE.md, {wrapper}, verification-protocol.md,
  scripts/verify-changes.sh, docs/agent/*
- CORE hook: spec(docs/sage_harness/hooks/*.md) + 정본(scripts/sage_harness/hooks: core+adapter+strategy+native)
- CORE roster agent spec(중립): leader/backend/frontend/qa/reviewer/convention-checker
- profile(빈 스키마, host/prefix 치환) + spec 템플릿 + schema + manifest(CORE hook 등록)
배치 후: profile 값 채움 → `sage generate --kind hook --write`(등록 산출물 + manifest 스탬프).
독립(제약 #2): 복사 리소스는 전부 도메인값 0(중립). 프로젝트 값은 profile 로만.
멱등: 기존 파일 skip(--force 로 덮어쓰기). AI 생성 아님(고정 템플릿 복사).
"""
import json
import os

from sage import _resources   # 번들 리소스 경로 단일 해석(env override + repo fallback — 재배치/설치 대비)

# CORE roster (중립 6인) + CORE hook 6종(form). 도메인값 아님 = framework 메타.
_CORE_AGENTS = ["leader", "backend", "frontend", "qa", "reviewer", "convention-checker"]
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
    p = sub.add_parser("install", help="SAGE CORE 하네스 설치 (host 택1 + framework/hook/agent 배치)")
    p.add_argument("--host", choices=["claude", "codex"], required=True,
                   help="host_runtime — PDCA를 실행하는 주 런타임 (Claude 특권화 금지)")
    p.add_argument("--prefix", default="sage", help="자산 네이밍 prefix")
    p.add_argument("--dest", default=".", help="설치 대상 프로젝트 루트")
    p.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기 (기본: skip)")
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
    _write(dst, open(src, encoding="utf-8").read(), force, created, skipped, executable)


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


def _profile_with_host(host, prefix):
    """templates/project-profile.yaml 을 읽어 host/prefix 만 치환(나머지는 빈 스키마 유지)."""
    src = os.path.join(_resources.templates_dir(), "project-profile.yaml")
    text = open(src, encoding="utf-8").read()
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
        "sage_version": "0.1.0", "generator_version": "0.1.0", "template_version": "0.1.0",
        "host_runtime": host, "assets": assets,
    }


def run(args) -> int:
    dest = os.path.abspath(args.dest)
    created, skipped = [], []
    wrapper = "CLAUDE.md" if args.host == "claude" else "CODEX.md"
    core = _resources.core_dir()
    fw = os.path.join(core, "framework")

    # 1. profile (host/prefix 치환, 나머지 빈 스키마)
    _write(os.path.join(dest, "sage", "project-profile.yaml"),
           _profile_with_host(args.host, args.prefix), args.force, created, skipped)

    # 2. framework 템플릿(중립): AGENT_GUIDE, {wrapper}, verification-protocol, verify-changes.sh, docs/agent/*
    _copy_file(os.path.join(fw, "AGENT_GUIDE.md"), os.path.join(dest, "AGENT_GUIDE.md"), args.force, created, skipped)
    _copy_file(os.path.join(fw, wrapper), os.path.join(dest, wrapper), args.force, created, skipped)
    _copy_file(os.path.join(fw, "verification-protocol.md"),
               os.path.join(dest, "verification-protocol.md"), args.force, created, skipped)
    _copy_file(os.path.join(fw, "scripts", "verify-changes.sh"),
               os.path.join(dest, "scripts", "verify-changes.sh"), args.force, created, skipped)
    _copy_tree(os.path.join(fw, "docs", "agent"), os.path.join(dest, "docs", "agent"), args.force, created, skipped)

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
    for sub in ("skills",):   # 빈 자산 디렉토리(프로젝트별 skill 은 추후)
        d = os.path.join(dest, "docs", "sage_harness", sub)
        os.makedirs(d, exist_ok=True)
        gk = os.path.join(d, ".gitkeep")
        if not os.path.exists(gk):
            open(gk, "w").close(); created.append(gk)

    # 6. manifest (CORE hook 등록 — generate 가 hash 스탬프)
    _write(os.path.join(dest, "docs", "sage_harness", ".manifest.json"),
           json.dumps(_manifest(args.host), ensure_ascii=False, indent=2) + "\n", args.force, created, skipped)

    # 7. spec 템플릿(사람 작성 참고) + schema(validate 참조)
    templates = _resources.templates_dir()
    for t in ("agent.spec.md", "hook.spec.md", "skill.spec.md", "claims.yml"):
        _copy_file(os.path.join(templates, t), os.path.join(dest, "sage", "templates", t), args.force, created, skipped)
    _copy_file(os.path.join(_resources.schema_dir(), "manifest.schema.json"),
               os.path.join(dest, "schema", "manifest.schema.json"), args.force, created, skipped)

    # 보고
    print(f"== sage install (host={args.host}, prefix={args.prefix}) → {dest} ==")
    print(f"생성 {len(created)}건 (framework + CORE hook {len(_CORE_HOOKS)} + roster agent {len(_CORE_AGENTS)}):")
    for p in sorted(created):
        print(f"  + {os.path.relpath(p, dest)}")
    if skipped:
        print(f"skip {len(skipped)}건 (이미 존재 — --force 로 덮어쓰기):")
        for p in sorted(skipped):
            print(f"  = {os.path.relpath(p, dest)}")
    print("다음: sage/project-profile.yaml 값 채움 → `sage generate --kind hook --write` (등록 산출물 + manifest 스탬프).")
    return 0
