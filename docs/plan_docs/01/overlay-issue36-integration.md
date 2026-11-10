# 통합 수용·검증 매트릭스

Cycle-Stem: overlay-issue36-integration
Document-Language: ko
Risk Level: L3
Done-Criteria-Revision: 1
Status: VERIFIED

| ID | 필수 근거 |
|---|---|
| I1 | stash SHA/ref, 102파일 hash/mode, 원본 #36 manifest, rollback guard |
| I2 | 3-way merge 기록, 기존 AST 테스트 보존, docs source digest |
| I3 | legacy hook fixture에 양 host CORE·shared/personal Standard/Fast 입력을 조합한 실제 CLI/collector 경계 |
| I4 | 기존 #36 global rollback 및 overlay dual-local failure 테스트, 통합 반례 추가 시 red/green |
| I5 | run-all, clean installed wheel, bundle metadata; local/remote 구분 |
| I6 | 5 host lens+Claude peer, 전체라운드 refuter2, frozen delta/source/usage |

원래 overlay native/model 표본은 변경없는 함수/CORE와 정확 byte 연결이 있을 때만 보존 근거로 사용한다. 새 실제 모델 호출/전OS 재검증으로 확대하지 않는다.


2026-11-10 위 I1~I6을 같은stem04의 근거와05 독립 검토 결과로 확인했다. 필수 기준과 revision1은 변경하지 않았다. Windows 전체·출시 준비를 이 표의 추가 PASS로 주장하지 않는다.
