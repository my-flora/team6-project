"""发言事件流（/backend/log）。

对应分工表里"发言事件流"这一项，同时是前端 4.1「Agent 状态灯」与
「议题与轮次提示」的数据源：

    Agent 状态灯  = 每个角色最近一条事件的记录时间 + 当前 RoundStatus
    时间线/讨论区 = 按 seq 增量拉取（前端记住 after_seq，只取增量）

设计要点：
    * append-only：只追加，不修改、不删除，保证审计可追溯；
    * 单调自增 seq：前端可以安全地做增量拉取与断线重放；
    * 订阅回调：Stage 流式输出（SSE / WebSocket）可以直接挂在 subscribe 上；
    * 可选 JSONL 落盘：一个事件一行，方便事后复盘与验收演示。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    """事件类型。命名遵循 `域.动作`，前端可据此做颜色/图标映射。"""

    PROJECT_STARTED = "project.started"
    PROJECT_PAUSED = "project.paused"
    PROJECT_RESUMED = "project.resumed"
    PROJECT_FROZEN = "project.frozen"

    ROUND_OPENED = "round.opened"
    ROUND_ADVANCED = "round.advanced"
    ROUND_CONVERGED = "round.converged"
    ROUND_TERMINATED = "round.terminated"
    PULL_BACK = "round.pull_back"
    TIMEBOX_EXPIRED = "round.timebox_expired"

    MESSAGE_ACCEPTED = "message.accepted"
    MESSAGE_DISCARDED = "message.discarded"
    MESSAGE_DEVIATED = "message.deviated"

    STAGE_ADVANCED = "stage.advanced"
    STAGE_WAITING_HUMAN = "stage.waiting_human"
    STAGE_REJECTED = "stage.rejected"

    ENTRY_CREATED = "entry.created"
    ENTRY_UPDATED = "entry.updated"
    ENTRY_SUBMITTED = "entry.submitted"
    ENTRY_DECIDED = "entry.decided"
    ENTRY_REOPENED = "entry.reopened"
    ENTRY_CONFLICT = "entry.conflict"

    ESCALATION = "system.escalation"


@dataclass(frozen=True, slots=True)
class LogEvent:
    """一条不可变的日志事件。"""

    seq: int
    ts: str
    type: EventType
    actor: str
    role: str | None = None
    stage: str | None = None
    round_no: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "type": self.type.value,
            "actor": self.actor,
            "role": self.role,
            "stage": self.stage,
            "round_no": self.round_no,
            "payload": self.payload,
        }


class EventLog:
    """线程安全的内存事件流（可选 JSONL 落盘）。"""

    def __init__(
        self,
        project_id: str,
        *,
        clock: Callable[[], datetime] = utcnow,
        sink_path: str | Path | None = None,
        max_memory: int = 10_000,
    ) -> None:
        self.project_id = project_id
        self._clock = clock
        self._lock = threading.RLock()
        self._events: list[LogEvent] = []
        self._seq = 0
        self._subscribers: list[Callable[[LogEvent], None]] = []
        self._max_memory = max_memory
        self._sink = Path(sink_path) if sink_path is not None else None
        if self._sink is not None:
            self._sink.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ 写
    def append(
        self,
        event_type: EventType,
        *,
        actor: str,
        role: Any | None = None,
        stage: Any | None = None,
        round_no: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> LogEvent:
        with self._lock:
            self._seq += 1
            event = LogEvent(
                seq=self._seq,
                ts=self._clock().isoformat(timespec="seconds"),
                type=event_type,
                actor=actor,
                role=_enum_value(role),
                stage=_enum_value(stage),
                round_no=round_no,
                payload=payload or {},
            )
            self._events.append(event)
            if len(self._events) > self._max_memory:
                # 只裁内存，落盘的 JSONL 仍然完整
                self._events = self._events[-self._max_memory :]
            self._write_sink(event)
            subscribers = list(self._subscribers)
        # 回调放在锁外，避免下游回调里再写日志造成死锁
        for callback in subscribers:
            try:
                callback(event)
            except Exception:  # noqa: BLE001 - 订阅方异常不能影响主流程
                continue
        return event

    # ------------------------------------------------------------------ 读
    def list_events(
        self,
        *,
        after_seq: int = 0,
        limit: int = 200,
        types: Iterable[EventType] | None = None,
        role: Any | None = None,
        round_no: int | None = None,
        stage: Any | None = None,
    ) -> list[LogEvent]:
        """增量拉取：返回 seq > after_seq 的事件，供前端做轮询/重放。"""
        wanted_types = {t.value for t in types} if types is not None else None
        role_value = _enum_value(role)
        stage_value = _enum_value(stage)
        with self._lock:
            result: list[LogEvent] = []
            for event in self._events:
                if event.seq <= after_seq:
                    continue
                if wanted_types is not None and event.type.value not in wanted_types:
                    continue
                if role_value is not None and event.role != role_value:
                    continue
                if round_no is not None and event.round_no != round_no:
                    continue
                if stage_value is not None and event.stage != stage_value:
                    continue
                result.append(event)
                if len(result) >= limit:
                    break
            return result

    def messages_of_round(self, round_no: int) -> list[LogEvent]:
        """某一轮被采纳的 Agent 发言，PM 写收敛总结时用。"""
        return self.list_events(
            types=[EventType.MESSAGE_ACCEPTED],
            round_no=round_no,
            limit=10_000,
        )

    def last_event_of_role(self) -> dict[str, LogEvent]:
        """每个角色最近一次活动，前端 Agent 状态灯用。"""
        with self._lock:
            latest: dict[str, LogEvent] = {}
            for event in self._events:
                if event.role is None:
                    continue
                if event.type in (
                    EventType.MESSAGE_ACCEPTED,
                    EventType.MESSAGE_DISCARDED,
                    EventType.MESSAGE_DEVIATED,
                ):
                    latest[event.role] = event
            return latest

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def count(self, event_type: EventType | None = None) -> int:
        with self._lock:
            if event_type is None:
                return len(self._events)
            return sum(1 for e in self._events if e.type is event_type)

    # -------------------------------------------------------------- 订阅
    def subscribe(self, callback: Callable[[LogEvent], None]) -> Callable[[], None]:
        """注册订阅者，返回取消订阅的函数。"""
        with self._lock:
            self._subscribers.append(callback)
        return lambda: self.unsubscribe(callback)

    def unsubscribe(self, callback: Callable[[LogEvent], None]) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    # ------------------------------------------------------------ 导出
    def to_dicts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [event.to_dict() for event in self._events]

    def export_jsonl(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            events = list(self._events)
        with target.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        return target

    # ------------------------------------------------------------ 内部
    def _write_sink(self, event: LogEvent) -> None:
        if self._sink is None:
            return
        try:
            with self._sink.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            # 落盘失败不能阻断业务流程，内存里仍有完整副本
            pass


def _enum_value(value: Any | None) -> str | None:
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)
