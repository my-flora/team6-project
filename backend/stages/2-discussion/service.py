"""T6 multi-agent discussion service (R2 -> R3 -> R4 -> R5)."""
from __future__ import annotations
import json
import re
import uuid
from difflib import SequenceMatcher
from typing import Any
from agents.roles.base import AgentContext
from agents.roles.business.agent import BusinessAgent
from agents.roles.ux.agent import UxAgent
from agents.roles.tech_critic.agent import TechCriticAgent
from agents.roles.architect.agent import ArchitectAgent
from backend.blackboard.service import BlackboardService
from backend.core.enums import AgentRole, EntryStatus, Stage
from backend.core.models import AgentMessage
from backend.orchestrator.engine import Orchestrator
from backend.errors import RoundNotOpen, StageMismatch

ROLE_ID = {AgentRole.BA: "R2", AgentRole.UX: "R3", AgentRole.TECH: "R4", AgentRole.ARCH: "R5"}
AGENT_ORDER = (BusinessAgent, UxAgent, TechCriticAgent, ArchitectAgent)


def _normalise(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold(), flags=re.UNICODE)


def _same_viewpoint(left: str, right: str) -> bool:
    a, b = _normalise(left), _normalise(right)
    return bool(a and b and (a == b or SequenceMatcher(None, a, b).ratio() >= 0.93))


