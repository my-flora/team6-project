"""基线冻结与变更申请 HTTP 路由（T10 接口）。"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.baseline.service import BaselineService
from backend.store import store

router = APIRouter(prefix="/baseline", tags=["baseline"])
service = BaselineService(store)


class FreezeBody(BaseModel):
    project_id: str
    scope: str
    source_entry_ids: list[str] = []


class ChangeRequestBody(BaseModel):
    baseline_id: str
    description: str
    impact_scope: str = ""
    impact_cost: str = ""
    impact_schedule: str = ""


class ChangeDecisionBody(BaseModel):
    cr_id: str
    approved: bool
    decided_by: str


@router.post("/freeze", summary="冻结基线（校验三方会签全绿；冻结后黑板只读）")
def freeze(body: FreezeBody):
    baseline = service.freeze_baseline(body.project_id, body.scope, body.source_entry_ids)
    return {
        "baseline_id": baseline.id,
        "version": baseline.version,
        "frozen_at": baseline.frozen_at.isoformat(),
        "project_status": "FROZEN",
        "blackboard": "READ_ONLY",
    }


@router.post("/change-requests", summary="提交变更申请（须附影响评估：范围/成本/工期）")
def submit_cr(body: ChangeRequestBody):
    cr = service.submit_change_request(
        body.baseline_id, body.description,
        body.impact_scope, body.impact_cost, body.impact_schedule,
    )
    return {"cr_id": cr.id, "status": cr.status.value}


@router.post("/change-requests/decision", summary="审批变更申请（批准后版本 +1 并通知干系人）")
def decide_cr(body: ChangeDecisionBody):
    cr = service.decide_change_request(body.cr_id, body.approved, body.decided_by)
    return {"cr_id": cr.id, "status": cr.status.value, "decided_by": cr.decided_by}
