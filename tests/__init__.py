"""第二部分测试包。

负责把仓库根目录加入 sys.path；如果本机没装 pydantic / fastapi，
再挂上 tests/stubs 的轻量桩（只在真实包缺失时生效，合并进仓库后不会劫持真依赖）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUBS = Path(__file__).resolve().parent / "stubs"


def _missing(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is None
    except (ImportError, ValueError):
        return True


if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if _missing("pydantic") or _missing("fastapi"):
    if str(STUBS) not in sys.path:
        sys.path.insert(0, str(STUBS))