class DiscussionStageService:
    """生成当前议题的一轮 R2-R5 发言，并将消息、观点和风险写入现有流程。"""
    def __init__(self, blackboard: BlackboardService, orchestrator: Orchestrator, agents=None) -> None:
        self.blackboard = blackboard
        self.orchestrator = orchestrator
        self.agents = agents if agents is not None else [cls() for cls in AGENT_ORDER]

    def run_round(self, project_id: str, *, actor: str = "R1") -> dict[str, Any]:
        project = self.orchestrator._require_project(project_id)
        if project.current_stage != Stage.DISCUSSION:
            raise StageMismatch("T6 只能在 DISCUSSION 阶段运行", current_stage=project.current_stage.value)
        runtime = self.orchestrator.runtime(project_id)
        state = runtime.rounds.current
        if state is None or not runtime.rounds.is_open():
            raise RoundNotOpen("请先由 R1 打开当前讨论议题")
        topic = state.entity.topic
        round_no = state.entity.round_no
        context_cards = self.blackboard.readable_entries(project_id, Stage.IDEA)
        if not context_cards:
            raise ValueError("没有阶段 1 已批准的上下文卡片")
        context_ids = [item.id for item in context_cards]
        ctx = AgentContext(project_id=project_id, stage=Stage.DISCUSSION,
                           topic_id=state.entity.id, round_no=round_no,
                           readable_entries=context_cards,
                           extra={"topic": topic, "prior_messages": []})
        responses: list[dict[str, Any]] = []
        submitted: list[dict[str, Any]] = []
        accepted_roles = set(state.spoken)
        expected_roles = state.expected_speakers
        agents_by_role = {agent.AGENT_ROLE: agent for agent in self.agents}
        for role in expected_roles:
            if role not in agents_by_role or role in accepted_roles:
                continue
            agent = agents_by_role[role]
            response = agent.respond(ctx)
            references = list(dict.fromkeys(response.get("references", [])))
            if not references or any(ref not in context_ids for ref in references):
                raise ValueError(f"{ROLE_ID[role]} 发言必须引用本阶段已批准的上下文卡片")
            message = AgentMessage(
                id=f"m-{uuid.uuid4().hex[:8]}", project_id=project_id,
                stage=Stage.DISCUSSION, agent_role=role, topic_id=state.entity.id,
                round_no=round_no, content=response["content"], references=references,
            )
            result = self.orchestrator.submit_message(message, actor=actor)
            submitted.append({"message": message, "response": response, "result": result,
                              "role_id": ROLE_ID[role]})
            responses.append({"message_id": message.id, "source_agent": ROLE_ID[role],
                              "content": message.content, "references": references,
                              "risk_items": response.get("risk_items", []),
                              "conflicts_with": response.get("conflicts_with", []),
                              "is_conflict": bool(response.get("is_conflict", False))})
            ctx.extra["prior_messages"].append(responses[-1])
            if result.get("converged"):
                break

        if not submitted:
            raise ValueError("当前轮次的 R2-R5 发言已全部提交")
        viewpoints = self._deduplicate(responses)
        self._mark_conflicts(viewpoints, responses)
        created_entries = []
        for viewpoint in viewpoints:
            first_role = next(role for role, role_id in ROLE_ID.items()
                              if role_id == viewpoint["first_source"])
            content = json.dumps(viewpoint, ensure_ascii=False)
            entry = self.blackboard.create_entry(
                project_id, stage=Stage.DISCUSSION, source_agent=first_role,
                content=content, references=viewpoint["references"], actor=actor)
            if viewpoint["is_conflict"]:
                self.blackboard.mark_conflict(entry.id, "存在相反观点，保留双方方案并等待人类裁决")
            entry, gate = self.blackboard.submit_for_review(entry.id, actor=actor)
            created_entries.append({"entry": entry.model_dump(), "gate_id": gate.id,
                                    "source_agent": viewpoint["first_source"]})

        risks = self._collect_risks(responses, context_ids)
        for card in context_cards:
            try:
                input_payload = json.loads(card.content)
            except (TypeError, ValueError):
                continue
            for risk in input_payload.get("risk_register", []):
                risks.append({**risk, "source_agent": "HUMAN",
                              "source_references": [card.id]})
        if risks:
            refs = list(dict.fromkeys(ref for risk in risks for ref in risk["source_references"]))
            risk_entry = self.blackboard.create_entry(
                project_id, stage=Stage.DISCUSSION, source_agent=AgentRole.PM,
                content=json.dumps({"kind": "risk_register", "items": risks}, ensure_ascii=False),
                references=refs, actor=actor)
            risk_entry, risk_gate = self.blackboard.submit_for_review(risk_entry.id, actor=actor)
            created_entries.append({"entry": risk_entry.model_dump(), "gate_id": risk_gate.id,
                                    "source_agent": "R1", "kind": "risk_register"})
        return {
            "topic": topic, "round_no": round_no,
            "round_status": runtime.rounds.current.entity.status.value,
            "messages": [{"message_id": item["message"].id, "source_agent": item["role_id"],
                          "accepted": item["result"].get("accepted", False)} for item in submitted],
            "viewpoints": viewpoints, "risk_register": risks,
            "blackboard_entries": created_entries,
        }

    @staticmethod
    def _deduplicate(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for msg in messages:
            match = next((item for item in groups if _same_viewpoint(item["text"], msg["content"])), None)
            if match:
                match["duplicate_sources"].append({"source_agent": msg["source_agent"],
                                                     "message_id": msg["message_id"],
                                                     "content": msg["content"]})
                match["source_agents"] = list(dict.fromkeys(match["source_agents"] + [msg["source_agent"]]))
                match["references"] = list(dict.fromkeys(match["references"] + msg["references"]))
            else:
                groups.append({
                    "kind": "viewpoint",
                    "viewpoint_id": f"v-{uuid.uuid4().hex[:8]}",
                    "text": msg["content"],
                    "first_source": msg["source_agent"],
                    "first_message_id": msg["message_id"],
                    "source_agents": [msg["source_agent"]],
                    "references": list(msg["references"]),
                    "duplicate_sources": [],
                    "is_conflict": bool(msg.get("is_conflict", False)),
                    "conflicts_with": [],
                    "alternatives": [{"source_agent": msg["source_agent"],
                                       "message_id": msg["message_id"], "content": msg["content"]}],
                })
        return groups

    @staticmethod
    def _mark_conflicts(viewpoints: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
        role_to_view = {}
        message_to_view = {}
        message_by_id = {item["message_id"]: item for item in messages}
        for view in viewpoints:
            for role in view["source_agents"]:
                role_to_view[role] = view
            message_to_view[view["first_message_id"]] = view
            for duplicate in view["duplicate_sources"]:
                message_to_view[duplicate["message_id"]] = view
        for message in messages:
            current = message_to_view.get(message["message_id"])
            if not current: continue
            for target in message.get("conflicts_with", []):
                other = role_to_view.get(target) or message_to_view.get(target)
                if not other or other["viewpoint_id"] == current["viewpoint_id"]: continue
                current["is_conflict"] = other["is_conflict"] = True
                current["conflicts_with"] = list(dict.fromkeys(current["conflicts_with"] + [other["viewpoint_id"]]))
                other["conflicts_with"] = list(dict.fromkeys(other["conflicts_with"] + [current["viewpoint_id"]]))
                pair = [message]
                if target in message_by_id:
                    pair.append(message_by_id[target])
                else:
                    pair.extend(m for m in messages if m["source_agent"] == target)
                for msg in pair:
                    view = message_to_view.get(msg["message_id"])
                    if view:
                        alternative = {"source_agent": msg["source_agent"],
                                       "message_id": msg["message_id"], "content": msg["content"]}
                        if alternative not in view["alternatives"]:
                            view["alternatives"].append(alternative)

    @staticmethod
    def _collect_risks(messages: list[dict[str, Any]], valid_refs: list[str]) -> list[dict[str, Any]]:
        ledger = []
        for msg in messages:
            for risk in msg.get("risk_items", []):
                required = ("type", "severity", "trigger_condition", "source", "needs_human_decision")
                if any(key not in risk for key in required):
                    raise ValueError(f"{msg['source_agent']} 风险记录缺少必填字段")
                if any(not str(risk[key]).strip() for key in ("type", "trigger_condition", "source")):
                    raise ValueError(f"{msg['source_agent']} 风险记录的类型、触发条件和来源不能为空")
                if risk["severity"] not in {"高", "中", "低"}:
                    raise ValueError("风险严重度必须为高/中/低")
                if not isinstance(risk["needs_human_decision"], bool):
                    raise ValueError("needs_human_decision 必须为布尔值")
                source_refs = [ref for ref in msg["references"] if ref in valid_refs]
                ledger.append({**risk, "source_agent": msg["source_agent"],
                               "source_references": source_refs})
        return ledger
