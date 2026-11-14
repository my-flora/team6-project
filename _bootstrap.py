"""本地运行引导。

第二部分是"覆盖进仓库"的交付物，依赖第一部分的 `backend.core` 等包。
本文件负责三件事：

1. 把仓库根目录放进 `sys.path`（兼容"本目录就是仓库根"和"本目录是子目录"两种布局）；
2. 如果本机没装 `pydantic` / `fastapi`，临时挂上 `tests/stubs` 里的轻量桩，
   让单测与 demo 在没有依赖的机器上也能跑；
   注意：桩只在**真实包缺失**时启用，仓库里装了真依赖时永远不会生效；
3. 给出清晰的报错，提示"先把本目录合并进仓库"。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUBS = ROOT / "tests" / "stubs"

_MISSING_DEPS: list[str] = []


def _has_package(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def prepare() -> str:
    """返回契约来源说明，供 demo / 测试打印。"""
    for candidate in (ROOT, ROOT.parent):
        if (candidate / "backend" / "core" / "enums.py").exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break
    else:
        raise RuntimeError(
            "找不到第一部分 /backend/core/enums.py。\n"
            "第二部分需要和第一部分合并后才能运行：请把本目录下的 backend/、agents/ "
            "覆盖到 team6-project 仓库根目录，然后在仓库根目录执行 python run_tests.py。"
        )

    for package in ("pydantic", "fastapi"):
        if not _has_package(package):
            _MISSING_DEPS.append(package)

    if _MISSING_DEPS:
        if str(STUBS) not in sys.path:
            sys.path.insert(0, str(STUBS))
        return "stub(" + ",".join(_MISSING_DEPS) + ")"
    return "repo"

