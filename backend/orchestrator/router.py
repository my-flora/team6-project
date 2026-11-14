"""编排 HTTP 路由（T4）。

端点设计对齐第一部分 `backend/gate/router.py` 的风格；
请求体字段与 `contracts/*.schema.json` 保持一致，前端可直接复用 `AgentMessageRequest`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /orchestrator/start | 开题（进入当前阶段并打开首个议题） |
| POST | /orchestrator/messages | Agent 发言（走 GateService 门禁 + 轮次推进） |
| POST | /orchestrator/rounds/pull-back | 人类拉回主轴（清零重开） |
| POST | /orchestrator/rounds/converge | 人类强制收敛 |
| POST | /orchestrator/rounds/open | PM 重新开题 |
| POST | /orchestrator/rounds/tick | 时间盒巡检（前端 1s 轮询） |
| POST | /orchestrator/stages/advance | 阶段推进（E101/E102/E104/E105） |
| POST | /orchestrator/stages/freeze | 冻结基线（复用 T10） |
| POST | /orchestrator/project/resume | 人类处理完门禁后恢复运行 |
| GET  | /orchestrator/state | 看板所需全部信号（4.1） |
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.core.enums import Stage
from backend.core.models import AgentMessage
from backend.orchestrator.engine import Orchestrator
from backend.store import store

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])
orchestrator = Orchestrator(store)


class StartBody(BaseModel):
    project_id: str
    topic: str = Field(min_length=1, description="首个议题")


class PullBackBody(BaseModel):
    project_id: str
    reason: str = Field(min_length=1, description="拉回理由（4.2 必填）")
    new_topic: Optional[str] = None
    actor: str = "human"


class ConvergeBody(BaseModel):
    project_id: str
    reason: Optional[str] = None
    actor: str = "human"


class OpenTopicBody(BaseModel):
    project_id: str
    topic: str = Field(min_length=1)
    timebox_seconds: Optional[int] = None


class AdvanceBody(BaseModel):
    """StageAdvanceRequest（与 contracts/stage-advance.schema.json 对齐）。"""

    project_id: str
    current_stage: Stage
    target_stage: Stage
    human_prompt_input: str
    actor: str = "human"


class FreezeBody(BaseModel):
    project_id: str
    scope: str
    source_entry_ids: list[str] = Field(default_factory=list)
    human_prompt_input: str = "确认冻结基线"
    actor: str = "human"


class ResumeBody(BaseModel):
    project_id: str
    reason: str = "人工恢复"
    actor: str = "human"


@router.post("/start", summary="开题：进入阶段并打开首个议题")
def start(body: StartBody):
    return orchestrator.start(body.project_id, body.topic)


@router.post("/messages", summary="Agent 发言（契约校验 + 轮次推进 + 触顶自动收敛）")
def submit_message(msg: AgentMessage):
    return orchestrator.submit_message(msg)


@router.post("/rounds/pull-back", summary="拉回主轴：终止当前议题并清零重开")
def pull_back(body: PullBackBody):
    return orchestrator.pull_back(
        body.project_id,
        reason=body.reason,
        new_topic=body.new_topic,
        actor=body.actor,
    )


@router.post("/rounds/converge", summary="强制收敛（仅 ONGOING 可执行）")
def converge(body: ConvergeBody):
    return orchestrator.force_converge(body.project_id, reason=body.reason, actor=body.actor)


@router.post("/rounds/open", summary="PM 重新开题")
def open_topic(body: OpenTopicBody):
    return orchestrator.open_topic(body.project_id, body.topic, timebox_seconds=body.timebox_seconds)


@router.post("/rounds/tick", summary="时间盒巡检（到点自动强制收敛）")
def tick(project_id: str = Query(...)):
    return orchestrator.tick(project_id) or {"converged": False}


@router.post("/stages/advance", summary="阶段推进（门禁红点 / 空 Prompt / 待审条目拦截）")
def advance(body: AdvanceBody):
    return orchestrator.advance_stage(
        body.project_id,
        body.target_stage,
        body.human_prompt_input,
        actor=body.actor,
    )


@router.post("/stages/freeze", summary="冻结基线（三方会签全绿后黑板只读）")
def freeze(body: FreezeBody):
    return orchestrator.freeze_baseline(
        body.project_id,
        scope=body.scope,
        source_entry_ids=body.source_entry_ids,
        human_prompt_input=body.human_prompt_input,
        actor=body.actor,
    )


@router.post("/project/resume", summary="人类处理完门禁后恢复运行")
def resume(body: ResumeBody):
    return orchestrator.resume_project(body.project_id, reason=body.reason, actor=body.actor)


@router.get("/state", summary="看板快照（4.1 信号-字段映射的落地）")
def state(project_id: str = Query(...)):
    return orchestrator.snapshot(project_id)


@router.get("/events", summary="发言事件流（增量拉取）")
def events(
    project_id: str = Query(...),
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return orchestrator.events(project_id, after_seq=after_seq, limit=limit)
