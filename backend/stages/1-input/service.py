"""T5: 结构化输入（负责人③范云娜）。

输出通过现有 T2 黑板服务创建并进入 PENDING_REVIEW；不重复定义全局状态枚举。
"""
from __future__ import annotations
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.blackboard.service import BlackboardService
from backend.core.enums import AgentRole, Stage
from backend.core.models import BlackboardEntry, HumanGate


class RiskRegisterItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    type: str = Field(min_length=1, description="风险类型")
    severity: Literal["高", "中", "低"]
    trigger_condition: str = Field(min_length=1, description="触发条件")
    source: str = Field(min_length=1, description="来源卡片或提出者")
    needs_human_decision: bool
    description: str = ""

    @field_validator("type", "trigger_condition", "source")
    @classmethod
    def no_blank_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("此字段不能为空")
        return value


class StructuredInputRequest(BaseModel):
    project_id: str = Field(min_length=1)
    core_goal: str = Field(min_length=1, description="核心目标")
    target_audience: str = Field(min_length=1, description="目标受众")
    desired_boundary: str = Field(min_length=1, description="期望边界")
    success_criteria: str = Field(min_length=1, description="成功判据")
    value_proposition: str = Field(min_length=1, description="价值主张")
    risk_register: list[RiskRegisterItem] = Field(default_factory=list, description="待补充风险登记区")
    references: list[str] = Field(default_factory=list)
    actor: str = "human"

    @field_validator("core_goal", "target_audience", "desired_boundary", "success_criteria", "value_proposition")
    @classmethod
    def required_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("必填字段不能为空")
        return value


class StructuredInputService:
    def __init__(self, blackboard: BlackboardService) -> None:
        self.blackboard = blackboard

    def submit(self, request: StructuredInputRequest) -> tuple[BlackboardEntry, HumanGate]:
        content = request.model_dump(exclude={"project_id", "actor", "references"}, by_alias=True)
        entry = self.blackboard.create_entry(
            request.project_id,
            stage=Stage.IDEA,
            source_agent=AgentRole.HUMAN,
            content=json.dumps(content, ensure_ascii=False),
            references=request.references,
            actor=request.actor,
        )
        return self.blackboard.submit_for_review(entry.id, actor=request.actor)
