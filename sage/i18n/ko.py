"""CLI 한국어 catalog.

한국어가 호환 기본값이다. 이 catalog 의 문장은 catalog 도입 **전의 출력을 그대로 재현**해야
하며, 새 문구를 쓰고 싶으면 그건 별개 변경이다 — 언어 배선과 문구 변경을 같은 커밋에 섞으면
회귀가 어느 쪽에서 왔는지 갈라낼 수 없다.

조각을 이어 붙이지 않고 완전한 문장 단위로 둔다. 조각 합성은 어순이 다른 언어에서 반드시
깨지고, 깨진 뒤에는 어느 조각이 원인인지 보이지 않는다.
"""

MESSAGES = {
    # 최초 발견 — 인자 없이 `sage` 를 쳤을 때. 유일하게 한영을 함께 내는 자리라 catalog 를
    # 거치지 않고 고정 문자열이지만, key 는 inventory 대조를 위해 여기에도 등록한다.
    "cli.root.description": (
        "SAGE는 Claude/Codex 프로젝트에 규칙 파일, hook, agent spec을 설치하고 검증하는 CLI입니다."
    ),
    "cli.root.epilog": (
        "기본 사용 순서:\n"
        "  1. sage install --host codex --skill-scope project-local\n"
        "                                     # 또는 --skill-scope global\n"
        "  2. sage generate --kind hook --write\n"
        "  3. sage validate\n"
        "\n"
        "각 명령의 자세한 옵션:\n"
        "  sage <command> --help\n"
    ),
    "cli.root.help_option": "도움말을 보여주고 종료합니다",
    "cli.root.version_option": "설치된 SAGE 버전을 보여줍니다",
    "cli.root.lang_option": "출력 언어를 고릅니다 (기본: ko)",
    "cli.root.positionals_title": "명령어",
    "cli.root.optionals_title": "옵션",
    "cli.root.switch_hint": "영어 도움말: sage --lang en --help",

    # 언어 선택 실패. 판정 이전 단계라 exit 2 로 끝나며 어떤 부작용도 남기지 않는다.
    "cli.lang.unsupported": "지원하지 않는 언어입니다: {value}. 사용 가능: {supported}",
    "cli.lang.missing_value": "--lang 에 값이 필요합니다. 사용 가능: {supported}",
    "cli.lang.duplicated": "--lang 은 한 번만 지정할 수 있습니다",
    "cli.lang.local_invalid": (
        "local profile 의 interface.language 를 읽을 수 없어 한국어로 표시합니다 — "
        "{path} 를 확인하세요"
    ),

    # EH-13 drift 진단. 라벨만 번역하고 논리 경로·건수·구분자는 언어와 무관하게 같다 —
    # 값이 달라지면 같은 drift 가 언어마다 다른 증거로 보인다.
    "cli.drift.changed": "변경",
    "cli.drift.added": "추가",
    "cli.drift.removed": "삭제",
    "cli.drift.more": " 외 {count}건",
    "cli.drift.part": "{label} {count}건: {shown}{more}",

    # 각 명령의 argparse help/description. `--lang en --help` 가 실제로 영어를
    # 내려면 루트 help 만으로는 부족하다 — 사용자가 보는 화면은 하위 명령 쪽이다.

    "cli.absorb.absorb": "직접 고친 생성 파일을 spec 수정안으로 되돌려 제안합니다",
    "cli.absorb.from_blocked_diff": "write guard 에 막힌 diff 를 재입력 없이 바로 patch 후보로 변환",
    "cli.absorb.from_retro": "승인된(approved:true) retro human-gate 노트를 읽어 제안→자산 patch 후보로 변환(Loop C)",
    "cli.absorb.claude": "(agent/skill) 수정된 .claude 산출물 경로",
    "cli.absorb.codex": "(agent/skill) 수정된 .codex 산출물 경로",
    "cli.absorb.guide": "(agent/skill) AGENT_GUIDE 경로",

    "cli.acceptance_waiver.acceptance_waiver": "특정 L3 acceptance의 운영 검증 유예를 명시적으로 기록합니다",
    "cli.acceptance_waiver.grant": "exact cycle/required acceptance ID waiver 발급",
    "cli.acceptance_waiver.confirm_user": "명시 승인한 사용자 표시(로컬 self-asserted audit이며 원격 신원 증명 아님)",
    "cli.acceptance_waiver.ttl": "유효기간, 최대 24h (기본 24h)",
    "cli.acceptance_waiver.list": "waiver audit와 현재 active grant 조회",
    "cli.acceptance_waiver.revoke": "active waiver 명시 회수",

    "cli.asset_check.asset_check": "프레임워크 자산 중 자동 통과 가능/사람 확인 필요를 나눕니다(구 sage review)",
    "cli.asset_check.batch": "auto 버킷을 1줄 요약",
    "cli.asset_check.gate": "review 버킷 있으면 exit 1 (CI 게이트)",

    "cli.authority.authority": "보호된 CI에서 base/head 정책과 exact PDCA 증거를 검증합니다",
    "cli.authority.inspect": "base/head git object를 읽어 권위 판정을 계산합니다",
    "cli.authority.attest": "보호된 CI 판정 claims를 HMAC 서명합니다",
    "cli.authority.gate": "권위 판정과 protected attestation 결속을 검증합니다",
    "cli.authority.root": "base/head object가 존재하는 git repository",
    "cli.authority.issuer": "gate에서는 attestation expected issuer",

    "cli.change.change": "하고 싶은 변경을 어떤 SAGE 명령으로 처리할지 안내합니다",
    "cli.change.intent": "예: \"capture-declared-risk hook 고쳐줘\"",

    "cli.context.context": "phase 경계 context packet을 저장하고 검증 복원합니다",
    "cli.context.snapshot": "완료 phase의 구조화 context packet 저장",
    "cli.context.phase": "profile pdca.phases에 선언된 완료 phase id",
    "cli.context.restore": "packet/source 결속 검증 후 resume briefing 생성",
    "cli.context.snapshot_2": "managed snapshot JSON 경로",

    "cli.cycle.cycle": "지금 작업 중인 사이클을 게이트에 알려줍니다",
    "cli.cycle.stem": "set 할 Cycle-Stem",
    "cli.cycle.create": "Phase 00 뼈대를 만든 뒤 stem 을 선언합니다",
    "cli.cycle.risk": "--create 로 만들 Phase 00의 위험도",
    "cli.cycle.path": "Phase 00을 만들 프로젝트 root 상대 디렉터리",
    "cli.cycle.root": "대상 프로젝트 루트 (기본: cwd 에서 가장 가까운 SAGE 설치본)",
    "cli.cycle.document_language": "이 사이클의 00~06 문서를 쓸 언어 (기본: 표시 언어)",

    "cli.doctor.doctor": "SAGE 실행에 필요한 도구와 리뷰 설정을 점검합니다",
    "cli.doctor.profile": "project-profile.yaml 경로 (없으면 templates 기본)",

    "cli.fast_cycle.fast_cycle": "축약 PDCA Fast Cycle 감사를 시작·검증·종료합니다",
    "cli.fast_cycle.open": "composite Fast Plan을 감사 run에 결속합니다",
    "cli.fast_cycle.review": "APPROVED Loop Audit을 Fast run에 결속합니다",
    "cli.fast_cycle.close": "승인·보고 증거를 검증하고 Fast run을 종료합니다",
    "cli.fast_cycle.abort": "사유를 남기고 활성 Fast run을 중단합니다",
    "cli.fast_cycle.show": "Fast Cycle 감사 요약을 표시합니다",

    "cli.feedback.feedback": "sage-feedback 마커를 스캔해 보여줍니다",
    "cli.feedback.root": "프로젝트 루트(기본: profile 을 가진 상위 디렉토리)",
    "cli.feedback.blocking_only": "차단성(!sage-feedback) 마커만 표시",
    "cli.feedback.exit_code": "미해결 차단성 마커가 있으면 2 로 종료(스크립트·CI 용)",
    "cli.feedback.release_gate": "feedback.block_release 가 true 일 때만 미해결 차단성 마커로 2 종료 (릴리즈 CI 가 무조건 호출하고 판정은 프로필이 한다)",
    "cli.feedback.record": "마커 1건의 처리 결과를 기록한다(--path/--line/--verdict/--note 필요)",
    "cli.feedback.path": "--record: 마커가 있던 저장소 상대 경로",
    "cli.feedback.line": "--record: 마커 줄 번호",
    "cli.feedback.verdict": "--record: 3분기 판정 (fixed=수정함 | intentional=불일치 아님 | undetermined=판단 불가·마커 유지)",
    "cli.feedback.note": "--record: 판단 근거 한 줄(계획 문서의 어느 부분인지)",
    "cli.feedback.cycle_stem": "--record: 그 코드를 만든 사이클 stem(vault 노트 단위)",
    "cli.feedback.vault": "--record: vault 경로 오버라이드(생략 시 profile vault_path)",

    "cli.generate.generate": "spec 파일을 읽어 Claude/Codex용 설정 파일을 생성합니다",
    "cli.generate.id": "단일 자산 (없으면 kind 전체; roster 는 profile.components 에서 파생)",
    "cli.generate.write": "파일 기록 (없으면 dry-run 미리보기)",
    "cli.generate.target": "등록 대상 런타임 (both 는 cross_model on)",
    "cli.generate.dest": "등록 산출물 기록 루트 (기본 cwd)",
    "cli.generate.root": "SAGE 루트 (manifest 탐색)",
    "cli.generate.from_existing": "(--kind roster) 기존 implementer 의 렌더+프로젝트 오버레이를 새 implementer-<component> 정체성으로 시드한다(create-only). 예: implementer-a",
    "cli.generate.deploy_codex": "(--kind skill) repo .codex/skills 정본을 codex 전역 $CODEX_HOME/skills 에 배포(prefix 네임스페이스). codex 는 repo-스코프 skill 미자동발견 → 전역 배포해야 호출 가능. 명시적 opt-in(환경 부작용 분리).",

    "cli.install.install": "현재 프로젝트에 SAGE 기본 파일을 설치합니다",
    "cli.install.help": "도움말을 보여주고 종료합니다",
    "cli.install.host": "SAGE를 설치할 AI 도구를 선택합니다: claude 또는 codex (필수)",
    "cli.install.prefix": "자산 네이밍 prefix (선택, 기본값: sage)",
    "cli.install.dest": "설치 대상 프로젝트 루트 (선택, 기본값: 현재 디렉토리)",
    "cli.install.force": "기존 파일 덮어쓰기 (기본: skip)",
    "cli.install.skill_scope": "codex host: CORE skill 설치 위치를 명시적으로 선택 (필수: global 또는 project-local)",
    "cli.install.no_global_skill": "DEPRECATED codex CI/샌드박스 호환: CORE skill 설치를 완전히 생략",

    "cli.knowledge.knowledge": "Obsidian vault 사전조회/개발후 갱신을 실행합니다",
    "cli.knowledge.scan": "개발 전 vault 관련 노트를 조회하고 .sage/knowledge_scan.md 를 갱신합니다",
    "cli.knowledge.query": "조회할 작업/기능 설명",
    "cli.knowledge.query_file": "조회 문구를 읽을 파일(자유문자 shell 인자 주입 방지)",
    "cli.knowledge.profile": "project-profile.yaml 경로",
    "cli.knowledge.vault": "vault 경로 override. 경로 생략 시 profile.knowledge_capture.vault_path 사용",
    "cli.knowledge.limit": "최대 결과 수(기본 8)",
    "cli.knowledge.root": "프로젝트 루트 override",
    "cli.knowledge.write_back": "개발 완료 후 vault 노트와 wiki/log.md 를 갱신합니다",
    "cli.knowledge.title": "작성할 노트 제목",
    "cli.knowledge.summary": "요약 본문",
    "cli.knowledge.summary_file": "요약 본문을 읽을 파일(자유문자 shell 인자 주입 방지)",
    "cli.knowledge.profile_2": "project-profile.yaml 경로",
    "cli.knowledge.vault_2": "vault 경로 override. 경로 생략 시 profile.knowledge_capture.vault_path 사용",
    "cli.knowledge.prefix": "노트 prefix(기본 TECH)",
    "cli.knowledge.tags": "쉼표구분 태그(벌트 작성 가이드대로 host 가 제공; 미지정 시 기본 tech,sage,knowledge-capture)",
    "cli.knowledge.append_log": "wiki/log.md 에 wikilink 라인 추가",
    "cli.knowledge.skip_structure_check": "required_structure advisory 골격 검증을 끈다(L1 사소 노트·기획 인터뷰 등 심층 골격 대상이 아닌 노트용). risk tier·노트 종류 판단은 host 가 하고 CLI 는 그 결과만 결정론으로 반영한다(SAGE 경계)",
    "cli.knowledge.root_2": "프로젝트 루트 override",

    "cli.models.models": "host 모델 후보와 검증 출처를 표시합니다",
    "cli.models.codex_home": "Codex cache root (기본 CODEX_HOME 또는 ~/.codex)",

    "cli.override.override": "막힌 작업을 사유와 시간 제한을 남기고 임시로 허용합니다",
    "cli.override.reason": "우회 사유 (grant 시 필수 — 감사 기록)",
    "cli.override.ttl": "유효기간: 30m | 2h | 1d | 90s | 1800(초)",
    "cli.override.list": "활성 override + 최근 감사 요약",
    "cli.override.revoke": "활성 grant 를 만료 전에 회수 (--list 의 id)",
    "cli.override.root": "대상 프로젝트 루트 (기본 cwd)",

    "cli.retro.retro": "리뷰 사이클 학습을 자산 개선 제안으로 정리합니다(Loop C, 자동반영 없음)",
    "cli.retro.run_id": "대상 loop_audit run_id(기본: 최신)",
    "cli.retro.feature": "사이클 스템 — 05 문서 경로 필터 + human-gate 노트 제목. 예: loop-engineering",
    "cli.retro.vault": "Obsidian vault 에 human-gate 노트(approved:false) 작성. 경로 생략 시 profile.knowledge_capture.vault_path",
    "cli.retro.no_vault": "이번 실행만 vault 노트 생략(retro_note 플래그가 켜져 있어도). --vault 보다 우선",
    "cli.retro.check": "retro 노트가 실제로 채워졌는지 결정론 검사(빈 템플릿/무효 제안이면 non-zero). --run-id 를 함께 주면 그 run 의 노트인지도 대조",

    "cli.review.review": "Phase 05 same-runtime 리뷰(cross_model=false 경로)",
    "cli.review.packet_file": "리뷰 패킷(phase 문서 + 변경 파일) — active host headless stdin으로 전달",
    "cli.review.host": "현재 active host. profile 값과 충돌하면 실행 차단",
    "cli.review.cross_check": "Phase 05 cross-model 리뷰 — 반대 런타임 CLI 직접 호출",
    "cli.review.packet_file_2": "리뷰 패킷(변경 diff + 05 맥락) 파일 — peer 에게 전달할 프롬프트",
    "cli.review.host_2": "현재 실행 중인 host. env 판별이 모호할 때(중첩 실행 등) 필수",
    "cli.review.strict": "하위호환 플래그. reviewer 실패는 설정과 무관하게 BLOCKED/nonzero",

    "cli.review_loop.review_loop": "Loop A(Phase 05 적대적 리뷰) 라운드 감사를 기록·조회합니다",
    "cli.review_loop.open": "루프 시작 기록 → run_id 출력",
    "cli.review_loop.risk": "위험 tier(루프는 L2/L3 만)",
    "cli.review_loop.run_id": "명시 run_id(기본: 자동 발급)",
    "cli.review_loop.reviewer_requested": "의도한 리뷰어 모드(예: cross_model|same_runtime). close 의 --reviewer-actual 와 비교해 degraded 판정",
    "cli.review_loop.cycle_stem": "Fast Cycle 결속용 exact cycle stem",
    "cli.review_loop.lenses": "Fast Cycle 결속용 comma-separated 렌즈 목록",
    "cli.review_loop.round": "라운드 1건 기록(찾기/반박/채택 집계)",
    "cli.review_loop.found": "FIND 발견 수",
    "cli.review_loop.survived": "REFUTE 생존 수",
    "cli.review_loop.accepted": "REWORK 채택 수",
    "cli.review_loop.arch": "아키텍처 에스컬레이션 수",
    "cli.review_loop.tokens": "누적 토큰",
    "cli.review_loop.lens_receipts": "이번 라운드에 실제 완료한 comma-separated 렌즈 receipt",
    "cli.review_loop.close": "루프 종료 기록(result/reason/iterations)",
    "cli.review_loop.reviewer_actual": "실제 수행된 리뷰어 모드(예: cross_model|same_runtime). open 의 --reviewer-requested 와 다르면 degraded",
    "cli.review_loop.show": "루프 감사 요약(+무결성 점검). --vault 면 Obsidian 대시보드 노트도 작성",
    "cli.review_loop.run_id_2": "특정 run_id(미지정: 전체 요약)",
    "cli.review_loop.vault": "Obsidian vault 대시보드 작성. 경로 생략 시 profile.knowledge_capture.vault_path 사용",
    "cli.review_loop.next": "기록된 라운드 + profile cfg 로 계속/종료를 결정론 권고(감사 기록 안 함)",

    "cli.sync_overlays.sync_overlays": "오버레이 편집 후 CORE 렌더의 관리 블록을 다시 물리화합니다",
    "cli.sync_overlays.root": "SAGE 레포 루트 (기본: cwd 에서 탐색)",

    "cli.validate.validate": "spec과 생성 파일이 서로 어긋났는지 검사합니다",
    "cli.validate.check": "staleness 만 (regression 미실행, 빠른 CI/hook용)",
    "cli.validate.schema": "manifest 를 JSON Schema 로 구조검증 (jsonschema 선택의존, 미설치 시 WARN skip)",
    "cli.validate.strict": "안전 allowlist check-id의 WARN을 FAIL로 승격(CI 자산 무결성용)",
    "cli.validate.id": "단일 자산 검사",
    "cli.validate.root": "SAGE 레포 루트 (기본: cwd 에서 탐색)",

    # 정적 추출이 놓친 자리 — f-string 과 파서 속성 직접 대입.
    "cli.override.gate": "대상 게이트 ({gates}). 기본 all",
    "cli.install.optionals_title": "옵션",
    "cli.review.timeout": "headless 호출 상한 초(기본 {default})",
    "cli.review.timeout_peer": "peer 호출 상한 초(기본 {default})",
}
