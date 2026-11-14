"""核心实体模型 —— T1 交付物。

来源：《第6组-虚拟项目室设计规格书》1.2 数据模型 + 4.1 信号-字段映射。
实体只定义结构与状态，不含业务规则；业务规则在 gate / orchestrator / baseline 等服务中实现。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .enums import (
    AgentRole,
    EntryStatus,
    GateStatus,
    ProjectStatus,
    RoundStatus,
    Stage,
    StageStatus,
    MAX_ROUNDS,
)


class Project(BaseModel):
    """项目（可视化映射：Project.current_stage → 阶段进度条）"""
    id: str
    name: str
    status: ProjectStatus = ProjectStatus.RUNNING
    current_stage: Stage = Stage.IDEA
    stage_status: StageStatus = StageStatus.NOT_STARTED
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BlackboardEntry(BaseModel):
    """共享黑板条目（信息流转规则：所有 Agent 发言必须写入黑板并标注来源/阶段/状态）"""
    id: str
    project_id: str
    stage: Stage
    source_agent: AgentRole
    content: str
    status: EntryStatus = EntryStatus.DRAFT
    is_conflict: bool = False           # 冲突高亮标签（4.1）
    references: list[str] = Field(default_factory=list)  # 引用的上游条目 ID


class AgentMessage(BaseModel):
    """Agent 发言记录（AgentMessageRequest 落库后的形态）"""
    id: str
    project_id: str
    stage: Stage
    agent_role: AgentRole
    topic_id: Optional[str] = None
    round_no: int = Field(default=1, ge=1, le=MAX_ROUNDS)
    content: str
    references: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DiscussionRound(BaseModel):
    """议题轮次（可视化映射：round_no/max_rounds → 议题与轮次提示；timebox_end → 时间盒倒计时）"""
    id: str
    project_id: str
    topic: str
    round_no: int = Field(default=1, ge=1, le=MAX_ROUNDS)
    max_rounds: int = MAX_ROUNDS
    status: RoundStatus = RoundStatus.ONGOING
    timebox_end: Optional[datetime] = None


class HumanGate(BaseModel):
    """人类门禁（可视化映射：count(GateStatus=PENDING) → 门禁待办红点）"""
    id: str
    project_id: str
    stage: Stage
    entry_id: str                       # 待审黑板条目
    gate_status: GateStatus = GateStatus.PENDING
    reason: Optional[str] = None        # 驳回必须填 reason
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Signoff(BaseModel):
    """三方电子会签：业务 / 开发 / 测试，三项并行，不可一人代签"""
    id: str
    project_id: str
    party: str                          # "business" | "development" | "testing"
    status: EntryStatus = EntryStatus.DRAFT
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None


class Baseline(BaseModel):
    """需求基线：冻结后打版本号并记录日期与冻结范围，黑板进入只读 + 变更申请状态"""
    id: str
    project_id: str
    version: str                        # 如 "V1.0"
    frozen_at: datetime = Field(default_factory=datetime.utcnow)
    scope: str                          # 冻结范围说明
    source_entry_ids: list[str] = Field(default_factory=list)


class ChangeRequest(BaseModel):
    """变更请求：基线后变更须提交 → 影响评估（范围/成本/工期）→ 审批 → 按版本更新基线"""
    id: str
    baseline_id: str
    project_id: str
    description: str
    impact_scope: str = ""
    impact_cost: str = ""
    impact_schedule: str = ""
    status: EntryStatus = EntryStatus.DRAFT   # DRAFT(待提交) / PENDING_REVIEW(待审批) / APPROVED / REJECTED
    decided_by: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
