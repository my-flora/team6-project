"""轮次控制、时间盒、强制收敛、拉回清零 —— T4（Owner：张嘉辉）。

规格书依据：
    2.2 T4 验收标准：实现轮次到 5 自动截断；实现偏离拉回清零逻辑
    3.1 轮次控制：单议题 RoundStatus = ONGOING 达到 5 轮，PM 强制置为 CONVERGED
    3.2 无限发散防御：RoundNo ≥ 5 或人类点击「拉回」→ PM 停止发言、CONVERGED 并输出总结
    4.1 议题与轮次提示「议题: [topic] · 轮次 [2]/[5]」；时间盒倒计时，小于 1 分钟变红

实体用第一部分冻结的 `backend.core.models.DiscussionRound`
（round_no / max_rounds / status / timebox_end 直接喂给前端 4.1 的信号），
控制器只额外保存"谁发过言、偏离了几次、总结是什么"这类运行期状态。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from backend.core.enums import MAX_ROUNDS, AgentRole, RoundStatus, Stage
from backend.core.models import DiscussionRound
from backend.errors import InvalidRoundConfig, InvalidRoundOperation, RoundNotOpen
from backend.log import EventLog, EventType

DEFAULT_TIMEBOX_SECONDS = 300  # 单议题 5 分钟，可在构造时覆盖
TIMEBOX_WARNING_SECONDS = 60  # 4.1：小于 1 分钟变红


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RoundState:
    """一个议题的运行期状态（entity 是落库/对前端的那一份）。"""

    entity: DiscussionRound
    stage: Stage
    expected_speakers: tuple[AgentRole, ...] = ()
    spoken: list[AgentRole] = field(default_factory=list)
    message_count: int = 0
    deviation_count: int = 0
    summary: Optional[str] = None
    summary_data: Optional[dict] = None
    termination_reason: Optional[str] = None

    # ---------------------------------------------------------------- 查询
    def remaining_seconds(self, now: Optional[datetime] = None) -> int:
        if self.entity.timebox_end is None:
            return 0
        return max(0, int((self.entity.timebox_end - (now or utcnow())).total_seconds()))

    def is_timebox_expired(self, now: Optional[datetime] = None) -> bool:
        return self.entity.status == RoundStatus.ONGOING and self.remaining_seconds(now) == 0

    def is_timebox_warning(self, now: Optional[datetime] = None) -> bool:
        remaining = self.remaining_seconds(now)
        return 0 < remaining < TIMEBOX_WARNING_SECONDS

    def progress_label(self) -> str:
        return f"议题: {self.entity.topic} · 轮次 [{self.entity.round_no}]/[{self.entity.max_rounds}]"

    def to_dict(self, now: Optional[datetime] = None) -> dict:
        now = now or utcnow()
        payload = self.entity.model_dump(mode="json")
        payload.update(
            {
                "remaining_seconds": self.remaining_seconds(now),
                "timebox_warning": self.is_timebox_warning(now),
                "progress_label": self.progress_label(),
                "spoken": [role.value for role in self.spoken],
                "expected_speakers": [role.value for role in self.expected_speakers],
                "message_count": self.message_count,
                "deviation_count": self.deviation_count,
                "summary": self.summary,
                "termination_reason": self.termination_reason,
            }
        )
        return payload


@dataclass(frozen=True)
class RoundProgress:
    """一次发言之后的轮次进度。"""

    round_no: int
    spoken_count: int
    expected_count: int
    pass_complete: bool       # 是否刚好完成一遍（全体发完）
    advanced: bool            # 是否因此进入下一轮
    reached_max_rounds: bool  # 是否到 5 轮上限（需要 PM 强制收敛）
    round_status: RoundStatus

    def to_dict(self) -> dict:
        return {
            "round_no": self.round_no,
            "spoken_count": self.spoken_count,
            "expected_count": self.expected_count,
            "pass_complete": self.pass_complete,
            "advanced": self.advanced,
            "reached_max_rounds": self.reached_max_rounds,
            "round_status": self.round_status.value,
        }


class RoundController:
    """议题轮次状态机。只负责"轮"，不负责"谁该发言"（那是 PM 的职责）。"""

    def __init__(
        self,
        project_id: str,
        log: EventLog,
        *,
        max_rounds: int = MAX_ROUNDS,
        timebox_seconds: int = DEFAULT_TIMEBOX_SECONDS,
        clock=utcnow,
    ) -> None:
        if not 1 <= max_rounds <= MAX_ROUNDS:
            raise InvalidRoundConfig(f"max_rounds 必须在 1..{MAX_ROUNDS} 之间，收到 {max_rounds}")
        if timebox_seconds < 1:
            raise InvalidRoundConfig(f"timebox_seconds 必须 ≥ 1，收到 {timebox_seconds}")
        self.project_id = project_id
        self._log = log
        self._max_rounds = max_rounds
        self._timebox_seconds = timebox_seconds
        self._clock = clock
        self._lock = threading.RLock()
        self._current: Optional[RoundState] = None
        self._history: list[RoundState] = []

    # ---------------------------------------------------------------- 属性
    @property
    def current(self) -> Optional[RoundState]:
        return self._current

    @property
    def max_rounds(self) -> int:
        return self._max_rounds

    @property
    def timebox_seconds(self) -> int:
        return self._timebox_seconds

    @property
    def history(self) -> list[RoundState]:
        return list(self._history)

    def is_open(self) -> bool:
        return self._current is not None and self._current.entity.status == RoundStatus.ONGOING

    # ---------------------------------------------------------------- 开轮
    def open_round(
        self,
        *,
        topic: str,
        stage: Stage,
        expected_speakers: Sequence[AgentRole],
        round_no: int = 1,
        timebox_seconds: Optional[int] = None,
        actor: str = "PM",
    ) -> RoundState:
        if not topic or not topic.strip():
            raise InvalidRoundOperation("开题必须给出议题（topic）")
        with self._lock:
            if self.is_open():
                raise RoundNotOpen(
                    f"议题《{self._current.entity.topic}》尚在进行中，请先收敛或拉回",
                    round_no=self._current.entity.round_no,
                )
            seconds = timebox_seconds or self._timebox_seconds
            started = self._clock()
            entity = DiscussionRound(
                id=f"r-{uuid.uuid4().hex[:8]}",
                project_id=self.project_id,
                topic=topic.strip(),
                round_no=round_no,
                max_rounds=self._max_rounds,
                status=RoundStatus.ONGOING,
                timebox_end=started + timedelta(seconds=seconds),
            )
            state = RoundState(
                entity=entity,
                stage=stage,
                expected_speakers=tuple(expected_speakers),
            )
            self._current = state
            self._history.append(state)
        self._log.append(
            EventType.ROUND_OPENED,
            actor=actor,
            stage=stage,
            round_no=state.entity.round_no,
            payload={
                "topic": state.entity.topic,
                "max_rounds": entity.max_rounds,
                "timebox_seconds": seconds,
                "expected_speakers": [role.value for role in state.expected_speakers],
            },
        )
        return state

    # ---------------------------------------------------------------- 发言
    def record_turn(self, role: AgentRole) -> RoundProgress:
        """记录一次发言，返回本轮是否满员、是否触及 5 轮上限。"""
        with self._lock:
            state = self._require_open()
            state.message_count += 1
            if role not in state.spoken:
                state.spoken.append(role)

            expected_count = len(state.expected_speakers)
            spoken_count = len(state.spoken)
            pass_complete = expected_count > 0 and spoken_count >= expected_count
            advanced = False
            if pass_complete:
                if state.entity.round_no >= state.entity.max_rounds:
                    # 到顶：不再开新的一遍，等 PM 强制收敛（3.1）
                    return RoundProgress(
                        round_no=state.entity.round_no,
                        spoken_count=spoken_count,
                        expected_count=expected_count,
                        pass_complete=True,
                        advanced=False,
                        reached_max_rounds=True,
                        round_status=state.entity.status,
                    )
                state.entity.round_no += 1
                state.spoken.clear()
                advanced = True

            if advanced:
                self._log.append(
                    EventType.ROUND_ADVANCED,
                    actor="PM",
                    stage=state.stage,
                    round_no=state.entity.round_no,
                    payload={"topic": state.entity.topic, "max_rounds": state.entity.max_rounds},
                )
            return RoundProgress(
                round_no=state.entity.round_no,
                spoken_count=spoken_count,
                expected_count=expected_count,
                pass_complete=pass_complete,
                advanced=advanced,
                reached_max_rounds=False,
                round_status=state.entity.status,
            )

    def note_deviation(self, *, role: AgentRole, reason: str) -> int:
        """记录一次偏离，返回累计次数（PM 据此决定是否拉回）。"""
        with self._lock:
            state = self._require_open()
            state.deviation_count += 1
            count = state.deviation_count
            round_no = state.entity.round_no
            topic = state.entity.topic
        self._log.append(
            EventType.MESSAGE_DEVIATED,
            actor=role.value,
            role=role,
            stage=state.stage,
            round_no=round_no,
            payload={"reason": reason, "deviation_count": count, "topic": topic},
        )
        return count

    # ---------------------------------------------------------------- 收敛
    def converge(
        self,
        *,
        reason: str,
        summary: str,
        summary_data: Optional[dict] = None,
        actor: str = "PM",
    ) -> RoundState:
        """强制收敛：ONGOING → CONVERGED，并固化总结。"""
        with self._lock:
            state = self._require_open()
            state.entity.status = RoundStatus.CONVERGED
            state.summary = summary
            state.summary_data = summary_data or {}
            state.termination_reason = reason
            round_no = state.entity.round_no
            topic = state.entity.topic
        self._log.append(
            EventType.ROUND_CONVERGED,
            actor=actor,
            stage=state.stage,
            round_no=round_no,
            payload={
                "topic": topic,
                "reason": reason,
                "summary": summary,
                "message_count": state.message_count,
                "round_no": round_no,
            },
        )
        return state

    def terminate(self, *, reason: str, actor: str = "PM") -> RoundState:
        with self._lock:
            state = self._require_open()
            state.entity.status = RoundStatus.TERMINATED
            state.termination_reason = reason
            round_no = state.entity.round_no
            topic = state.entity.topic
        self._log.append(
            EventType.ROUND_TERMINATED,
            actor=actor,
            stage=state.stage,
            round_no=round_no,
            payload={"reason": reason, "topic": topic},
        )
        return state

    # ------------------------------------------------------------ 拉回清零
    def pull_back(
        self,
        *,
        reason: str,
        new_topic: str,
        actor: str = "human",
        stage: Optional[Stage] = None,
        expected_speakers: Optional[Sequence[AgentRole]] = None,
    ) -> RoundState:
        """人类「拉回主轴」：终止当前议题 → 轮次与偏离计数清零 → 用新议题重开。

        规格书 4.2：拉回必须填写理由 Prompt，否则不允许提交（R402）。
        """
        if not reason or not reason.strip():
            raise InvalidRoundOperation("拉回必须填写理由（4.2：必须填写拉回理由 Prompt）")
        if not new_topic or not new_topic.strip():
            raise InvalidRoundOperation("拉回后必须给出新的议题（new_topic）")

        with self._lock:
            state = self._require_open()
            state.entity.status = RoundStatus.TERMINATED
            state.termination_reason = f"人工拉回：{reason.strip()}"
            old_topic = state.entity.topic
            old_round_no = state.entity.round_no
            target_stage = stage or state.stage
            expected = tuple(expected_speakers) if expected_speakers else state.expected_speakers

        self._log.append(
            EventType.PULL_BACK,
            actor=actor,
            stage=target_stage,
            round_no=old_round_no,
            payload={
                "reason": reason.strip(),
                "old_topic": old_topic,
                "new_topic": new_topic.strip(),
                "reset": {"round_no": 1, "deviation_count": 0},
            },
        )
        self._log.append(
            EventType.ROUND_TERMINATED,
            actor=actor,
            stage=target_stage,
            round_no=old_round_no,
            payload={"reason": f"人工拉回：{reason.strip()}", "topic": old_topic},
        )
        # 清零：新实体 round_no = 1，deviation_count = 0（旧记录保留在 history 与事件流里）
        return self.open_round(
            topic=new_topic,
            stage=target_stage,
            expected_speakers=expected,
            round_no=1,
            actor=actor,
        )

    # ---------------------------------------------------------------- 时间
    def tick(self, now: Optional[datetime] = None) -> Optional[RoundState]:
        """时间盒巡检：到点返回该议题，由调用方触发「强制收敛」。"""
        now = now or self._clock()
        with self._lock:
            state = self._current
            if state is None or state.entity.status != RoundStatus.ONGOING:
                return None
            if not state.is_timebox_expired(now):
                return None
            return state

    def remaining_seconds(self, now: Optional[datetime] = None) -> int:
        with self._lock:
            return 0 if self._current is None else self._current.remaining_seconds(now)

    # ---------------------------------------------------------------- 内部
    def _require_open(self) -> RoundState:
        if self._current is None:
            raise RoundNotOpen("当前没有进行中的议题，请先开题")
        if self._current.entity.status != RoundStatus.ONGOING:
            raise RoundNotOpen(
                f"议题《{self._current.entity.topic}》已 {self._current.entity.status.value}，不再接收发言",
                round_no=self._current.entity.round_no,
            )
        return self._current
