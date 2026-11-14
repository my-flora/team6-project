"""R4 技术挑刺 Agent（Owner：范云娜，角色③ · 发散域）。

职责：挑战可行性与技术风险（规格书 阶段 2 建议配置）。
"""
from agents.roles.base import BaseAgent
from backend.core.enums import AgentRole


class TechCriticAgent(BaseAgent):
    AGENT_ROLE = AgentRole.TECH
