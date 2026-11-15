"""R5 架构/方案 Agent：阶段2发言和阶段3七章方案骨架生成。"""
import json
import uuid
from agents.roles.base import BaseAgent, AgentContext
from backend.core.enums import AgentRole, Stage

PROPOSAL_CHAPTERS = [
    ("background_and_goal", "一 项目背景与目标"),
    ("scope_and_constraints", "二 范围与边界"),
    ("business_system_architecture", "三 业务与系统架构"),
    ("modules_and_technical_route", "四 模块清单与技术路线"),
    ("alternatives_and_selection", "五 方案比较与推荐"),
    ("cost_schedule_resources", "六 成本、工期与资源估算"),
    ("risks_mitigation_acceptance", "七 风险、缓解措施与验收依据"),
]

class ArchitectAgent(BaseAgent):
    AGENT_ROLE = AgentRole.ARCH

    def respond(self, ctx: AgentContext) -> dict:
        entries = list(ctx.readable_entries)
        if not entries:
            return {"content": "缺少已批准的上下文卡片，无法形成架构建议。", "references": []}
        entry = entries[-1]
        try: card = json.loads(entry.content)
        except (TypeError, ValueError): card = {"core_goal": entry.content}
        prior = ctx.extra.get("prior_messages", [])
        prior_text = "；".join(f"{item['source_agent']}：{item['content']}" for item in prior)
        return {
            "content": f"架构视角：综合前序观点（{prior_text or '暂无'}），建议先围绕“{card.get('core_goal', '核心目标')}”划分用户端、业务处理和数据/集成边界，再将期望边界“{card.get('desired_boundary', '待明确')}”转成模块范围。先验证关键依赖，再估算成本与工期；具体模块和选型待结合其他 Agent 的观点确定。",
            "references": [entry.id], "is_conflict": False,
            "risk_items": [{
                "type": "模块边界不清风险", "severity": "中",
                "trigger_condition": "模块职责或系统边界无法映射到需求和验收依据",
                "source": entry.id, "needs_human_decision": False,
                "description": "方案结构需在阶段 3 结合已批准观点进一步细化。",
            }],
            "conflicts_with": [],
        }

    def build_proposal(self, ctx: AgentContext) -> dict:
        """基于已 APPROVED 的阶段1/2材料生成七章完整草案，不虚构估算。"""
        idea = {}
        viewpoints = []
        risks = []
        unresolved_conflicts = []
        for entry in ctx.readable_entries:
            try: payload = json.loads(entry.content)
            except (TypeError, ValueError): payload = {"raw": entry.content}
            if entry.stage == Stage.IDEA:
                idea.update(payload)
            elif entry.stage == Stage.DISCUSSION:
                if payload.get("kind") == "risk_register":
                    risks.extend(payload.get("items", []))
                elif payload.get("kind") == "viewpoint":
                    viewpoints.append(payload)
                    if payload.get("is_conflict"):
                        unresolved_conflicts.append(payload.get("viewpoint_id", entry.id))
        goal = idea.get("core_goal", "待补充")
        audience = idea.get("target_audience", "待补充")
        boundary = idea.get("desired_boundary", "待补充")
        criteria = idea.get("success_criteria", "待补充")
        value = idea.get("value_proposition", "待补充")
        modules = []
        for point in viewpoints:
            modules.append({
                "id": "item-" + uuid.uuid4().hex[:8], "item_type": "viewpoint",
                "title": point.get("first_source", "Agent") + "观点",
                "description": point.get("text", ""),
                "source_refs": point.get("references", []),
                "selected": True, "trim_reason": None,
            })
        alternatives = []
        for point in viewpoints:
            if point.get("is_conflict"):
                for alternative in point.get("alternatives", []):
                    alternatives.append({
                        "id": "item-" + uuid.uuid4().hex[:8], "item_type": "alternative",
                        "title": f"{alternative.get('source_agent', 'Agent')}备选方案",
                        "description": alternative.get("content", ""),
                        "source_refs": point.get("references", []),
                        "selected": True, "trim_reason": None,
                    })
        chapters = [
            {"key": PROPOSAL_CHAPTERS[0][0], "title": PROPOSAL_CHAPTERS[0][1],
             "content": f"核心目标：{goal}\n目标价值：{value}"},
            {"key": PROPOSAL_CHAPTERS[1][0], "title": PROPOSAL_CHAPTERS[1][1],
             "content": f"目标受众：{audience}\n期望边界：{boundary}"},
            {"key": PROPOSAL_CHAPTERS[2][0], "title": PROPOSAL_CHAPTERS[2][1],
             "content": "待根据已批准观点补充业务流程、系统边界及组件关系。"},
            {"key": PROPOSAL_CHAPTERS[3][0], "title": PROPOSAL_CHAPTERS[3][1],
             "content": "待确认模块和技术路线；当前观点见本章裁剪清单。"},
            {"key": PROPOSAL_CHAPTERS[4][0], "title": PROPOSAL_CHAPTERS[4][1],
             "content": ("存在冲突时保留双方备选方案，待人类裁决后选择。" if unresolved_conflicts
                         else "待结合业务价值、用户体验和技术可行性比较并记录推荐理由。")},
            {"key": PROPOSAL_CHAPTERS[5][0], "title": PROPOSAL_CHAPTERS[5][1],
             "content": "成本、工期与资源估算：待估。补充估算依据后再作为确定结论。"},
            {"key": PROPOSAL_CHAPTERS[6][0], "title": PROPOSAL_CHAPTERS[6][1],
             "content": f"成功判据：{criteria}\n风险登记：{len(risks)} 项，需在此补充逐项缓解措施和验收办法。"},
        ]
        trim_items = modules + alternatives
        return {
            "title": "阶段3 方案草案", "agent": "R5",
            "chapters": chapters, "viewpoints": viewpoints,
            "alternatives": alternatives, "trim_items": trim_items,
            "trim_archive": [], "risk_register": risks,
            "unresolved_conflicts": unresolved_conflicts,
            "source_entry_ids": list(ctx.extra.get("source_entry_ids", [])),
        }
