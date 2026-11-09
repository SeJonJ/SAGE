# 통합 QA와 수용 근거

Cycle-Stem: overlay-issue36-integration
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: LOCAL_VERIFICATION_EXECUTED — Windows baseline failures / candidate CI NOT_TESTED / independent review BLOCKED

| ID | 결과 | 근거 |
|---|---|---|
| I1 | PASS | stash102blob hash/mode·namedref, guard14경로·sandbox복구, #36 원본drift0 |
| I2 | PASS | 3-way10경로, 양쪽 test method AST보존, 문서digest |
| I3 | PASS | 통합3회귀와 실제v1.0설치→최종wheel3조합, 양hosthook_entry·2/4catalog·legacy유지·reapply |
| I4 | PASS | 기존89upgrade/53layout, 새dual-local/globalprimary+secondarylocal후반실패 bytes/mode복원 |
| I5 | PASS | 전체4149Ran(13skip), 실패오류0/exit0; wheel217동일, sdist검사 |
| I6 | NOT_TESTED | 독립 L3 검토 예정 |

독립QA 원문 qa-independent.json은 전체 runner 종료 전 I5를PARTIAL로 보존한다. 위I5는 이후full-summary.json의 실제exit0/ALL PASS와 loghash를 따른다. local 결과를 원격CI/다른OSmatrix/native모델재실행으로 승격하지 않는다. 제품 결함은 이번 기능·QA 단계에서 확인되지 않았다. release/mainmerge는 아직 미실행이다.

## 독립 QA 최종 확인

qa-independent.json LOCAL_QA_COMPLETE가 whole4149/13skip/0fail·exit0 및sdist/217source를직접검산했다. I6은유효한Claude결과·반박2명미완료로NOT_TESTED를유지하며05예산초과BLOCKED다. 기능PASS는독립승인/출시PASS가아니다.


## 2026-11-07 Windows → macOS → CI 후속 검증

위4149/13skip표는통합직후Mac로컬의역사적결과다. 후속플랫폼실행은별도원본/R2로보존하며Windows전체PASS로승격하지않는다.

- Windows11 Python3.12: 전체114script/4149Ran/61skip.94script exit0/20nonzero.112실패이벤트중104는8e17a88에서38대조명령으로재현,8은테스트가정3파일수정후3Python버전에서해당사례PASS. Windows전체baseline/R2전체는미실행.
- Windows3.10/3.11: 각8핵심suite/333Ran/3skip. 3.11layout최초fixture os.rename WinError5 1건은원본보존;단독현재2회/기존1회및전체53재실행PASS이나원인미확인. 기존materialize경로/mode실패도분리보존.
- 설치wheel: Windows3버전각10case smoke/실제v1.0소비자3조합PASS. 최종wheel별도venv312재확인10/3PASS. Mac최종wheel10/3PASS. 실제모델세션재검증이아니라설치CLI/publichook_entry/업그레이드·globalrollback수용범위다.
- Mac Python3.11.6: 전체114script/4150Ran/15skip/실패오류0,exit0. 기존13skip에Windows전용1과venv user-site비활성1추가. user-site사례는별도global Python에서1test/0skip PASS. 원본15skip유지.
- 제품217파일은플랫폼검증중불변.3테스트파일만Windows가정수정. 제품hash205ba39f9b2f587573fb44c31f313a2f3c7975a2dabc1e2d6b9941785282ae70. source/installed/live217map동일. 최종wheel64d7a8a5577228aaeb81d6d8dbff6a889dd8afe8c266653afa1cf61ba08c7cfd. 이전wheel과4개동봉테스트본문+RECORD만다르며실행제품entry는모두동일.
- 새로확인한기존제품결함WIN-PHASE4-01: Windows03문서경로namespace불일치때문에Phase4체크리스트게이트가차단대신경고통과. 이전/현재source·현재설치wheel/양host재현. 원래overlay3가지범위밖이며수정여부별도사용자판단대기. 제품수정미적용. 위초기QA의제품결함미확인문장은후속관찰을포함하지않는다.
- GitHub조회: 현재main8e17a88의마지막CI는13success/1Windows skipped. 현통합후보는미커밋local patch이며원격branch/PR/run없음. 후보CI NOT_TESTED. 기존main성공으로대체하지않는다.
- #36원본10파일drift0,stash/namedref유지,guard19경로. 독립리뷰BLOCKED/새model review0/통합06미작성/commit·push·mainmerge·release미실행.

근거: sibling evidence root `overlay-issue36-platform-20261107/REPORT.md`, platform-summary.json, windows-evidence.zip322파일SHA, mac-stage-reviewed.json, ci-stage-reviewed.json. 예산·원본stash·guard는기존통합evidence root를유지한다.
