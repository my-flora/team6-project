"""黑板服务 —— T2（Owner：张嘉辉）。

直接落在第一部分的共享设施上，不另造模型：
    * 实体用 `backend.core.models.BlackboardEntry` / `HumanGate`（T1 的 Pydantic 模型）；
    * 存储用 `backend.store.Store`（第一部分留出的进程内共享存储）；
    * 写保护用 `BaselineService.assert_blackboard_writable`（冻结后 B301 只读）；
    * 门禁裁决用 `GateService.decide_gate`（驳回必须填 reason，E202）。

规格书对应关系：
    2.2 T2  「提供增删改查接口；实现 DRAFT→PENDING 的强约束」
    3.1 状态门槛「下游阶段只能读取上游 EntryStatus = APPROVED 的黑板条目」
    3.2 幻觉传染防御（由 GateService 的 E004 承担，本服务负责读侧过滤）
    4.2 冻结基线后黑板进入只读拦截
    4.1 黑板条目状态色 / 冲突高亮

关键设计：**提交审核即生成人类门禁**。
DRAFT --submit--> PENDING_REVIEW + HumanGate(PENDING)，这样
`Store.pending_gate_count()` 天然就是 4.1 的「门禁待办红点」，
人类在门禁面板裁决后条目状态才变 APPROVED / REJECTED，中间没有捷径。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.baseline.service import BaselineService
from backend.core.enums import AgentRole, EntryStatus, GateStatus, Stage
from backend.core.models import BlackboardEntry, HumanGate
from backend.errors import (
    DownstreamReadForbidden,
    EmptyEntryContent,
    EntryNotFound,
    EntryNotEditable,
    EntryOutsideCurrentStage,
    IllegalEntryTransition,
    ProjectNotFound,
)
from backend.gate.service import GateService
from backend.store import Store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class EntryAudit:
    """条目流转留痕（不写进 T1 的模型，避免污染冻结的实体结构）。"""

    at: str
    actor: str
    from_status: str
    to_status: str
    reason: Optional[str] = None
    gate_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "at": self.at,
            "actor": self.actor,
            "from": self.from_status,
            "to": self.to_status,
            "reason": self.reason,
            "gate_id": self.gate_id,
        }


@dataclass
class _EntrySidecar:
    """挂在条目 ID 上的补充信息：审计链 + 冲突备注。"""

    history: list[EntryAudit] = field(default_factory=list)
    conflict_note: Optional[str] = None
    created_by: Optional[str] = None


class BlackboardService:
    """T2：黑板状态机 + 状态门槛 + 冻结只读。"""

    def __init__(
        self,
        store: Store,
        *,
        gate_service: Optional[GateService] = None,
        baseline_service: Optional[BaselineService] = None,
    ) -> None:
        self.store = store
        self.gate = gate_service or GateService()
        self.baseline = baseline_service or BaselineService(store)
        self._sidecar: dict[str, _EntrySidecar] = {}
        self._lock = threading.RLock()

    # ================================================================ 查询
    def list_entries(
        self,
        project_id: str,
        *,
        stage: Optional[Stage] = None,
        status: Optional[EntryStatus] = None,
    ) -> list[BlackboardEntry]:
        entries = self.store.get_entries(project_id)
        return [
            entry
            for entry in entries
            if (stage is None or entry.stage == stage)
            and (status is None or entry.status == status)
        ]

    def get_entry(self, entry_id: str) -> BlackboardEntry:
        entry = self.store.get_entry(entry_id)
        if entry is None:
            raise EntryNotFound(f"黑板条目不存在：{entry_id}", entry_id=entry_id)
        return entry

    def readable_entries(self, project_id: str, stage: Stage) -> list[BlackboardEntry]:
        """3.1 状态门槛的读侧实现。

        * 当前阶段：全部可见（Agent 要能看到本阶段的草稿与被驳回项）；
        * 上游阶段：只返回 APPROVED（未通过的不许流向下一阶段）；
        * 下游阶段：直接拒绝，防止提前窥视。
        """
        project = self._project(project_id)
        if _order(stage) > _order(project.current_stage):
            raise DownstreamReadForbidden(
                f"当前处于 {project.current_stage.value}，不能提前读取下游阶段 {stage.value} 的黑板",
                stage=stage.value,
                current_stage=project.current_stage.value,
            )
        entries = self.list_entries(project_id, stage=stage)
        if stage == project.current_stage:
            return entries
        return [entry for entry in entries if entry.status == EntryStatus.APPROVED]

    def history(self, entry_id: str) -> list[dict]:
        sidecar = self._sidecar.get(entry_id)
        return [item.to_dict() for item in sidecar.history] if sidecar else []

    def stats(self, project_id: str) -> dict:
        """4.1 黑板统计：四色条目数量 + 冲突数 + 只读标记。"""
        entries = self.store.get_entries(project_id)
        by_status = {status.value: 0 for status in EntryStatus}
        for entry in entries:
            by_status[entry.status.value] += 1
        return {
            "total": len(entries),
            "by_status": by_status,
            "conflicts": sum(1 for entry in entries if entry.is_conflict),
            "readonly": project_id in self.store.blackboard_readonly,
        }

    # ================================================================ 写操作
    def create_entry(
        self,
        project_id: str,
        *,
        stage: Stage,
        source_agent: AgentRole,
        content: str,
        references: Optional[list[str]] = None,
        actor: Optional[str] = None,
    ) -> BlackboardEntry:
        self._project(project_id)
        self._assert_writable(project_id)
        if not content or not content.strip():
            raise EmptyEntryContent("黑板条目内容不能为空")
        project = self._project(project_id)
        if stage != project.current_stage:
            raise EntryOutsideCurrentStage(
                f"只能向当前阶段 {project.current_stage.value} 写黑板，收到 {stage.value}",
                stage=stage.value,
                current_stage=project.current_stage.value,
            )
        entry = BlackboardEntry(
            id=f"e-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            stage=stage,
            source_agent=source_agent,
            content=content.strip(),
            status=EntryStatus.DRAFT,
            references=list(references or []),
        )
        self.store.add_entry(entry)
        sidecar = self._sidecar.setdefault(entry.id, _EntrySidecar())
        sidecar.created_by = actor or source_agent.value
        sidecar.history.append(
            EntryAudit(
                at=_now(),
                actor=actor or source_agent.value,
                from_status="-",
                to_status=EntryStatus.DRAFT.value,
            )
        )
        return entry

    def update_content(self, entry_id: str, content: str, *, actor: str) -> BlackboardEntry:
        """只有 DRAFT 可改；APPROVED 想改必须走「驳回 → 重开」，保住审计链。"""
        entry = self.get_entry(entry_id)
        self._assert_writable(entry.project_id)
        if entry.status != EntryStatus.DRAFT:
            raise EntryNotEditable(
                f"条目 {entry.id} 当前为 {entry.status.value}，只有 DRAFT 允许修改；"
                "如需变更请走门禁驳回 → 重开流程",
                entry_id=entry.id,
                status=entry.status.value,
            )
        if not content or not content.strip():
            raise EmptyEntryContent("黑板条目内容不能为空")
        entry.content = content.strip()
        return entry

    def submit_for_review(self, entry_id: str, *, actor: str = "human") -> tuple[BlackboardEntry, HumanGate]:
        """DRAFT → PENDING_REVIEW，并生成人类门禁（唯一提交路径）。"""
        entry = self.get_entry(entry_id)
        self._assert_writable(entry.project_id)
        if entry.status != EntryStatus.DRAFT:
            raise IllegalEntryTransition(
                f"条目 {entry.id} 当前为 {entry.status.value}，只有 DRAFT 可以提交审核",
                entry_id=entry.id,
                status=entry.status.value,
            )
        if not entry.content.strip():
            raise EmptyEntryContent("条目内容为空，不能提交审核")

        gate = HumanGate(
            id=f"g-{uuid.uuid4().hex[:8]}",
            project_id=entry.project_id,
            stage=entry.stage,
            entry_id=entry.id,
            gate_status=GateStatus.PENDING,
        )
        self.store.add_gate(gate)
        entry.status = EntryStatus.PENDING_REVIEW
        self._audit(entry, actor, EntryStatus.DRAFT, EntryStatus.PENDING_REVIEW, gate_id=gate.id)
        return entry, gate

    def decide_gate(
        self,
        gate_id: str,
        decision: GateStatus,
        *,
        reason: Optional[str] = None,
        actor: str = "human",
    ) -> tuple[HumanGate, Optional[BlackboardEntry]]:
        """门禁通过/驳回；驳回必须填 reason（4.2，E202）。"""
        gate = self.store.get_gate(gate_id)
        if gate is None:
            raise EntryNotFound(f"门禁不存在：{gate_id}", gate_id=gate_id)
        entry = self.store.get_entry(gate.entry_id)
        if entry is not None:
            self._assert_writable(entry.project_id)

        before = entry.status if entry is not None else None
        gate = self.gate.decide_gate(gate, decision, reason or "")
        if entry is not None:
            entry.status = (
                EntryStatus.APPROVED if decision == GateStatus.APPROVED else EntryStatus.REJECTED
            )
            self._audit(entry, actor, before, entry.status, reason=reason, gate_id=gate.id)
        return gate, entry

    def reopen(self, entry_id: str, *, reason: Optional[str] = None, actor: str = "human") -> BlackboardEntry:
        """REJECTED → DRAFT，供 Agent 重新生成（4.2 驳回后触发重新生成）。"""
        entry = self.get_entry(entry_id)
        self._assert_writable(entry.project_id)
        if entry.status != EntryStatus.REJECTED:
            raise IllegalEntryTransition(
                f"条目 {entry.id} 当前为 {entry.status.value}，只有 REJECTED 可以重开",
                entry_id=entry.id,
                status=entry.status.value,
            )
        entry.status = EntryStatus.DRAFT
        self._audit(entry, actor, EntryStatus.REJECTED, EntryStatus.DRAFT, reason=reason)
        return entry

    def delete_entry(self, entry_id: str, *, actor: str = "human") -> None:
        """只有从未提交过的 DRAFT 允许删除，其余一律走驳回。"""
        entry = self.get_entry(entry_id)
        self._assert_writable(entry.project_id)
        if entry.status != EntryStatus.DRAFT:
            raise IllegalEntryTransition(
                f"条目 {entry.id} 已进入 {entry.status.value}，不可删除，请走驳回流程",
                entry_id=entry.id,
                status=entry.status.value,
            )
        with self._lock:
            self.store.entries.pop(entry_id, None)
            self._sidecar.pop(entry_id, None)

    # ------------------------------------------------------------ 冲突高亮
    def mark_conflict(self, entry_id: str, note: str, *, actor: str = "PM") -> BlackboardEntry:
        """4.1 冲突高亮：条目旁显示橙色 ⚠ 待裁决。"""
        if not note or not note.strip():
            raise EmptyEntryContent("标记冲突必须说明冲突点")
        entry = self.get_entry(entry_id)
        entry.is_conflict = True
        sidecar = self._sidecar.setdefault(entry.id, _EntrySidecar())
        sidecar.conflict_note = note.strip()
        return entry

    def resolve_conflict(self, entry_id: str, decision: str, *, actor: str = "human") -> BlackboardEntry:
        """人类拍板后清除冲突标记，裁决理由进审计链。"""
        entry = self.get_entry(entry_id)
        entry.is_conflict = False
        sidecar = self._sidecar.setdefault(entry.id, _EntrySidecar())
        sidecar.conflict_note = None
        sidecar.history.append(
            EntryAudit(
                at=_now(),
                actor=actor,
                from_status=entry.status.value,
                to_status=entry.status.value,
                reason=f"冲突拍板：{decision}",
            )
        )
        return entry

    def conflict_note(self, entry_id: str) -> Optional[str]:
        sidecar = self._sidecar.get(entry_id)
        return sidecar.conflict_note if sidecar else None

    # ================================================================ 内部
    def _project(self, project_id: str):
        project = self.store.get_project(project_id)
        if project is None:
            raise ProjectNotFound(f"项目不存在：{project_id}", project_id=project_id)
        return project

    def _assert_writable(self, project_id: str) -> None:
        """冻结后黑板只读（B301 由第一部分提供，直接复用，不重复实现）。"""
        self.baseline.assert_blackboard_writable(project_id)

    def _audit(
        self,
        entry: BlackboardEntry,
        actor: str,
        from_status: Optional[EntryStatus],
        to_status: EntryStatus,
        *,
        reason: Optional[str] = None,
        gate_id: Optional[str] = None,
    ) -> None:
        sidecar = self._sidecar.setdefault(entry.id, _EntrySidecar())
        sidecar.history.append(
            EntryAudit(
                at=_now(),
                actor=actor,
                from_status=from_status.value if from_status else "-",
                to_status=to_status.value,
                reason=reason,
                gate_id=gate_id,
            )
        )


def _order(stage: Stage) -> int:
    """阶段序号，用于判断上下游（复用第一部分 STAGE_ORDER，不再自建顺序表）。"""
    from backend.core.enums import STAGE_ORDER

    return STAGE_ORDER.index(stage)
