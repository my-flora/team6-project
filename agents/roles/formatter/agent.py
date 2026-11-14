"""R7 需求格式化 Agent（Owner：张吴博，角色④ · 格式化域）。

职责（规格书 阶段 5）：将前序 APPROVED 条目与驳回理由合成为 PRD V1.0
（User Story + Given-When-Then 验收标准 + 决策记录）。
"""
from agents.roles.base import BaseAgent
from backend.core.enums import AgentRole


class FormatterAgent(BaseAgent):
    AGENT_ROLE = AgentRole.FORMATTER
