"""sage install — host 택1 + 빈 스키마 profile + framework 배치 (부트스트랩).

마스터 §13: install → host_runtime 선택 + CORE 템플릿(빈 스키마 profile + spec 템플릿 + 빈 manifest) 배치.
멱등: 이미 있는 파일은 기본 skip(--force 로 덮어쓰기). 결정론(고정 템플릿 복사, AI 생성 아님).
배치 후 사용자/AI 가 profile 값을 채우고 spec 을 작성한다(빈 스키마 → 값은 대화로).
"""
import os
import shutil
import sys

# 이 파일: sage/commands/install.py → 레포 루트 = ../../
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_TEMPLATES = os.path.join(_REPO_ROOT, "templates")
_SCHEMA = os.path.join(_REPO_ROOT, "schema")


def register(sub):
    p = sub.add_parser("install", help="SAGE CORE 설치 (host 택1 + 빈 스키마 배치)")
    p.add_argument("--host", choices=["claude", "codex"], required=True,
                   help="host_runtime — PDCA를 실행하는 주 런타임 (Claude 특권화 금지)")
    p.add_argument("--prefix", default="sage", help="자산 네이밍 prefix")
    p.add_argument("--dest", default=".", help="설치 대상 프로젝트 루트")
    p.add_argument("--force", action="store_true", help="기존 파일 덮어쓰기 (기본: skip)")
    p.set_defaults(func=run)


def _write(path, content, force, created, skipped):
    if os.path.exists(path) and not force:
        skipped.append(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(path)


def _profile_with_host(host, prefix):
    """templates/project-profile.yaml 을 읽어 host/prefix 만 치환(나머지는 빈 스키마 유지)."""
    src = os.path.join(_TEMPLATES, "project-profile.yaml")
    text = open(src, encoding="utf-8").read()
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("host: ") and "claude | codex" in line:
            out.append(line.split("host:")[0] + f"host: {host}                   # claude | codex — 설치 시 택1")
        elif s.startswith("name:") and "project:" not in line and out and out[-1].lstrip().startswith("project:"):
            out.append(line)  # name 은 빈값 유지
        elif s.startswith('prefix:'):
            indent = line[:len(line) - len(line.lstrip())]
            out.append(f'{indent}prefix: "{prefix}"')
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def run(args) -> int:
    dest = os.path.abspath(args.dest)
    created, skipped = [], []

    # 1. project-profile.yaml (host/prefix 치환, 나머지 빈 스키마)
    _write(os.path.join(dest, "sage", "project-profile.yaml"),
           _profile_with_host(args.host, args.prefix), args.force, created, skipped)

    # 2. docs/sage_harness 레이아웃 + 빈 manifest + 빈 자산 디렉토리
    manifest = (
        '{\n'
        '  "sage_version": "0.1.0",\n'
        '  "generator_version": "0.1.0",\n'
        '  "template_version": "0.1.0",\n'
        f'  "host_runtime": "{args.host}",\n'
        '  "assets": {}\n'
        '}\n'
    )
    _write(os.path.join(dest, "docs", "sage_harness", ".manifest.json"), manifest, args.force, created, skipped)
    for sub in ("hooks", "agents", "skills"):
        d = os.path.join(dest, "docs", "sage_harness", sub)
        os.makedirs(d, exist_ok=True)
        gk = os.path.join(d, ".gitkeep")
        if not os.path.exists(gk):
            open(gk, "w").close(); created.append(gk)

    # 3. spec 템플릿 복사 (사람이 작성 시 참고)
    for t in ("agent.spec.md", "hook.spec.md", "skill.spec.md", "claims.yml"):
        srcp = os.path.join(_TEMPLATES, t)
        if os.path.exists(srcp):
            _write(os.path.join(dest, "sage", "templates", t),
                   open(srcp, encoding="utf-8").read(), args.force, created, skipped)

    # 4. schema 복사 (validate 참조)
    srcs = os.path.join(_SCHEMA, "manifest.schema.json")
    if os.path.exists(srcs):
        _write(os.path.join(dest, "schema", "manifest.schema.json"),
               open(srcs, encoding="utf-8").read(), args.force, created, skipped)

    # 보고
    print(f"== sage install (host={args.host}, prefix={args.prefix}) → {dest} ==")
    print(f"생성 {len(created)}건:")
    for p in created:
        print(f"  + {os.path.relpath(p, dest)}")
    if skipped:
        print(f"skip {len(skipped)}건 (이미 존재 — --force 로 덮어쓰기):")
        for p in skipped:
            print(f"  = {os.path.relpath(p, dest)}")
    print("다음: sage/project-profile.yaml 값 채움 → spec 작성 → sage generate/validate.")
    return 0
