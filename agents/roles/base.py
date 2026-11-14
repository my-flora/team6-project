"""角色 Agent 基类 —— 脚手架（Owner：陈欣然，角色1）。

范云娜（③）与张吴博（④）实现具体角色时继承本类：
    - 只需实现 respond()：输入黑板上下文，输出发言文本；
    - 发言必须携带 references（引用的黑板条目 ID），空引用会被
      GateService E002 拦截 —— 在这里就提醒调用方传齐。
不内置大模型调用：课堂验收以确定性规则为主，接模型时替换 respond 内部实现即可。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Sequence

from backend.core.enums import AgentRole, Stage
from backend.core.models import BlackboardEntry


@dataclass
class AgentContext:
    """PM 调度后发给角色 Agent 的上下文包。"""
    project_id: str
    stage: Stage
    topic_id: str | None
    round_no: int
    # 本阶段可读的黑板条目（服务层已过滤：仅 EntryStatus=APPROVED）
    readable_entries: Sequence[BlackboardEntry]
    extra: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """角色 Agent 骨架。"""
    AGENT_ROLE: AgentRole

    def __init__(self, name: str = "") -> None:
        self.name = name or self.AGENT_ROLE.value

    @abstractmethod
    def respond(self, ctx: AgentContext) -> dict:
        """产出一次发言。

        返回结构（直接可交给 /orchestrator/messages 或黑板服务）：
            {
                "content": str,             # 发言文本
                "references": [entry_id],   # 必须引用本轮可读条目，不得为空
                "is_conflict": bool,        # 与他人观点冲突时标 True，进「待裁决」
            }
        """
        raise NotImplementedError
