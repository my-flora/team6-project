"""R3 用户体验 Agent（Owner：范云娜，角色③ · 发散域）。"""
from agents.roles.base import BaseAgent
from backend.core.enums import AgentRole


class UxAgent(BaseAgent):
    AGENT_ROLE = AgentRole.UX
