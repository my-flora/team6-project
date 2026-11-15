"""R4 技术挑刺 Agent：识别边界、依赖、可验证性和技术风险。"""
import json
from agents.roles.base import BaseAgent, AgentContext
from backend.core.enums import AgentRole

class TechCriticAgent(BaseAgent):
    AGENT_ROLE = AgentRole.TECH

    def respond(self, ctx: AgentContext) -> dict:
        entries = list(ctx.readable_entries)
        if not entries:
            return {"content": "缺少已批准的上下文卡片，无法开展技术挑刺。", "references": []}
        entry = entries[-1]
        try: card = json.loads(entry.content)
        except (TypeError, ValueError): card = {"core_goal": entry.content}
        boundary = card.get("desired_boundary", "待明确期望边界")
        criteria = card.get("success_criteria", "待明确成功判据")
        prior = ctx.extra.get("prior_messages", [])
        previous = (f"复核前序观点（{prior[-1]['source_agent']}）：{prior[-1]['content']}。"
                    if prior else "")
        return {
            "content": f"技术挑刺：{previous}当前边界为“{boundary}”，成功判据为“{criteria}”。请补充外部依赖、数据来源、运行环境和异常处理约束；在这些条件明确前，不应把具体技术选型或工期写成已确认结论。",
            "references": [entry.id],
            "risk_items": [{
                "type": "技术依赖与可行性风险", "severity": "高",
                "trigger_condition": "关键外部依赖、数据来源或运行约束未确认，导致方案无法实现或验收",
                "source": entry.id, "needs_human_decision": True,
                "description": "需求卡片尚未提供依赖清单及运行环境。",
            }],
            "conflicts_with": [],
        }
