"""T7 proposal generation and reason-archived pruning."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from agents.roles.architect.agent import ArchitectAgent
from agents.roles.base import AgentContext
from backend.blackboard.service import BlackboardService
from backend.core.enums import AgentRole, EntryStatus, Stage
from backend.core.models import BlackboardEntry

class ProposalService:
    def __init__(self, blackboard: BlackboardService) -> None:
        self.blackboard = blackboard
        self.architect = ArchitectAgent()

    def generate(self, project_id: str, source_entry_ids: list[str], *, actor: str = "R5") -> BlackboardEntry:
        sources = []
        for entry_id in source_entry_ids:
            entry = self.blackboard.get_entry(entry_id)
            if entry.project_id != project_id or entry.status != EntryStatus.APPROVED:
                raise ValueError(f"T7 只能读取本项目已通过的条目: {entry_id}")
            if entry.stage not in (Stage.IDEA, Stage.DISCUSSION):
                raise ValueError(f"T7 不读取阶段 {entry.stage.value} 条目")
            sources.append(entry)
        idea_entries = [e for e in sources if e.stage == Stage.IDEA]
        discussion_entries = [e for e in sources if e.stage == Stage.DISCUSSION]
        if not idea_entries or not discussion_entries:
            raise ValueError("方案生成必须同时包含阶段 1 输入卡片和阶段 2 讨论结果")
        ctx = AgentContext(project_id=project_id, stage=Stage.PROPOSAL, topic_id=None,
                           round_no=1, readable_entries=sources,
                           extra={"source_entry_ids": [e.id for e in sources]})
        proposal = self.architect.build_proposal(ctx)
        entry = self.blackboard.create_entry(
            project_id, stage=Stage.PROPOSAL, source_agent=AgentRole.ARCH,
            content=json.dumps(proposal, ensure_ascii=False),
            references=[e.id for e in sources], actor=actor)
        return entry

    def trim(self, project_id: str, entry_id: str, *, item_id: str, action: str,
             reason: str, actor: str = "human") -> BlackboardEntry:
        entry = self.blackboard.get_entry(entry_id)
        if entry.project_id != project_id or entry.stage != Stage.PROPOSAL:
            raise ValueError("方案条目不存在或不属于当前项目")
        if entry.status != EntryStatus.DRAFT:
            raise ValueError("只有 DRAFT 状态方案可以裁剪")
        if action not in {"keep", "exclude"}:
            raise ValueError("action 只能是 keep 或 exclude")
        if action == "exclude" and not reason.strip():
            raise ValueError("剔除方案必须填写理由")
        content = json.loads(entry.content)
        item = next((x for x in content["trim_items"] if x["id"] == item_id), None)
        if item is None:
            raise ValueError(f"待裁剪项不存在: {item_id}")
        before = dict(item)
        item["selected"] = action == "keep"
        item["trim_reason"] = reason.strip() or None
        content.setdefault("trim_archive", []).append({
            "item_id": item_id, "action": action, "reason": reason.strip(),
            "actor": actor, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "before": before,
        })
        return self.blackboard.update_content(entry_id, json.dumps(content, ensure_ascii=False), actor=actor)
