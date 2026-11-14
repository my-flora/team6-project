"""编排引擎（Orchestrator）—— 第二部分门面（Owner：张嘉辉）。

把 T2 黑板、T4 轮次、发言事件流、PM 调度组装成一条可执行的流水线：

    人类开题 → 开轮 → Agent 发言（门禁校验 → 引用校验 → 轮次推进）
             → 到达 5 轮 / 时间盒到点 / 人类强制收敛 → PM 输出总结
             → 人类推进阶段（门禁红点、空 Prompt、待审条目全部拦截）
             → 阶段 6 冻结基线（复用 T10 的 BaselineService）

设计约定（与第一部分对齐）：
    * 服务无状态、以 `store` 为准：`Orchestrator(store)` 一个实例服务所有项目，
      每个项目的运行期状态（当前议题、事件流、暂停原因）放在 `_runtimes` 里；
    * 发言门槛、引用校验 **直接调用** `GateService.validate_agent_message`（E001-E005），
      不重复实现规则，保证两条链路的判定完全一致；
    * 冻结与只读直接走 `BaselineService`（B101-B103 / B301）。

规格书 3.2 六条异常分支的落点：
    幻觉传染防御 -> GateService E004（action=PROJECT_PAUSED）-> 本引擎置 PAUSED
    无限发散防御 -> 轮次上限 / 时间盒 / 人类拉回 -> CONVERGED + PM 总结
    袖手旁观防御 -> GateService E101（空 human_prompt_input）
    红蓝死锁     -> pause_project()（T7.5 调用）
    评审驳回     -> reject_stage()（T7.5 调用）
    基线超时未签 -> check_signoff_timeout() -> PM 升级告警
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from fastapi import HTTPException

from agents.roles.pm import PMAgent
from backend.baseline.service import BaselineService
from backend.blackboard.service import BlackboardService
from backend.core.enums import (
    MAX_ROUNDS,
    AgentRole,
    EntryStatus,
    ProjectStatus,
    RoundStatus,
    Stage,
)
from backend.core.models import AgentMessage, Project
from backend.errors import (
    GatePendingBlocksAdvance,
    InvalidRoundConfig,
    InvalidRoundOperation,
    PendingEntryBlocksAdvance,
    ProjectNotFound,
    RoundNotOpen,
    StageMismatch,
)
from backend.gate.service import GateService
from backend.log import EventLog, EventType
from backend.orchestrator.rounds import (
    DEFAULT_TIMEBOX_SECONDS,
    RoundController,
    RoundProgress,
    RoundState,
    utcnow,
)
from backend.orchestrator.stages import StageMachine, stage_label
from backend.store import Store

DEFAULT_DEVIATION_THRESHOLD = 2
SIGNOFF_TIMEOUT_HOURS = 24

#: 偏离判定钩子：给定 (议题, 发言内容) 返回 True 表示判定为偏离。
#: 默认不启用（None），避免中文关键词匹配误伤；接入语义判定时由调用方注入。
DeviationJudge = Callable[[str, str], bool]


@dataclass
class ProjectRuntime:
    """单个项目的运行期状态（进程内，重启即清空）。"""

    project_id: str
    log: EventLog
    rounds: RoundController
    pm: PMAgent
    pause_reason: Optional[str] = None
    signoff_started_at: Optional[datetime] = None


class Orchestrator:
    """编排门面。线程安全，供 HTTP 层与测试直接调用。"""

    def __init__(
        self,
        store: Store,
        *,
        blackboard: Optional[BlackboardService] = None,
        gate_service: Optional[GateService] = None,
        baseline_service: Optional[BaselineService] = None,
        max_rounds: int = MAX_ROUNDS,
        timebox_seconds: int = DEFAULT_TIMEBOX_SECONDS,
        deviation_threshold: int = DEFAULT_DEVIATION_THRESHOLD,
        deviation_judge: Optional[DeviationJudge] = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        if deviation_threshold < 1:
            raise InvalidRoundConfig("deviation_threshold 必须 ≥ 1")
        self.store = store
        self.gate = gate_service or GateService()
        self.baseline = baseline_service or BaselineService(store)
        self.board = blackboard or BlackboardService(
            store,
            gate_service=self.gate,
            baseline_service=self.baseline,
        )
        self._max_rounds = max_rounds
        self._timebox_seconds = timebox_seconds
        self._deviation_threshold = deviation_threshold
        self._deviation_judge = deviation_judge
        self._clock = clock
        self._runtimes: dict[str, ProjectRuntime] = {}
        self._lock = threading.RLock()

    # ============================================================== 运行时
    def runtime(self, project_id: str) -> ProjectRuntime:
        with self._lock:
            runtime = self._runtimes.get(project_id)
            if runtime is not None:
                return runtime
            self._require_project(project_id)
            log = EventLog(project_id, clock=self._clock)
            runtime = ProjectRuntime(
                project_id=project_id,
                log=log,
                rounds=RoundController(
                    project_id,
                    log,
                    max_rounds=self._max_rounds,
                    timebox_seconds=self._timebox_seconds,
                    clock=self._clock,
                ),
                pm=PMAgent(log),
            )
            self._runtimes[project_id] = runtime
            return runtime

    def stages_of(self, project_id: str) -> StageMachine:
        return StageMachine(self._require_project(project_id))

    # ================================================================ 开题
    def start(self, project_id: str, topic: str, *, actor: str = "human") -> dict:
        """进入阶段 1 并打开第一个议题。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        with self._lock:
            if runtime.rounds.current is not None:
                raise RoundNotOpen(
                    "该项目已经开过题，请勿重复 start",
                    project_id=project_id,
                )
            if not topic or not topic.strip():
                raise InvalidRoundOperation("开题必须给出议题（topic）")
            stages = StageMachine(project)
            stages.start()
            runtime.log.append(
                EventType.PROJECT_STARTED,
                actor=actor,
                stage=project.current_stage,
                payload={"topic": topic.strip(), "project_id": project_id},
            )
            self._open_round(project, runtime, topic=topic.strip())
        return self.snapshot(project_id)

    # ============================================================ Agent 发言
    def submit_message(self, message: AgentMessage, *, actor: Optional[str] = None) -> dict:
        """接收一条 Agent 发言（AgentMessageRequest），返回引擎处理结果。"""
        project = self._require_project(message.project_id)
        runtime = self.runtime(message.project_id)

        # ① 契约校验 / 发言门槛：完全复用 T3 的 GateService（E001-E005）
        referenced = {entry.id: entry for entry in self.store.get_entries(project.id)}
        try:
            self.gate.validate_agent_message(message, referenced, project)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            if detail.get("code") == "E004":
                # 幻觉传染防御：引用未 APPROVED 条目 → 项目 PAUSED
                StageMachine(project).pause()
                runtime.pause_reason = detail.get("message", "引用未通过门禁的上游条目")
                runtime.log.append(
                    EventType.PROJECT_PAUSED,
                    actor="system",
                    stage=project.current_stage,
                    payload={"reason": runtime.pause_reason, "entry_reference": message.references},
                )
            elif detail.get("code") == "E002":
                runtime.log.append(
                    EventType.MESSAGE_DISCARDED,
                    actor=message.agent_role.value,
                    role=message.agent_role,
                    stage=project.current_stage,
                    round_no=message.round_no,
                    payload={"code": "E002", "reason": detail.get("message", "空引用")},
                )
            raise

        # ② 阶段必须一致（旧阶段的消息不应再被接纳）
        if message.stage != project.current_stage:
            raise StageMismatch(
                f"发言所属阶段 {message.stage.value} 与当前阶段 {project.current_stage.value} 不一致",
                message_stage=message.stage.value,
                current_stage=project.current_stage.value,
            )

        # ③ 必须有进行中的议题
        if not runtime.rounds.is_open():
            raise RoundNotOpen(
                "当前没有进行中的议题，请等待人类推进阶段或由 PM 重新开题",
                current_stage=project.current_stage.value,
            )

        state = runtime.rounds.current
        assert state is not None

        # ④ 偏离检查：命中钩子则累计，连续越界由 PM 拉回清零（T4）
        if self._deviation_judge is not None and self._deviation_judge(state.entity.topic, message.content):
            count = runtime.rounds.note_deviation(
                role=message.agent_role,
                reason="发言与当前议题的相关度过低",
            )
            if count >= self._deviation_threshold:
                pulled = self._auto_pull_back(project, runtime, role=message.agent_role)
                return {
                    "accepted": False,
                    "pulled_back": True,
                    "code": "R404",
                    "deviation_count": count,
                    "reason": f"连续偏离 {count} 次，PM 已拉回清零",
                    "round": pulled.to_dict(self._clock()),
                }
            runtime.pm.deviation_warning(
                role=message.agent_role,
                reason="发言与当前议题的相关度过低",
                count=count,
            )

        # ⑤ 接纳发言 + 轮次推进
        message_round = state.entity.round_no
        progress: RoundProgress = runtime.rounds.record_turn(message.agent_role)
        runtime.log.append(
            EventType.MESSAGE_ACCEPTED,
            actor=message.agent_role.value,
            role=message.agent_role,
            stage=project.current_stage,
            round_no=message_round,
            payload={
                "content": message.content,
                "references": list(message.references),
                "topic": state.entity.topic,
                "message_id": message.id,
            },
        )

        result: dict[str, Any] = {
            "accepted": True,
            "message_id": message.id,
            "round_no": message_round,
            "progress": progress.to_dict(),
            "converged": None,
            "summary": None,
        }

        # ⑥ 触顶 → PM 强制收敛（3.1：达到 5 轮自动截断）
        if progress.reached_max_rounds:
            summary = self._converge(
                project,
                runtime,
                reason=f"达到最大轮次 {runtime.rounds.max_rounds}，PM 强制收敛",
            )
            result["converged"] = True
            result["summary"] = summary
        return result

    # ============================================================== 人类操作
    def pull_back(
        self,
        project_id: str,
        *,
        reason: str,
        new_topic: Optional[str] = None,
        actor: str = "human",
    ) -> dict:
        """人类「拉回主轴」：终止当前议题并清零重开（4.2）。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        if project.status == ProjectStatus.FROZEN:
            raise RoundNotOpen("项目已冻结，不可拉回")
        if runtime.rounds.current is None:
            raise RoundNotOpen("当前没有进行中的议题，无法拉回")
        if not (reason or "").strip():
            raise InvalidRoundOperation("拉回必须填写理由（4.2：必须填写拉回理由 Prompt）")
        target_topic = (new_topic or "").strip() or runtime.rounds.current.entity.topic
        state = runtime.rounds.pull_back(
            reason=reason.strip(),
            new_topic=target_topic,
            actor=actor,
            stage=project.current_stage,
            expected_speakers=runtime.pm.agenda_for(project.current_stage),
        )
        # 拉回是恢复动作：若之前因幻觉传染被 PAUSED，人类已重新给题 → 恢复运行
        if project.status == ProjectStatus.PAUSED:
            StageMachine(project).resume()
            runtime.pause_reason = None
        return {"ok": True, "round": state.to_dict(self._clock())}

    def force_converge(self, project_id: str, *, reason: Optional[str] = None, actor: str = "human") -> dict:
        """人类强制收敛（4.2：只能在 ONGOING 状态执行）。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        if not runtime.rounds.is_open():
            raise RoundNotOpen(
                "只有进行中的议题才能强制收敛",
                status=runtime.rounds.current.entity.status.value if runtime.rounds.current else None,
            )
        summary = self._converge(project, runtime, reason=reason or "人类强制收敛", actor=actor)
        return {"ok": True, "summary": summary}

    def open_topic(
        self,
        project_id: str,
        topic: str,
        *,
        timebox_seconds: Optional[int] = None,
        actor: str = "PM",
    ) -> dict:
        """PM 在当前阶段开新议题（收敛后可继续讨论）。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        if project.status != ProjectStatus.RUNNING:
            raise RoundNotOpen(f"项目状态为 {project.status.value}，不能开新议题")
        state = self._open_round(project, runtime, topic=topic, timebox_seconds=timebox_seconds)
        return {"ok": True, "round": state.to_dict(self._clock())}

    # ============================================================== 阶段推进
    def advance_stage(
        self,
        project_id: str,
        target_stage: Stage,
        human_prompt_input: str,
        *,
        actor: str = "human",
    ) -> dict:
        """阶段推进：空 Prompt（E101）、跳阶段（E102）、冻结（E103）、
        门禁红点（E104）、待审条目（E105）、议题未收敛（R401）逐条拦截。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)

        # 3.2 袖手旁观防御 + 3.1 阶段顺序：直接复用 T3 的校验
        self.gate.validate_stage_advance(project, target_stage, human_prompt_input)

        current = project.current_stage
        pending = self.store.pending_gate_count(project_id)
        if pending > 0:
            runtime.pm.pending_gate_reminder(pending=pending, stage=current)
            StageMachine(project).set_waiting_human()
            raise GatePendingBlocksAdvance(
                f"{stage_label(current)} 还有 {pending} 项门禁待处理，请先在门禁面板通过/驳回",
                pending_gates=pending,
            )

        pending_entries = self.board.list_entries(project_id, stage=current, status=EntryStatus.PENDING_REVIEW)
        if pending_entries:
            raise PendingEntryBlocksAdvance(
                f"{stage_label(current)} 还有 {len(pending_entries)} 条黑板条目处于 PENDING_REVIEW",
                pending_entries=[entry.id for entry in pending_entries],
            )

        if runtime.rounds.is_open():
            raise RoundNotOpen(
                "当前议题仍在进行中，请先收敛（或让 PM 自动收敛）再推进阶段",
                topic=runtime.rounds.current.entity.topic,
                round_no=runtime.rounds.current.entity.round_no,
            )

        stages = StageMachine(project)
        stages.complete_current()
        stages.advance_to(target_stage)
        stages.clear_waiting_human()
        runtime.pause_reason = None

        runtime.log.append(
            EventType.STAGE_ADVANCED,
            actor=actor,
            stage=target_stage,
            payload={
                "from_stage": current.value,
                "to_stage": target_stage.value,
                "human_prompt_input": human_prompt_input,
            },
        )
        if target_stage == Stage.CONFIRMATION:
            runtime.signoff_started_at = self._clock()
        self._open_round(project, runtime, topic=human_prompt_input[:120])
        return {"ok": True, "from": current.value, "to": target_stage.value, **self.snapshot(project_id)}

    def freeze_baseline(
        self,
        project_id: str,
        *,
        scope: str,
        source_entry_ids: Optional[list[str]] = None,
        human_prompt_input: str = "确认冻结基线",
        actor: str = "human",
    ) -> dict:
        """冻结基线：复用 T10 的 BaselineService（会签全绿 + 黑板只读）。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        if not human_prompt_input.strip():
            raise InvalidRoundOperation("冻结基线同样需要人类确认 Prompt（E101 同理）")
        if runtime.rounds.is_open():
            raise RoundNotOpen("会签阶段仍在讨论中，请先收敛再冻结基线")
        pending = self.store.pending_gate_count(project_id)
        if pending > 0:
            raise GatePendingBlocksAdvance(f"还有 {pending} 项门禁待处理，冻结前必须清零")

        baseline = self.baseline.freeze_baseline(project_id, scope, list(source_entry_ids or []))
        StageMachine(project).freeze()
        runtime.log.append(
            EventType.PROJECT_FROZEN,
            actor=actor,
            stage=project.current_stage,
            payload={"baseline_id": baseline.id, "version": baseline.version, "scope": scope},
        )
        return {
            "ok": True,
            "baseline_id": baseline.id,
            "version": baseline.version,
            "frozen_at": baseline.frozen_at.isoformat() if baseline.frozen_at else None,
            "project_status": project.status.value,
            **self.snapshot(project_id),
        }

    # ================================================================ 巡检
    def tick(self, project_id: str, now: Optional[datetime] = None) -> Optional[dict]:
        """时间盒巡检：前端每 1 秒调用一次，到点自动强制收敛。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        state = runtime.rounds.tick(now)
        if state is None:
            return None
        runtime.log.append(
            EventType.TIMEBOX_EXPIRED,
            actor="system",
            stage=project.current_stage,
            round_no=state.entity.round_no,
            payload={"topic": state.entity.topic, "timebox_seconds": runtime.rounds.timebox_seconds},
        )
        summary = self._converge(project, runtime, reason="时间盒到期，PM 强制收敛")
        return {"converged": True, "summary": summary}

    def check_signoff_timeout(self, project_id: str, *, now: Optional[datetime] = None) -> Optional[str]:
        """3.2 基线超时未签：会签发起 24 小时仍未全绿 → PM 升级告警。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        if project.current_stage != Stage.CONFIRMATION or project.status == ProjectStatus.FROZEN:
            return None
        if runtime.signoff_started_at is None:
            return None
        signoffs = self.store.get_signoffs(project_id)
        if len(signoffs) >= 3 and all(s.status == EntryStatus.APPROVED for s in signoffs):
            return None
        now = now or self._clock()
        elapsed = now - runtime.signoff_started_at
        if elapsed < timedelta(hours=SIGNOFF_TIMEOUT_HOURS):
            return None
        return runtime.pm.signoff_timeout_alert(
            hours=int(elapsed.total_seconds() // 3600),
            timeout_hours=SIGNOFF_TIMEOUT_HOURS,
        )

    # ------------------------------------------------------------ 供 T7.5 调用
    def pause_project(self, project_id: str, *, reason: str) -> None:
        """3.2 红蓝死锁：方案改 2 次仍被 REJECTED → 挂起，等人类拍板。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        StageMachine(project).pause()
        runtime.pause_reason = reason
        runtime.log.append(
            EventType.PROJECT_PAUSED,
            actor="PM",
            stage=project.current_stage,
            payload={"reason": reason},
        )

    def resume_project(self, project_id: str, *, reason: str = "人工恢复", actor: str = "human") -> dict:
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        StageMachine(project).resume()
        runtime.pause_reason = None
        runtime.log.append(
            EventType.PROJECT_RESUMED,
            actor=actor,
            stage=project.current_stage,
            payload={"reason": reason},
        )
        return {"ok": True, **self.snapshot(project_id)}

    def reject_stage(self, project_id: str, *, reason: str) -> None:
        """3.2 评审驳回：阶段置 REJECTED，等待回退到 Proposal（T7.5 调用）。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        StageMachine(project).mark_rejected()
        runtime.log.append(
            EventType.STAGE_REJECTED,
            actor="PM",
            stage=project.current_stage,
            payload={"reason": reason},
        )

    # ================================================================ 视图
    def snapshot(self, project_id: str) -> dict:
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        stages = StageMachine(project)
        state = runtime.rounds.current
        pending = self.store.pending_gate_count(project_id)
        signoffs = self.store.get_signoffs(project_id)

        return {
            "project_id": project_id,
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status.value,
                "current_stage": project.current_stage.value,
                "current_stage_label": stage_label(project.current_stage),
                "stage_status": project.stage_status.value,
                "pause_reason": runtime.pause_reason,
                **stages.to_dict(),
            },
            "round": state.to_dict(self._clock()) if state else None,
            "agents": self.agent_status(project_id),
            "gates": {"pending": pending, "red_dot": pending > 0},
            "board": self.board.stats(project_id),
            "signoff": {
                "parties": [
                    {"party": s.party, "status": s.status.value, "signed_by": s.signed_by}
                    for s in signoffs
                ],
                "all_approved": len(signoffs) >= 3
                and all(s.status == EntryStatus.APPROVED for s in signoffs),
                "started_at": runtime.signoff_started_at.isoformat()
                if runtime.signoff_started_at
                else None,
            },
            "log": {"last_seq": runtime.log.last_seq},
            "pm": {
                "agenda": [role.value for role in runtime.pm.agenda_for(project.current_stage)],
                "last_summary": state.summary if state else None,
            },
        }

    def agent_status(self, project_id: str) -> list[dict]:
        """Agent 状态灯（4.1）：ONGOING 时轮流闪烁；WAITING_HUMAN / PAUSED 时全灰。"""
        project = self._require_project(project_id)
        runtime = self.runtime(project_id)
        state = runtime.rounds.current
        agenda = runtime.pm.agenda_for(project.current_stage)
        last_events = runtime.log.last_event_of_role()

        speaking_allowed = (
            project.status == ProjectStatus.RUNNING
            and state is not None
            and state.entity.status == RoundStatus.ONGOING
            and bool(agenda)
        )
        next_speaker = None
        if speaking_allowed and state is not None:
            for role in agenda:
                if role not in state.spoken:
                    next_speaker = role
                    break

        items: list[dict] = []
        for role in agenda:
            last = last_events.get(role.value)
            if not speaking_allowed:
                state_name = "IDLE"
            elif state is not None and role in state.spoken:
                state_name = "DONE"
            elif role is next_speaker:
                state_name = "NEXT"
            else:
                state_name = "WAITING"
            items.append(
                {
                    "role": role.value,
                    "state": state_name,
                    "last_at": last.ts if last else None,
                    "last_seq": last.seq if last else None,
                    "dimmed": not speaking_allowed,
                }
            )
        return items

    def events(self, project_id: str, *, after_seq: int = 0, limit: int = 200) -> dict:
        runtime = self.runtime(project_id)
        items = runtime.log.list_events(after_seq=after_seq, limit=limit)
        return {
            "items": [event.to_dict() for event in items],
            "last_seq": runtime.log.last_seq,
            "has_more": bool(items) and items[-1].seq < runtime.log.last_seq,
        }

    def events_of_round(self, project_id: str, round_no: int) -> list[dict]:
        runtime = self.runtime(project_id)
        return [event.to_dict() for event in runtime.log.messages_of_round(round_no)]

    # ================================================================ 内部
    def _open_round(
        self,
        project: Project,
        runtime: ProjectRuntime,
        *,
        topic: str,
        timebox_seconds: Optional[int] = None,
    ) -> RoundState:
        state = runtime.rounds.open_round(
            topic=topic,
            stage=project.current_stage,
            expected_speakers=runtime.pm.agenda_for(project.current_stage),
            timebox_seconds=timebox_seconds,
        )
        runtime.log.append(
            EventType.ESCALATION,
            actor="PM",
            stage=project.current_stage,
            round_no=state.entity.round_no,
            payload={
                "level": "info",
                "title": "PM 开题",
                "detail": runtime.pm.opening_note(
                    stage=project.current_stage,
                    topic=state.entity.topic,
                    round_no=state.entity.round_no,
                    max_rounds=state.entity.max_rounds,
                ),
            },
        )
        return state

    def _converge(self, project: Project, runtime: ProjectRuntime, *, reason: str, actor: str = "PM") -> dict:
        state = runtime.rounds.current
        if state is None or state.entity.status != RoundStatus.ONGOING:
            raise RoundNotOpen("当前没有可收敛的议题")
        messages = [
            event
            for event in runtime.log.list_events(types=[EventType.MESSAGE_ACCEPTED], limit=10_000)
            if event.payload.get("topic") == state.entity.topic
        ]
        summary = runtime.pm.summarize(
            topic=state.entity.topic,
            round_no=state.entity.round_no,
            reason=reason,
            messages=messages,
        )
        runtime.rounds.converge(
            reason=reason,
            summary=summary.text,
            summary_data=summary.to_dict(),
            actor=actor,
        )
        return summary.to_dict()

    def _auto_pull_back(self, project: Project, runtime: ProjectRuntime, *, role: AgentRole) -> RoundState:
        state = runtime.rounds.current
        assert state is not None
        topic = state.entity.topic
        reason = f"连续偏离议题 {self._deviation_threshold} 次（最近一条来自 {role.value}）"
        new_state = runtime.rounds.pull_back(
            reason=reason,
            new_topic=topic,
            actor="PM",
            stage=project.current_stage,
            expected_speakers=runtime.pm.agenda_for(project.current_stage),
        )
        runtime.pm.escalation(
            title="偏离拉回清零",
            detail=f"【PM】{reason}，已终止当前讨论并把轮次清零重开，请各 Agent 回到议题《{topic}》。",
            level="warning",
        )
        return new_state

    def _require_project(self, project_id: str) -> Project:
        project = self.store.get_project(project_id)
        if project is None:
            raise ProjectNotFound(f"项目不存在：{project_id}", project_id=project_id)
        return project
