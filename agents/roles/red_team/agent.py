"""R6 评价/红队 Agent（Owner：张吴博，角色④ · 博弈域）。

职责（规格书 阶段 4）：按人类设定的维度（安全/性能/合规/ROI…）质疑方案 Agent，
产出打分与致命缺陷列表；未达最低分触发 REJECTED 退回阶段 3。
"""
from agents.roles.base import BaseAgent
from backend.core.enums import AgentRole


class RedTeamAgent(BaseAgent):
    AGENT_ROLE = AgentRole.RED_TEAM
