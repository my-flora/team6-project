"""T5-T7 routes for role ③ 发散域; reuses the shared T2/T4 service instances."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.blackboard.router import blackboard_service
from backend.orchestrator.router import orchestrator

router = APIRouter(prefix="/stages", tags=["stages-1-3"])
ROOT = Path(__file__).parent


def _load_service(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载阶段服务：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Folder names mirror the team split table: backend/stages/{1-input,2-discussion,3-proposal}.
_t5 = _load_service("backend.stages._t5_service", ROOT / "1-input" / "service.py")
_t6 = _load_service("backend.stages._t6_service", ROOT / "2-discussion" / "service.py")
_t7 = _load_service("backend.stages._t7_service", ROOT / "3-proposal" / "service.py")

input_service = _t5.StructuredInputService(blackboard_service)
discussion_service = _t6.DiscussionStageService(blackboard_service, orchestrator)
proposal_service = _t7.ProposalService(blackboard_service)


class DiscussionRunRequest(BaseModel):
    project_id: str = Field(min_length=1)
    actor: str = "R1"


class ProposalGenerateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    source_entry_ids: list[str] = Field(min_length=2)
    actor: str = "R5"


class ProposalTrimRequest(BaseModel):
    project_id: str = Field(min_length=1)
    item_id: str = Field(min_length=1)
    action: str = Field(pattern="^(keep|exclude)$")
    reason: str = ""
    actor: str = "human"


def _bad_request(exc: ValueError):
    raise HTTPException(status_code=400, detail={"code": "S301", "message": str(exc)}) from exc


@router.post("/1-input", summary="T5 结构化输入并提交人类门禁")
def submit_structured_input(body: _t5.StructuredInputRequest):
    try:
        entry, gate = input_service.submit(body)
        return {"entry": entry.model_dump(), "gate_id": gate.id,
                "gate_status": gate.gate_status.value}
    except ValueError as exc:
        _bad_request(exc)


@router.post("/2-discussion/run-round", summary="T6 执行当前轮 R2-R5 讨论、去重并登记风险")
def run_discussion_round(body: DiscussionRunRequest):
    try:
        return discussion_service.run_round(body.project_id, actor=body.actor)
    except ValueError as exc:
        _bad_request(exc)


@router.post("/3-proposal/generate", summary="T7 生成七章方案草案")
def generate_proposal(body: ProposalGenerateRequest):
    try:
        entry = proposal_service.generate(body.project_id, body.source_entry_ids, actor=body.actor)
        return {"entry": entry.model_dump(), "required_chapters": 7,
                "trim_items": json.loads(entry.content).get("trim_items", [])}
    except ValueError as exc:
        _bad_request(exc)


@router.post("/3-proposal/{entry_id}/trim", summary="T7 保留或剔除方案项；剔除理由必填并归档")
def trim_proposal(entry_id: str, body: ProposalTrimRequest):
    try:
        entry = proposal_service.trim(body.project_id, entry_id, item_id=body.item_id,
                                      action=body.action, reason=body.reason, actor=body.actor)
        return {"entry": entry.model_dump(),
                "trim_archive": json.loads(entry.content).get("trim_archive", [])}
    except ValueError as exc:
        _bad_request(exc)


@router.post("/3-proposal/{entry_id}/submit", summary="提交裁剪完成的方案进入门禁")
def submit_proposal(entry_id: str, actor: str = "human"):
    try:
        entry, gate = blackboard_service.submit_for_review(entry_id, actor=actor)
        return {"entry": entry.model_dump(), "gate_id": gate.id,
                "gate_status": gate.gate_status.value}
    except ValueError as exc:
        _bad_request(exc)
