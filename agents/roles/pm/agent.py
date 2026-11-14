"""R1 PM / 调度 Agent（Owner：张嘉辉）。

分工表里 Agent 角色列为「R1 PM / 调度」，负责的是**流程裁决**而不是内容生成：
    * 排发言序（每个阶段该由哪些角色发言）；
    * 开题、收敛、总结（3.2 无限发散防御：收敛后必须输出总结）；
    * 偏离提醒与拉回（T4 偏离拉回清零）；
    * 升级告警（3.2 基线超时未签：系统向 PM 发送升级告警）。

实现上刻意做成**确定性规则引擎**，不调用大模型：
课堂验收时结果可复现，也方便范云娜 / 张吴博的角色 Agent 直接复用 PM 的调度结论。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from backend.core.enums import AgentRole, Stage
from backend.log import EventLog, EventType, LogEvent

#: 各阶段的发言序（PM 议程）。阶段 6 是三方会签，没有 Agent 发言。
AGENDA: dict[Stage, tuple[AgentRole, ...]] = {
    Stage.IDEA: (AgentRole.BA, AgentRole.UX),
    Stage.DISCUSSION: (AgentRole.BA, AgentRole.UX, AgentRole.TECH, AgentRole.ARCH),
    Stage.PROPOSAL: (AgentRole.ARCH, AgentRole.TECH, AgentRole.BA),
    Stage.EVALUATION: (AgentRole.RED_TEAM, AgentRole.TECH, AgentRole.ARCH),
    Stage.REQUIREMENT: (AgentRole.TECH, AgentRole.BA),
    Stage.CONFIRMATION: (),
}

_POINT_PREVIEW = 80


@dataclass(frozen=True)
class RoundSummary:
    """PM 的收敛总结（结构 + 文本双份，前端与 PRD 合成都能用）。"""

    topic: str
    round_no: int
    reason: str
    participants: tuple[str, ...]
    points: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    message_count: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "round_no": self.round_no,
            "reason": self.reason,
            "participants": list(self.participants),
            "points": list(self.points),
            "conflicts": list(self.conflicts),
            "message_count": self.message_count,
            "text": self.text,
        }


class PMAgent:
    """PM / 调度。所有对外方法都不抛异常，失败以事件流形式暴露。"""

    role: AgentRole = AgentRole.PM
    name = "PM"

    def __init__(self, log: EventLog) -> None:
        self._log = log

    # ---------------------------------------------------------------- 议程
    def agenda_for(self, stage: Stage) -> tuple[AgentRole, ...]:
        return AGENDA.get(stage, ())

    def opening_note(self, *, stage: Stage, topic: str, round_no: int, max_rounds: int) -> str:
        speakers = "、".join(role.value for role in self.agenda_for(stage))
        return (
            f"【PM】{stage.value} 议题《{topic}》开始，第 {round_no}/{max_rounds} 轮。"
            f"本轮发言序：{speakers or '（人类会签，无 Agent 发言）'}。"
            f"请每条发言引用上游已通过条目，references 为空将被直接丢弃。"
        )

    # ---------------------------------------------------------------- 总结
    def summarize(
        self,
        *,
        topic: str,
        round_no: int,
        reason: str,
        messages: Sequence[LogEvent],
    ) -> RoundSummary:
        """把一轮发言压成总结。相同角色多次发言只保留要点，冲突单独列出。"""
        participants: list[str] = []
        points: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        for event in messages:
            role = event.role or "unknown"
            if role not in participants:
                participants.append(role)
            content = str(event.payload.get("content", "")).strip().replace("\n", " ")
            preview = content[:_POINT_PREVIEW].rstrip("。．.;；,，")
            if len(content) > _POINT_PREVIEW:
                preview += "…"
            points.append({"role": role, "point": preview, "seq": event.seq})
            if event.payload.get("conflict"):
                conflicts.append({"role": role, "point": preview})

        head = (
            f"【PM 收敛总结】议题《{topic}》共 {len(messages)} 条有效发言、"
            f"{len(participants)} 位 Agent 参与，收敛原因：{reason}。"
        )
        if points:
            bullet = "；".join(f"{item['role']}：{item['point']}" for item in points[:6])
            if len(points) > 6:
                bullet += f"；等共 {len(points)} 条"
            body = f"核心要点：{bullet}。"
        else:
            body = "本轮无有效发言，直接进入人类裁决。"
        tail = (
            f"仍有 {len(conflicts)} 条冲突待人类裁决。"
            if conflicts
            else "未发现未裁决冲突，可进入下一阶段。"
        )

        return RoundSummary(
            topic=topic,
            round_no=round_no,
            reason=reason,
            participants=tuple(participants),
            points=tuple(points),
            conflicts=tuple(conflicts),
            message_count=len(messages),
            text=head + body + tail,
        )

    # ------------------------------------------------------------ 异常提示
    def deviation_warning(self, *, role: AgentRole, reason: str, count: int) -> None:
        """偏离提醒（未到拉回阈值时）。"""
        self._log.append(
            EventType.ESCALATION,
            actor="PM",
            role=role,
            payload={
                "level": "warning",
                "title": "发言偏离议题",
                "detail": f"{role.value} 的发言偏离议题（第 {count} 次）：{reason}",
            },
        )

    def escalation(self, *, title: str, detail: str, level: str = "error") -> None:
        """升级告警（3.2 基线超时未签等）。"""
        self._log.append(
            EventType.ESCALATION,
            actor="PM",
            payload={"level": level, "title": title, "detail": detail},
        )

    def signoff_timeout_alert(self, *, hours: int, timeout_hours: int = 24) -> str:
        """3.2「基线超时未签」：发起会签 24 小时仍未全绿 → 向 PM 发送升级告警。"""
        text = (
            f"【PM 升级告警】发起会签已超过 {timeout_hours} 小时（当前 {hours} 小时），"
            f"会签状态仍未全绿：请立即催办，或由人类手动强制冻结。"
        )
        self.escalation(title="基线超时未签", detail=text)
        return text

    def pending_gate_reminder(self, *, pending: int, stage: Stage) -> str:
        """4.1 门禁红点：提醒人类先处理门禁再推进。"""
        text = f"【PM】{stage.value} 仍有 {pending} 项门禁待处理，推进按钮已灰显。"
        self.escalation(title="门禁未处理", detail=text, level="warning")
        return text

    def round_summary_of(self, log: Sequence[LogEvent]) -> Optional[dict[str, Any]]:
        """取最近一条收敛总结（前端「PM 总结」卡片用）。"""
        for event in reversed(list(log)):
            if event.type is EventType.ROUND_CONVERGED:
                return dict(event.payload)
        return None
