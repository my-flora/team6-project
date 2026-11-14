"""进程内共享存储（联调用）。真实持久化由 T2 黑板服务负责，此处仅为 T3/T10 联调提供最小依赖。"""
import threading
import uuid
from typing import Optional

from backend.core.enums import Stage
from backend.core.models import (
    Baseline,
    BlackboardEntry,
    ChangeRequest,
    HumanGate,
    Project,
    Signoff,
)


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.projects: dict[str, Project] = {}
        self.entries: dict[str, BlackboardEntry] = {}
        self.gates: dict[str, HumanGate] = {}
        self.signoffs: dict[str, Signoff] = {}
        self.baselines: dict[str, Baseline] = {}
        self.change_requests: dict[str, ChangeRequest] = {}
        self.blackboard_readonly: set[str] = set()  # 已冻结项目 ID

    # ---------- 项目 ----------

    def create_project(self, name: str) -> Project:
        p = Project(id=f"p-{uuid.uuid4().hex[:8]}", name=name, current_stage=Stage.IDEA)
        with self._lock:
            self.projects[p.id] = p
        return p

    def get_project(self, project_id: str) -> Optional[Project]:
        return self.projects.get(project_id)

    # ---------- 黑板条目 ----------

    def add_entry(self, entry: BlackboardEntry) -> BlackboardEntry:
        with self._lock:
            self.entries[entry.id] = entry
        return entry

    def get_entry(self, entry_id: str) -> Optional[BlackboardEntry]:
        return self.entries.get(entry_id)

    def get_entries(self, project_id: str) -> list[BlackboardEntry]:
        return [e for e in self.entries.values() if e.project_id == project_id]

    # ---------- 门禁 ----------

    def add_gate(self, gate: HumanGate) -> HumanGate:
        with self._lock:
            self.gates[gate.id] = gate
        return gate

    def get_gate(self, gate_id: str) -> Optional[HumanGate]:
        return self.gates.get(gate_id)

    def pending_gate_count(self, project_id: str) -> int:
        """门禁待办红点：count(HumanGate where GateStatus=PENDING)"""
        from backend.core.enums import GateStatus
        return sum(
            1 for g in self.gates.values()
            if g.project_id == project_id and g.gate_status == GateStatus.PENDING
        )

    # ---------- 会签 ----------

    def add_signoff(self, signoff: Signoff) -> Signoff:
        with self._lock:
            self.signoffs[signoff.id] = signoff
        return signoff

    def get_signoffs(self, project_id: str) -> list[Signoff]:
        return [s for s in self.signoffs.values() if s.project_id == project_id]

    # ---------- 基线 / 变更 ----------

    def add_baseline(self, baseline: Baseline) -> Baseline:
        with self._lock:
            self.baselines[baseline.id] = baseline
            self.blackboard_readonly.add(baseline.project_id)
        return baseline

    def get_baseline(self, baseline_id: str) -> Optional[Baseline]:
        return self.baselines.get(baseline_id)

    def latest_baseline(self, project_id: str) -> Optional[Baseline]:
        items = [b for b in self.baselines.values() if b.project_id == project_id]
        return max(items, key=lambda b: b.frozen_at, default=None)

    def add_change_request(self, cr: ChangeRequest) -> ChangeRequest:
        with self._lock:
            self.change_requests[cr.id] = cr
        return cr

    def get_change_request(self, cr_id: str) -> Optional[ChangeRequest]:
        return self.change_requests.get(cr_id)


store = Store()
