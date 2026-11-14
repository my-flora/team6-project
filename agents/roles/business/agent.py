"""R2 商业分析 Agent（Owner：范云娜，角色③ · 发散域）。

职责（规格书 阶段 2）：评估市场与商业价值，从商业视角穷举机会与风险。
发言必须引用「初始上下文卡片」等 APPROVED 条目作为依据（3.1）。
实现：继承 agents.roles.base.BaseAgent，补全 respond()。
"""
from agents.roles.base import BaseAgent
from backend.core.enums import AgentRole


class BusinessAgent(BaseAgent):
    AGENT_ROLE = AgentRole.BA
