#!/usr/bin/env bash
# SAGE generated-artifact write guard — canonical algorithm
# spec: docs/sage_harness/hooks/generated-artifact-write-guard.md
#
# 목적: 생성 산출물(.claude/.codex 의 agents/hooks/skills) 직접수정을 block 하고 spec 으로 redirect.
#       산출물 직접수정을 막아야 "항상 spec 을 고친다"가 권고가 아닌 강제가 된다 (설계 §5.6).
#
# 입력 우선순위:
#   1) --path <p>            (테스트/직접호출, 단일)
#   2) $SAGE_GUARD_PATH       (테스트/직접호출, 단일)
#   3) stdin JSON            (런타임 PreToolUse 어댑터)
#      - Claude: tool_input.file_path / path
#      - Codex apply_patch: tool_input.command 본문의 *** Add/Update/Delete File:, *** Move to: 다중 target
#   하나라도 guarded path 면 block (audit 1회차 P0: Codex apply_patch 우회 차단).
#
# 종료코드: 0 = 통과, 2 = block (stderr 메시지가 모델에 전달됨)
set -euo pipefail

extract_paths_from_stdin() {
  # Claude file_path + Codex apply_patch command 본문 다중 target 모두 추출(줄단위 출력).
  # 프로그램은 -c 인자로 주고 stdin 은 JSON 으로 유지(heredoc-as-program 회피).
  python3 -c '
import sys, json, re
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = (d.get("tool_input") or {}) if isinstance(d, dict) else {}
out = []
fp = ti.get("file_path") or ti.get("path")
if fp:
    out.append(fp)
cmd = ti.get("command") or ""
for line in cmd.splitlines():
    m = re.match(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", line) or re.match(r"^\*\*\* Move to: (.+)$", line)
    if m:
        out.append(m.group(1).strip())
for p in out:
    print(p)
' 2>/dev/null || true
}

# guarded = .claude/.codex 의 agents/hooks/skills 산출물 + .mcp.json(SAGE 소유 생성물). (source/spec 경로는 여기 매칭 안 됨 → 자연 통과)
# audit 4회차 P1: 소문자 정규화로 대소문자 우회(.CODEX 등, macOS case-insensitive fs) 차단.
# (symlink 기반 우회는 §5.6 원칙상 범위 밖 — adversarial 은 OS 권한/CI 영역. 본 가드는 drift 방지용)
# .mcp.json: claude MCP 생성물(SAGE 전적 소유, repo 루트) → 직접수정 차단. (.codex/config.toml 은 managed-block 만
#  소유하고 비-MCP 설정 공존이라 파일 통째 가드 안 함 — staleness+소유권 검사로 보호. MCP plan §2.3 비대칭.)
is_guarded() {
  local p; p="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  # 예외: CORE 프레임워크 부트스트랩 자산(install 이 hand-ship — AGENT_GUIDE/docs/agent 와 동류).
  #   CORE skill(sage-init/pdca-start/sage-review) 렌더 + CORE 로스터 6인 에이전트 렌더.
  #   spec→generate 산출물이 아니므로 가드 면제 — 없는 spec 으로 보내는 막다른 redirect 방지(codex 리뷰 P1-2/P2).
  #   면제 패턴은 가드의 다른 패턴과 동일하게 path-global — 런타임 어댑터(hook_runtime.make_rel)가
  #   절대경로를 root 상대로 먼저 정규화한다.
  #   skill: claude=repo .claude/skills, codex=전역 $CODEX_HOME/skills 설치라 repo 산출물 아님 → claude 만 면제.
  #     repo .codex/skills/ 는 프로젝트 skill 영역(generate/extract)이라 동명이라도 계속 가드(과잉면제 방지).
  #   agent: claude=.claude/agents/, codex=.codex/agents/ 둘 다 repo CORE 렌더(install hand-ship) → 둘 다 by-name 면제.
  #     프로젝트 에이전트(비-CORE 이름)는 계속 가드.
  case "$p" in
    *.claude/skills/sage-init/*|*.claude/skills/pdca-start/*|*.claude/skills/sage-review/*|*.claude/skills/sage-asset/*) return 1 ;;
    *.claude/agents/leader.md|*.claude/agents/implementer-a.md|*.claude/agents/implementer-b.md) return 1 ;;
    *.claude/agents/qa.md|*.claude/agents/reviewer.md|*.claude/agents/convention-checker.md)     return 1 ;;
    *.codex/agents/leader.md|*.codex/agents/implementer-a.md|*.codex/agents/implementer-b.md)     return 1 ;;
    *.codex/agents/qa.md|*.codex/agents/reviewer.md|*.codex/agents/convention-checker.md)         return 1 ;;
  esac
  case "$p" in
    *.claude/agents/*|*.claude/hooks/*|*.claude/skills/*) return 0 ;;
    *.codex/agents/*|*.codex/hooks/*|*.codex/skills/*)    return 0 ;;
    .mcp.json|*/.mcp.json)                                 return 0 ;;
  esac
  return 1
}

block() {
  # printf 사용(heredoc temp 파일 회피 — 제한 환경에서도 exit 2 보장, audit 5회차 P1).
  printf '%s\n' \
    "⛔ SAGE write guard: '$1' 는 생성 산출물입니다. 직접수정 금지." \
    "→ docs/sage_harness/<kind>s/<id>.md (spec) 을 고치고 'sage generate' 를 쓰세요." \
    "→ 이미 수정한 diff 라면 'sage absorb --kind <k> --id <id> --from-blocked-diff' 로 spec patch 로 변환하세요." \
    "(sage generate CLI 는 편집도구를 안 거치므로 이 가드에 걸리지 않습니다.)" >&2
  exit 2
}

# 검사 대상 경로 수집(단일 또는 다중)
declare -a TARGETS=()
if [[ "${1:-}" == "--path" ]]; then
  TARGETS+=("${2:-}")
elif [[ -n "${SAGE_GUARD_PATH:-}" ]]; then
  TARGETS+=("$SAGE_GUARD_PATH")
elif [[ ! -t 0 ]]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && TARGETS+=("$line")
  done < <(extract_paths_from_stdin)
fi

# 경로 없음 → 가드 대상 아님
[[ ${#TARGETS[@]} -eq 0 ]] && exit 0

# guarded 판정 우선(P1: source-allow 선판정 제거). guarded path 면 즉시 block.
# docs/sage_harness·scripts/sage_harness 같은 소스는 guarded 패턴(.claude/.codex/{agents,hooks,skills})에
# 애초에 매칭되지 않으므로 자연 통과한다. (.codex/hooks/scripts/... 같은 산출물 하위는 guarded 가 먼저 걸림)
for t in "${TARGETS[@]}"; do
  norm="${t#./}"
  if is_guarded "$norm"; then
    block "$t"
  fi
done

exit 0
