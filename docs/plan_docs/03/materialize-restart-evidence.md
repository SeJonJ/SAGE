# 새 R1 F01 원본 LF 보존 수리

Cycle-Stem: overlay-context-delivery
Document-Language: ko
Done-Criteria-Revision: 3

두 독립 refuter가 확인한F01은 rootcontext의routing블록 제거가 `_normalize_trailing`을통해외부LF까지바꾼다는반례다. 기존marker검증과legacyspancapabilityguard는유지하고두context분기만검증된routing문자열의정확1회replace로수정했다. 일반worker/routinghelper의기존정규화정책은변경하지않았다. 새함수/API/서비스/지속상태는없다.

양host회귀는routing블록뒤한국어사용자suffix와LF3개를두계획함수와실제materialize에서bytes로비교하고2차멱등성을확인한다. `f01-red.log`는신규1test/host2subtest실패(exit1),`f01-green.log`는전체materialize44testsPASS(exit0)다. localTMPDIR는restart증거폴더안이며SAGE자기승인/모델/커밋/실사용설치는실행하지않았다.

기존collector담당의194scoped실행은동시F01 RED2subfail를정확보존했다. 이후통합수정본에서전체회귀를다시실행하며이전실패를성공으로덮지않는다.
