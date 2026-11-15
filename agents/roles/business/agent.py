"""R2 商业分析 Agent：围绕目标受众、价值主张和商业机会/风险发言。"""
import json
from agents.roles.base import BaseAgent, AgentContext
from backend.core.enums import AgentRole

class BusinessAgent(BaseAgent):
    AGENT_ROLE = AgentRole.BA

    def respond(self, ctx: AgentContext) -> dict:
        entries = list(ctx.readable_entries)
        if not entries:
            return {"content": "缺少已批准的上下文卡片，无法形成商业判断。", "references": []}
        entry = entries[-1]
        try: card = json.loads(entry.content)
        except (TypeError, ValueError): card = {"core_goal": entry.content}
        audience = card.get("target_audience", "待明确目标受众")
        value = card.get("value_proposition", "待明确价值主张")
        return {
            "content": f"商业视角：当前目标受众为“{audience}”，预期价值为“{value}”。建议在方案中说明目标用户规模、价值验证方式及资源投入依据；相关数据尚未提供时应标为待确认。",
            "references": [entry.id],
            "risk_items": [{
                "type": "商业价值验证风险", "severity": "中",
                "trigger_condition": "目标受众或价值主张无法通过访谈、试用或其他证据验证",
                "source": entry.id, "needs_human_decision": True,
                "description": "当前卡片尚未附市场规模或用户验证数据。",
            }],
            "conflicts_with": [],
        }
