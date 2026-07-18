# [Design] SAGE-FB-10 Codex rename 목적지 L3 분류 우회 차단

Cycle-Stem: `sage-fb-10-codex-rename-risk`

## 1. Parser State

`extract_changes`는 현재 marker가 가리키는 단일 `cur` 대신, 이후 `+` line을 귀속할
`content_targets` 목록을 유지한다.

1. Add/Update/Delete marker를 만나면 source change를 만들고 `content_targets=[source]`로 재설정한다.
2. Move marker를 만나면 destination change를 추가하고, source에 이미 누적된 content를 destination에 backfill한다.
3. Move가 source marker 뒤라면 destination도 `content_targets`에 추가한다.
4. 이후 `+` line은 모든 target에 동일하게 누적한다.
5. Move가 단독으로 나타나면 destination을 독립 target으로 보존한다.

## 2. Why Duplicate Added Content

위험 분류기는 change 단위로 path와 content를 함께 판정한다. rename 뒤 patch 내용이 source에만
남으면 destination의 domain/path와 새 content의 조합을 잃을 수 있다. source와 destination에 같은
추가 내용을 연결하면 두 경로 각각에 대해 보수적으로 분류하고, 최종 `max`가 높은 위험도를 선택한다.

## 3. Invariants

- change order는 patch marker order를 유지한다.
- path는 기존과 동일하게 `rel()`을 거친다.
- source op는 `update`, destination op는 `move`다.
- 동일 최고 위험도의 여러 change가 있으면 trigger provenance를 합쳐 filename-L3/content-L3를 모두 보존한다.
- filename-L3 change가 하나라도 있으면 `is_l3_filename`과 operator-facing `file_short`는 해당 경로를 가리킨다.
- operator-facing `reason`은 대표 `file_short`와 같은 change의 사유만 유지한다. 다른 파일의 trigger는
  gate용 aggregate에 남기되 메시지에서 대표 파일의 사유로 잘못 귀속하지 않는다.
- 삭제 line과 context line은 content classification 입력에 포함하지 않는 기존 계약을 유지한다.
- post-tool logger의 schema는 변경하지 않는다.

## 4. Alternatives Rejected

- destination path로 source를 대체: 출발지 위험을 잃는다.
- destination을 content 없이 추가: 단순 glob 우회는 막지만 path+content 조합 의미가 불완전하다.
- logger extractor를 pre-gate에서 재사용: logger 출력에는 content가 없어 content-L3 계약을 충족하지 못한다.

## 5. Claude Review R1 Design Correction

- Move marker가 hunk 뒤에 나타나는 순서도 fail-safe하게 처리하기 위해 destination 생성 시 source의 기존
  content를 복사한다. marker 뒤의 추가 line은 기존 target fan-out으로 계속 양쪽에 누적한다.
- change별 rank가 같더라도 security provenance가 같다는 뜻은 아니다. `classify_risk`는 최고 rank를
  선택하되 동일 rank의 trigger source를 ordered union하고, filename-L3 경로를 operator-facing 대표로
  우선한다.

## 6. Claude Review R2 Design Correction

- filename glob으로 이미 L3가 된 동일 change도 content-L3 keyword가 있으면 provenance에
  `content_l3`를 함께 기록한다.
- equal-rank aggregate는 gate trigger만 union한다. 대표 경로가 바뀔 때만 그 경로의 reason으로 교체하며,
  서로 다른 파일의 reason 문자열을 합치지 않는다.
- `decide()` 수준에서 filename-L3와 enforced content-L3가 plan 없이 BLOCK되는지 고정한다.
- L0/L3 overlap precedence는 SAGE-FB-07로 유지하고 이번 acceptance 문구에서 경계를 명시한다.
