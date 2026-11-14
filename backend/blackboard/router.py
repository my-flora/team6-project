"""黑板 HTTP 路由（T2）。

风格与 `backend/gate/router.py` 保持一致：模块级单例服务 + Pydantic 请求体，
错误由 `backend.errors.ApiError`（HTTPException 子类）直接抛出，
响应体统一是 FastAPI 默认的 `{"detail": {"code", "message"}}`。
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.blackboard.service import BlackboardService
from backend.core.enums import AgentRole, GateStatus, Stage
from backend.store import store

router = APIRouter(prefix="/blackboard", tags=["blackboard"])
blackboard_service = BlackboardService(store)


class CreateEntryBody(BaseModel):
    """新建黑板条目（一律落为 DRAFT）。"""

    project_id: str
    stage: Stage
    source_agent: AgentRole
    content: str = Field(min_length=1, description="条目正文")
    references: list[str] = Field(default_factory=list, description="引用的上游条目 ID")
    actor: Optional[str] = None


class UpdateEntryBody(BaseModel):
    content: str = Field(min_length=1)
    actor: str = "human"


class GateDecisionBody(BaseModel):
    decision: GateStatus
    reason: Optional[str] = None
    actor: str = "human"


class ConflictBody(BaseModel):
    note: str = Field(min_length=1, description="冲突点说明（4.1 橙色 ⚠ 标签）")


class ResolveBody(BaseModel):
    decision: str = Field(min_length=1, description="人类拍板的裁决理由")
    actor: str = "human"


@router.post("/entries", summary="新建黑板条目（DRAFT）")
def create_entry(body: CreateEntryBody):
    entry = blackboard_service.create_entry(
        body.project_id,
        stage=body.stage,
        source_agent=body.source_agent,
        content=body.content,
        references=body.references,
        actor=body.actor,
    )
    return entry.model_dump()


@router.get("/entries", summary="按项目/阶段查询黑板条目（状态门槛生效）")
def list_entries(
    project_id: str = Query(...),
    stage: Optional[Stage] = Query(default=None),
):
    entries = blackboard_service.list_entries(project_id, stage=stage)
    return {"items": [entry.model_dump() for entry in entries]}


@router.get("/entries/{entry_id}/history", summary="条目审计链（状态流转留痕）")
def entry_history(entry_id: str):
    return {"entry_id": entry_id, "history": blackboard_service.history(entry_id)}


@router.patch("/entries/{entry_id}", summary="修改条目正文（仅 DRAFT）")
def update_entry(entry_id: str, body: UpdateEntryBody):
    return blackboard_service.update_content(entry_id, body.content, actor=body.actor).model_dump()


@router.post("/entries/{entry_id}/submit", summary="提交审核：DRAFT→PENDING_REVIEW 并生成门禁")
def submit_entry(entry_id: str, actor: str = Query(default="human")):
    entry, gate = blackboard_service.submit_for_review(entry_id, actor=actor)
    return {
        "entry": entry.model_dump(),
        "gate_id": gate.id,
        "gate_status": gate.gate_status.value,
    }


@router.post("/entries/{entry_id}/reopen", summary="驳回后重开：REJECTED→DRAFT")
def reopen_entry(entry_id: str, reason: Optional[str] = Query(default=None), actor: str = Query(default="human")):
    return blackboard_service.reopen(entry_id, reason=reason, actor=actor).model_dump()


@router.delete("/entries/{entry_id}", summary="删除条目（仅未提交的 DRAFT）")
def delete_entry(entry_id: str, actor: str = Query(default="human")):
    blackboard_service.delete_entry(entry_id, actor=actor)
    return {"deleted": True, "entry_id": entry_id}


@router.post("/entries/{entry_id}/conflict", summary="标记冲突（4.1 橙色待裁决标签）")
def mark_conflict(entry_id: str, body: ConflictBody):
    entry = blackboard_service.mark_conflict(entry_id, body.note)
    return entry.model_dump()


@router.post("/entries/{entry_id}/resolve", summary="冲突拍板（清除标记并留痕）")
def resolve_conflict(entry_id: str, body: ResolveBody):
    return blackboard_service.resolve_conflict(entry_id, body.decision, actor=body.actor).model_dump()


@router.post("/gates/{gate_id}/decision", summary="人类门禁裁决（驳回必填 reason）")
def decide_gate(gate_id: str, body: GateDecisionBody):
    gate, entry = blackboard_service.decide_gate(
        gate_id,
        body.decision,
        reason=body.reason,
        actor=body.actor,
    )
    return {
        "gate_id": gate.id,
        "gate_status": gate.gate_status.value,
        "entry_status": entry.status.value if entry else None,
    }


@router.get("/stats", summary="黑板统计（4.1 四色状态 / 冲突数 / 只读标记）")
def stats(project_id: str = Query(...)):
    return blackboard_service.stats(project_id)
