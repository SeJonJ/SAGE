#!/usr/bin/env bash
# SAGE hook 전체 회귀 테스트 — write guard(bash) + reverse_extract hook(python).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/../../../.." && pwd)"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
rc=0

echo "### 1. generated-artifact write guard"
bash "$HERE/run-tests.sh" || rc=1

echo ""
echo "### 2. capture-declared-risk reverse_extract 폐루프"
python3 "$HERE/test_capture_declared_risk.py" || rc=1

echo ""
echo "### 3. post-tool-logger reverse_extract 폐루프 (structural + profile_bound)"
python3 "$HERE/test_post_tool_logger.py" || rc=1

echo ""
echo "### 4. pre-phase4-checklist-gate reverse_extract 폐루프 (IO-bound gate, 2단계 pure core)"
python3 "$HERE/test_pre_phase4_checklist_gate.py" || rc=1

echo ""
echo "### 5. pre-implementation-gate reverse_extract 폐루프 (부분추출 + unresolved 전략슬롯)"
python3 "$HERE/test_pre_implementation_gate.py" || rc=1

echo ""
echo "### 5a. deterministic Cycle-Stem binding"
python3 "$HERE/test_cycle_binding.py" || rc=1

echo ""
echo "### 5b. exact cycle/domain L3 review strategy"
python3 "$HERE/test_cycle_domain_review.py" || rc=1

echo ""
echo "### 6. stop-compliance-report reverse_extract 폐루프 (부분추출 + policy_delta 보존)"
python3 "$HERE/test_stop_compliance_report.py" || rc=1

echo ""
echo "### 7. reverse_extract_agent (agent typed claim 자동도출)"
python3 "$HERE/test_reverse_extract_agent.py" || rc=1

echo ""
echo "### 8. conformance_lint (agent/skill 렌더 부합 결정론 검사)"
python3 "$HERE/test_conformance.py" || rc=1

echo ""
echo "### 9. auto_approve_decision (sage asset-check 승인 UX — auto_approve_safe_default)"
python3 "$HERE/test_asset_check.py" || rc=1

echo ""
echo "### 10. sage change 라우터 (자연어 의도 → generate/absorb)"
python3 "$HERE/test_change_router.py" || rc=1

echo ""
echo "### 11. reviewer_resolution (cross-model peer CLI 직접 탐지)"
python3 "$HERE/test_reviewer_resolution.py" || rc=1

echo ""
echo "### 11b. sage review / cross-check (Phase 05 same-runtime / cross-model 직접 호출)"
python3 "$HERE/test_phase05_review.py" || rc=1

echo ""
echo "### 12. validate 안전성 (오염 manifest test 경로 차단)"
python3 "$HERE/test_validate_safety.py" || rc=1

echo ""
echo "### 13. extract_agent 드라이버 (재현 가능 진입점, 독립)"
python3 "$HERE/test_extract_driver.py" || rc=1

echo ""
echo "### 14. manifest_util (manifest 공용 헬퍼)"
python3 "$HERE/test_manifest_util.py" || rc=1

echo ""
echo "### 16. sage absorb (직접수정→spec patch 제안)"
python3 "$HERE/test_absorb.py" || rc=1

echo ""
echo "### 15. sage install (부트스트랩)"
python3 "$HERE/test_install.py" || rc=1

echo ""
echo "### 18. sage generate (hook 등록 산출물 + manifest 스탬프)"
python3 "$HERE/test_generate.py" || rc=1

echo ""
echo "### 18b. sage-hook 콘솔 엔트리포인트 (bash 비의존 hook 실행 — root/core-dir 해석)"
python3 "$HERE/test_hook_entry.py" || rc=1

echo ""
echo "### 17. reverse_extract_skill (skill typed claim 자동도출)"
python3 "$HERE/test_reverse_extract_skill.py" || rc=1

echo ""
echo "### 19. _resources (번들 리소스 경로 해석 — 패키징/재배치)"
python3 "$HERE/test_resources.py" || rc=1

echo ""
echo "### 20. sage doctor (profile 로드 실패 원인 구분)"
python3 "$HERE/test_doctor.py" || rc=1

echo ""
echo "### 21. 런타임 스모크 (어댑터 subprocess × 합성 인스턴스 — PDCA 강제 생존/예외 표면화, Pattern A 가드)"
python3 "$HERE/test_runtime_smoke.py" || rc=1

echo ""
echo "### 22. golden-instance e2e (install→generate→validate→설치 shim 구동 전체 파이프라인 폐루프)"
python3 "$HERE/test_golden_instance_e2e.py" || rc=1

echo ""
echo "### 23. asset_paths 단일 로케이터 (generate/validate/absorb 경로 수렴 — P2-6, 옛 조립식 동치)"
python3 "$HERE/test_asset_paths.py" || rc=1

echo ""
echo "### 24. hook_runtime / io_* 단위 (R1 어댑터 런타임 추출 — 입력추출/snapshot/전략F8b/렌더채널)"
python3 "$HERE/test_hook_runtime.py" || rc=1

echo ""
echo "### 25. contract_version_of (R3 계약버전 강제 — core.CONTRACT_VERSION 정규식 읽기, import 부작용 0)"
python3 "$HERE/test_contract_version.py" || rc=1

echo ""
echo "### 26. profile_validate (R2 profile 스키마+의미검증 — 오타키 FAIL/전략부재 FAIL/미정의phase FAIL, P0-2)"
python3 "$HERE/test_profile_validate.py" || rc=1

echo ""
echo "### 26b. shared/local profile layering (정책 완화 차단 + capability projection)"
python3 "$HERE/test_profile_layers.py" || rc=1

