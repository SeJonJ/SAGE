Cycle-Stem: q00-evidence-adoption
Document-Language: ko
Issue: https://github.com/SeJonJ/SAGE/issues/40

# Q00 원칙의 제한 적용 완료·릴리즈 인계

개발·일반/Windows 대상 검증·독립 검토를 마쳤다. 사용자 지시에 따라 문서 갱신→커밋/PR→CI 확인→머지→1.3.8 릴리즈→위키 갱신을 수행한다. 이 문서는 배포 전에 작성한 개발 완료 기록이며 아직 수행하지 않은 CI·게시를 성공으로 미리 적지 않는다. 실제 결과는 [PR](https://github.com/SeJonJ/SAGE/pulls), [tag workflow](https://github.com/SeJonJ/SAGE/actions/workflows/publish.yml), [v1.3.8 Release](https://github.com/SeJonJ/SAGE/releases/tag/v1.3.8), [PyPI1.3.8](https://pypi.org/project/sage-harness/1.3.8/)와 대조한다.

## 적용 결과

- 기존 인터뷰→01→QA 흐름에 요구 출처와 승인 계약 기반 기대값을 연결했다.
- configured check의 실행/생략 범위를 표시하고0실행은 NO_EVIDENCE로 구분한다. exit0을 요구 통과로 오해하지 않는다.
- 필수 실행 근거 부재는 해당 ID의 NOT TESTED로 남긴다. 기존 승인/waiver·실패 재시도 규칙을 유지한다.
- Windows의 지원 runner 경로 `/` 선언도 force 재설치에서 보존한다. 공유 YAML은 `/`를 권장한다.
- 다른 agent runtime 통합·새 DB/schema/gate/CLI·encoding 정책·자동 repair loop는 도입하지 않았다.

## 사용자가 갱신할 때

패키지를 올리는 것과 프로젝트 설치 자산을 갱신하는 것은 별개다. 설치된 문구·runner를 확인하고 기존 명시적 업데이트 절차를 따른다. non-force는 구 파일 보존/CORE trust 거부가 가능하다. 개인 runner는 새 출력 계약을 강제로 입히기 위해 덮어쓰지 않는다. Windows·구판·소유권 테스트와 그 한계는 [04](../04/q00-evidence-adoption.md), 독립 검토와 잔여는 [05](../05/q00-evidence-adoption.md)를 확인한다.

SAGE 엔진이 자기 gate/review-loop/waiver로 자기 변경을 승인하지 않도록00~06 기록 구조만 차용했다. 제품 CLI는 격리 consumer 테스트에만 사용했고 판단 근거는 사용자 지시·일반 테스트·독립 리뷰다.
