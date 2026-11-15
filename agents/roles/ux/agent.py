"""R3 用户体验 Agent：分析受众、场景、任务流程和体验风险。"""
import json
from agents.roles.base import BaseAgent, AgentContext
from backend.core.enums import AgentRole

class UxAgent(BaseAgent):
    AGENT_ROLE = AgentRole.UX

    def respond(self, ctx: AgentContext) -> dict:
        entries = list(ctx.readable_entries)
        if not entries:
            return {"content": "缺少已批准的上下文卡片，无法形成体验判断。", "references": []}
        entry = entries[-1]
        try: card = json.loads(entry.content)
        except (TypeError, ValueError): card = {"core_goal": entry.content}
        audience = card.get("target_audience", "待明确目标受众")
        goal = card.get("core_goal", "待明确核心目标")
        prior = ctx.extra.get("prior_messages", [])
        reply = (f"结合 {prior[-1]['source_agent']} 的观点“{prior[-1]['content']}”，"
                 if prior else "")
        return {
            "content": f"体验视角：{reply}需要验证“{audience}”在目标场景下能否顺利完成“{goal}”。建议补充关键任务流程、使用前提和失败后的恢复路径，再据此确认体验验收标准。",
            "references": [entry.id],
            "risk_items": [{
                "type": "关键流程体验风险", "severity": "中",
                "trigger_condition": "目标用户无法在目标场景中完成核心任务，或缺少失败恢复路径",
                "source": entry.id, "needs_human_decision": False,
                "description": "尚未提供用户流程或可用性验证结果。",
            }],
            "conflicts_with": [],
        }