echo ""
echo "### 26c. project SAGE version contract (required/install/generate/runtime axes)"
python3 "$HERE/test_version_contract.py" || rc=1

echo ""
echo "### 27. validate conformance 배선 (P1-4 agent/skill 폐루프 — render 누락 required claim/금지위반 → validate FAIL)"
python3 "$HERE/test_validate_conformance.py" || rc=1

echo ""
echo "### 28. override_audit (P1-5 게이트 BLOCK 합법 우회 — TTL 만료 자동회수/게이트스코프/append-only 감사)"
python3 "$HERE/test_override_audit.py" || rc=1

echo ""
echo "### 29. claims_codec (P2-7 YAML 단일화 — claims_to_yaml↔load_claims_yaml round-trip, pyyaml 무관 동일)"
python3 "$HERE/test_claims_codec.py" || rc=1

echo ""
echo "### 30. gen_roster (EH-1 동적 컴포넌트 파생 — profile.components→implementer-<comp> spec, 폴백/create-only/dry-run)"
python3 "$HERE/test_gen_roster.py" || rc=1

echo ""
echo "### 31. gen_mcp (MCP 4번째 kind — spec md→.mcp.json+config.toml managed-block, 시크릿 거부/staleness/소유권/단일-target)"
python3 "$HERE/test_gen_mcp.py" || rc=1

echo ""
echo "### 32. mcp shadow pilot (ChatForYou 실 codegraph+obsidian fixture e2e — 라이브 무변경)"
python3 "$HERE/test_mcp_shadow_pilot.py" || rc=1

echo ""
echo "### 33. kind invariants (N-R2 메타 박제 — mcps 경로 손조립 0/계약버전 스탬프·STALE/스키마 닫힘)"
python3 "$HERE/test_kind_invariants.py" || rc=1

echo ""
echo "### 34. loop_audit (Loop A 라운드별 append-only 감사 — open/round/close, run_id 격리, 손상줄 skip)"
python3 "$HERE/test_loop_audit.py" || rc=1

echo ""
echo "### 35. review-loop CLI (Loop A 감사 SAGE-owned 진입점 — 어휘/짝 강제, 음수거부, cfg 스냅샷, 무결성)"
python3 "$HERE/test_review_loop_cli.py" || rc=1

echo ""
echo "### 36. retro (Loop C process-absorb — 증거수집+distiller 제시, 자동반영 없음, 루트탐색/필터/무결성)"
python3 "$HERE/test_retro.py" || rc=1

echo ""
echo "### 37. vault (S5 Obsidian 옵션 — show --vault 대시보드 / retro --vault human-gate, vault_path 마스터게이트)"
python3 "$HERE/test_vault.py" || rc=1

echo ""
echo "### 38. messages SSOT (io_claude/io_codex 공유 게이트/컴플라이언스 문구 통일 — 5-3)"
python3 "$HERE/test_messages.py" || rc=1

echo ""
echo "### 39. bootstrap gate (profile 미부트스트랩 시 generate BLOCK / validate WARN — 강제 진입점)"
python3 "$HERE/test_bootstrap_gate.py" || rc=1

echo ""
echo "### 40. knowledge (Obsidian scan/write-back — vault 게이트, 노트 조립, 인덱스/로그 멱등)"
python3 "$HERE/test_knowledge.py" || rc=1

echo ""
echo "### 41. overlay lint (project overlay 구조/금지 검사)"
python3 "$HERE/test_overlay_lint.py" || rc=1

echo ""
echo "### 41a. overlay classify/materialize/sync (합성 자격 (a)/(b)/(c) + FB23 재분류 + backing 적대적 우회 증명)"
python3 "$HERE/test_overlay_classify.py" || rc=1
python3 "$HERE/test_overlay_reclassification_backing.py" || rc=1
python3 "$HERE/test_overlay_common.py" || rc=1
python3 "$HERE/test_overlay_materialize.py" || rc=1
python3 "$HERE/test_sync_overlays.py" || rc=1

echo ""
echo "### 42. retro_audit (Loop C --check 성공 증거 append-only 감사 — ok/missing/skipped 상태전이)"
python3 "$HERE/test_retro_audit.py" || rc=1

echo ""
echo "### 43. retro_gate (retro 게이트 enforce 판정 BLOCK/WARN — report_gate_enforce 정책)"
python3 "$HERE/test_retro_gate.py" || rc=1

echo ""
echo "### 43a. writeback_depth_gate (L2/L3 심층 노트 self-review 자기선언 게이트 — depth_review_gate 정책)"
python3 "$HERE/test_writeback_depth_gate.py" || rc=1

echo ""
echo "### 44. acceptance waiver (risk policy + exact L3 grant/use/revoke audit)"
python3 "$HERE/test_acceptance_waiver.py" || rc=1

echo ""
echo "### 45. install transaction (preflight-first + rollback + lock/CAS)"
python3 "$HERE/test_install_transaction.py" || rc=1

echo ""
echo "### 46. protected CI authority (base/head max-risk + exact evidence + attestation)"
python3 "$HERE/test_ci_authority.py" || rc=1

echo ""
echo "### 47. manual double-host (desired/actual/active host + opposite reviewer)"
python3 "$HERE/test_runtime_hosts.py" || rc=1

echo ""
echo "### 48. host model catalog/routing (provenance + component/reviewer selection)"
python3 "$HERE/test_model_catalog.py" || rc=1
python3 "$HERE/test_model_routing.py" || rc=1

echo ""
echo "### 49. context snapshot/restore (phase binding + compaction consumer + manual host handoff)"
python3 "$HERE/test_context.py" || rc=1

echo ""
if [[ "$rc" == "0" ]]; then echo "✅ ALL HOOK TESTS PASS"; else echo "❌ FAILURES"; fi
exit "$rc"
