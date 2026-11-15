"""应用入口：T3 门禁校验 + T10 基线接口的最小可运行组合（供 T11 联调）。

启动：uvicorn backend.app:app --reload --port 8000
"""
from fastapi import FastAPI

from backend.baseline.router import router as baseline_router
from backend.blackboard.router import router as blackboard_router
from backend.gate.router import router as gate_router
from backend.orchestrator.router import router as orchestrator_router
from backend.stages.router import router as stages_router
from backend.stages.router import router as stages_router

app = FastAPI(
    title="Virtual Project Room - Contracts & Gate API",
    version="1.0.0",
    description="角色1（契约与门槛）：T1 数据模型 / T3 门禁与契约校验 / T10 基线冻结与变更申请",
)

app.include_router(gate_router)
app.include_router(baseline_router)
app.include_router(blackboard_router)
app.include_router(orchestrator_router)
app.include_router(stages_router)
app.include_router(stages_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "owner": "chen-xinran", "contracts_version": "1.0"}
