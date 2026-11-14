"""本地联调入口：在**不修改** `backend/app.py` 的前提下，把第二部分路由挂上去。

    python demo_api.py           # 然后打开 http://127.0.0.1:8000/docs

正式合并时，只需要在 `backend/app.py` 里加两行（见 README 第 7 节），
这个文件就可以删掉。
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _bootstrap  # noqa: E402

_bootstrap.prepare()

from backend.app import app  # noqa: E402  第一部分的应用（gate / baseline）
from backend.blackboard.router import router as blackboard_router  # noqa: E402
from backend.orchestrator.router import router as orchestrator_router  # noqa: E402

app.include_router(blackboard_router)
app.include_router(orchestrator_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
