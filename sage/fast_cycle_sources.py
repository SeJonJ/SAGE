"""엔진측 loader — Fast Cycle 소스 provenance 검증.

정본은 `scripts/sage_harness/hooks/fast_cycle_sources.py` 다. 이 파일은 그 모듈의 공개 이름을
그대로 올려, 기존 `from sage.fast_cycle_sources import ...` 호출부가 바뀌지 않게 한다.
왜 hook 트리가 정본인지는 `sage/_hook_contract.py` 에 있다.
"""
from sage._hook_contract import reexport as _reexport

_reexport(globals(), "fast_cycle_sources")
