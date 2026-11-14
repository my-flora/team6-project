"""R5 架构/方案 Agent（Owner：范云娜，角色③ · 聚敛域）。

职责（规格书 阶段 3）：收敛生成建设草案（方案概述/架构/模块清单/选型/成本工期/风险）。
"""
from agents.roles.base import BaseAgent
from backend.core.enums import AgentRole


class ArchitectAgent(BaseAgent):
    AGENT_ROLE = AgentRole.ARCH
