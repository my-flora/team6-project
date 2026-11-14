"""门禁与契约校验 HTTP 路由（T3）。"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.enums import EntryStatus, GateStatus, Stage
from backend.core.models import AgentMessage
from backend.gate.service import GateService
from backend.store import store

router = APIRouter(prefix="/gate", tags=["gate"])
gate_service = GateService()


class StageAdvanceBody(BaseModel):
    """StageAdvanceRequest 请求体（对应 contracts/stage-advance.schema.json）"""
    project_id: str
    current_stage: Stage
    target_stage: Stage
    human_prompt_input: str


class GateDecisionBody(BaseModel):
    gate_id: str
    decision: GateStatus
    reason: Optional[str] = None


@router.post("/messages/validate", summary="AgentMessageRequest 契约校验（拦截空引用）")
def validate_agent_message(msg: AgentMessage):
    project = store.get_project(msg.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "E404", "message": "项目不存在"})
    entries = {e.id: e for e in store.get_entries(msg.project_id)}
    gate_service.validate_agent_message(msg, entries, project)
    return {"valid": True, "code": "OK"}


@router.post("/advance/validate", summary="StageAdvanceRequest 校验（拦截空人类输入）")
def validate_stage_advance(body: StageAdvanceBody):
    project = store.get_project(body.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "E404", "message": "项目不存在"})
    gate_service.validate_stage_advance(project, body.target_stage, body.human_prompt_input)
    return {"valid": True, "code": "OK"}


@router.post("/decision", summary="人类门禁裁决（APPROVED/REJECTED，驳回必填 reason）")
def gate_decision(body: GateDecisionBody):
    gate = store.get_gate(body.gate_id)
    if gate is None:
        raise HTTPException(status_code=404, detail={"code": "E404", "message": "门禁不存在"})
    gate = gate_service.decide_gate(gate, body.decision, body.reason or "")
    entry = store.get_entry(gate.entry_id)
    if entry is not None:
        entry.status = (
            EntryStatus.APPROVED if body.decision == GateStatus.APPROVED
            else EntryStatus.REJECTED
        )
    return {"gate_id": gate.id, "gate_status": gate.gate_status.value, "entry_status": entry.status.value if entry else None}
