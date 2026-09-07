"""bin/deputy 는 확장자 없는 실행 스크립트라 일반 import 가 안 된다.
파일 경로로 직접 로드해서 테스트가 내부 함수(consensus, validate_plan 등)에
접근할 수 있게 한다. 무거우므로 프로세스당 한 번만 로드해 캐시한다.
"""
import importlib.util
import os
from importlib.machinery import SourceFileLoader

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_ROOT, "bin", "deputy")

_cached = None


def load():
    global _cached
    if _cached is None:
        loader = SourceFileLoader("deputy_cli", _PATH)
        spec = importlib.util.spec_from_loader("deputy_cli", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        _cached = mod
    return _cached
