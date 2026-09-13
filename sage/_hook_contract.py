"""엔진이 hook 트리의 의존 없는 계약 모듈을 읽는 단일 통로.

**정본은 hook 트리에 있다.** 게이트 판정에 쓰이는 파싱·해시 계약은 소비 프로젝트에 물리화된
사본에서도 엔진 패키지 없이 돌아야 한다(hook 런타임의 standalone 계약). 그래서 알고리즘은
`scripts/sage_harness/hooks/` 가 소유하고, 엔진은 그것을 **읽는 쪽**이 된다.

방향을 반대로 잡으면 — hook 이 `sage.*` 를 import 하면 — 물리화된 사본이 엔진 설치 여부에
묶인다. 그 상태에서 import 가 실패하면 게이트는 판정을 내지 못하고 죽으며, 크래시의 종료코드는
차단이 아니라 통과로 읽힌다. 실제로 그렇게 되어 있었다.

사본을 두는 선택지는 없다. 같은 알고리즘이 두 벌 있으면 두 벌이 갈라지는 날이 오고, 그날
엔진의 판정과 hook 의 판정이 다르다. `checklist_contract` 가 같은 이유로 같은 방향을 쓴다.

hook 디렉터리를 `sys.path` 에 넣는 이유는 계약 모듈끼리 형제 이름으로 서로를 부르기 때문이다
(`fast_cycle_contract` ↔ `done_criteria_contract`). 그 이름 해석이 성립해야 hook 프로세스와
엔진이 **같은 모듈 그래프**를 본다.
"""
import importlib
import sys


def load(module_name):
    """hook 트리의 계약 모듈 하나를 반환. 두 번째 호출부터는 `sys.modules` 캐시를 쓴다."""
    from sage import _resources
    source = _resources.hooks_src_dir()
    if source not in sys.path:
        sys.path.insert(0, source)
    return importlib.import_module(module_name)


def reexport(namespace, module_name):
    """계약 모듈의 공개 이름을 호출한 모듈의 namespace 로 올린다 → 로드된 모듈.

    엔진 호출부는 `from sage.done_criteria_contract import parse_done_criteria` 처럼 계속 쓴다.
    이관 때문에 호출부 수십 곳을 고치면, 다음에 정본이 한 번 더 움직일 때 또 고쳐야 한다.
    """
    module = load(module_name)
    namespace.update({name: value for name, value in vars(module).items()
                      if not name.startswith("_")})
    return module
