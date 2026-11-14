"""编排引擎端到端：3.2 六条异常分支 + 3.1 路由规则 + 4.1 信号。"""

from __future__ import annotations

import json
import unittest

from fastapi import HTTPException

from backend.core.enums import (
    AgentRole,
    EntryStatus,
    GateStatus,
    ProjectStatus,
    RoundStatus,
    Stage,
)
from backend.core.models import AgentMessage, Signoff
from backend.log import EventType
from backend.orchestrator import Orchestrator
from backend.store import Store
from tests.support import FakeClock


def code_of(exc: HTTPException) -> str:
    return (exc.detail or {}).get("code", "") if isinstance(exc.detail, dict) else ""


class OrchestratorTest(unittest.TestCase):
    topic = "校园二手书交易小程序"

    def setUp(self) -> None:
        self.clock = FakeClock()
        self.store = Store()
        self.project = self.store.create_project(self.topic)
        self.pid = self.project.id
        self.orch = Orchestrator(self.store, timebox_seconds=300, clock=self.clock)
        self.orch.start(self.pid, self.topic)

    # ------------------------------------------------------------ 工具
    def approved_card(self, content: str = "痛点：二手书信息分散，交易靠群聊"):
        entry = self.orch.board.create_entry(
            self.pid,
            stage=Stage.IDEA,
            source_agent=AgentRole.BA,
            content=content,
            actor="BA",
        )
        entry, gate = self.orch.board.submit_for_review(entry.id, actor="BA")
        self.orch.board.decide_gate(gate.id, GateStatus.APPROVED, actor="human")
        return entry

    def make_message(
        self,
        role: AgentRole,
        content: str,
        references: list[str],
        *,
        stage: Stage | None = None,
        msg_id: str | None = None,
    ) -> AgentMessage:
        return AgentMessage(
            id=msg_id or f"m-{role.value}-{len(references)}-{abs(hash(content)) % 10000}",
            project_id=self.pid,
            stage=stage or self.project.current_stage,
            agent_role=role,
            content=content,
            references=references,
        )

    def say(self, role: AgentRole, content: str, references: list[str], **kwargs) -> dict:
        return self.orch.submit_message(self.make_message(role, content, references, **kwargs))

    def run_round_one(self) -> None:
        card = self.approved_card()
        self.say(AgentRole.BA, "目标用户是本校学生，痛点是找书难。", [card.id])
        self.say(AgentRole.UX, "建议先做搜索 + 站内私信两个核心动线。", [card.id])

    def advance_n(self, times: int) -> None:
        for _ in range(times):
            self.orch.force_converge(self.pid, reason="阶段收尾")
            target = self._next_stage(self.project.current_stage)
            self.orch.advance_stage(self.pid, target, f"确认进入 {target.value}")

    @staticmethod
    def _next_stage(stage: Stage) -> Stage:
        from backend.core.enums import STAGE_ORDER

        return STAGE_ORDER[STAGE_ORDER.index(stage) + 1]

    # ------------------------------------------------------------ 正常流程
    def test_start_opens_first_round(self) -> None:
        snapshot = self.orch.snapshot(self.pid)
        self.assertEqual(snapshot["project"]["current_stage"], Stage.IDEA.value)
        self.assertEqual(snapshot["round"]["round_no"], 1)
        self.assertEqual(
            snapshot["round"]["progress_label"],
            f"议题: {self.topic} · 轮次 [1]/[5]",
        )
        self.assertEqual(self.project.stage_status.value, "IN_PROGRESS")

    def test_happy_path_to_discussion(self) -> None:
        self.run_round_one()
        self.assertEqual(self.orch.runtime(self.pid).rounds.current.entity.round_no, 2)

        summary = self.orch.force_converge(self.pid)["summary"]
        self.assertIn("PM 收敛总结", summary["text"])

        result = self.orch.advance_stage(
            self.pid,
            Stage.DISCUSSION,
            "进入讨论阶段，聚焦 MVP 范围",
        )
        self.assertEqual(result["to"], Stage.DISCUSSION.value)
        snapshot = self.orch.snapshot(self.pid)
        self.assertEqual(snapshot["project"]["current_stage"], Stage.DISCUSSION.value)
        self.assertEqual(snapshot["round"]["topic"], "进入讨论阶段，聚焦 MVP 范围")
        self.assertEqual(snapshot["round"]["round_no"], 1)

    def test_max_rounds_auto_converge(self) -> None:
        """3.1：达到轮次上限由 PM 强制收敛（用 max_rounds=2 加速）。"""
        store = Store()
        project = store.create_project("轮次截断")
        orch = Orchestrator(store, max_rounds=2, clock=self.clock)
        orch.start(project.id, "轮次截断")
        entry = orch.board.create_entry(
            project.id,
            stage=Stage.IDEA,
            source_agent=AgentRole.BA,
            content="输入卡片",
            actor="BA",
        )
        entry, gate = orch.board.submit_for_review(entry.id, actor="BA")
        orch.board.decide_gate(gate.id, GateStatus.APPROVED, actor="human")

        for index in range(2):
            orch.submit_message(
                AgentMessage(
                    id=f"ba-{index}",
                    project_id=project.id,
                    stage=Stage.IDEA,
                    agent_role=AgentRole.BA,
                    content="观点",
                    references=[entry.id],
                )
            )
            result = orch.submit_message(
                AgentMessage(
                    id=f"ux-{index}",
                    project_id=project.id,
                    stage=Stage.IDEA,
                    agent_role=AgentRole.UX,
                    content="观点",
                    references=[entry.id],
                )
            )
        self.assertTrue(result["converged"])
        self.assertIn("PM 强制收敛", result["summary"]["reason"])

    def test_timebox_expiry_converges(self) -> None:
        self.clock.advance(seconds=300)
        result = self.orch.tick(self.pid)
        self.assertIsNotNone(result)
        self.assertEqual(
            self.orch.runtime(self.pid).log.count(EventType.TIMEBOX_EXPIRED),
            1,
        )
        self.assertEqual(
            self.orch.runtime(self.pid).rounds.current.entity.status,
            RoundStatus.CONVERGED,
        )

    # ------------------------------------------------ 3.1 发言门槛
    def test_empty_references_discarded(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.say(AgentRole.BA, "没有依据的一段话", [])
        self.assertEqual(code_of(ctx.exception), "E002")
        self.assertEqual(
            self.orch.runtime(self.pid).log.count(EventType.MESSAGE_DISCARDED),
            1,
        )

    def test_missing_reference_blocked(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.say(AgentRole.BA, "引用一个不存在的条目", ["e-not-exist"])
        self.assertEqual(code_of(ctx.exception), "E003")

    def test_stage_mismatch_blocked(self) -> None:
        card = self.approved_card()
        with self.assertRaises(HTTPException) as ctx:
            self.say(AgentRole.BA, "旧阶段的消息", [card.id], stage=Stage.PROPOSAL)
        self.assertEqual(code_of(ctx.exception), "E107")

    # ------------------------------------------------ 3.2 幻觉传染防御
    def test_hallucination_pauses_project(self) -> None:
        draft = self.orch.board.create_entry(
            self.pid,
            stage=Stage.IDEA,
            source_agent=AgentRole.BA,
            content="草稿：还没走门禁",
            actor="BA",
        )
        self.orch.force_converge(self.pid, reason="收尾")
        self.orch.advance_stage(self.pid, Stage.DISCUSSION, "进入讨论")

        with self.assertRaises(HTTPException) as ctx:
            self.say(AgentRole.BA, "顺着一张没过门的卡继续", [draft.id])
        self.assertEqual(code_of(ctx.exception), "E004")
        self.assertEqual(self.project.status, ProjectStatus.PAUSED)
        self.assertTrue(self.orch.snapshot(self.pid)["project"]["pause_reason"])

    def test_paused_project_rejects_further_messages(self) -> None:
        card = self.approved_card()
        self.project.status = ProjectStatus.PAUSED
        with self.assertRaises(HTTPException) as ctx:
            self.say(AgentRole.BA, "再说一句", [card.id])
        self.assertEqual(code_of(ctx.exception), "E005")

    # ------------------------------------------------ 3.2 袖手旁观防御
    def test_advance_requires_human_prompt(self) -> None:
        self.run_round_one()
        self.orch.force_converge(self.pid)
        with self.assertRaises(HTTPException) as ctx:
            self.orch.advance_stage(self.pid, Stage.DISCUSSION, "   ")
        self.assertEqual(code_of(ctx.exception), "E101")

    def test_advance_rejects_skip_stage(self) -> None:
        self.run_round_one()
        self.orch.force_converge(self.pid)
        with self.assertRaises(HTTPException) as ctx:
            self.orch.advance_stage(self.pid, Stage.PROPOSAL, "跳阶段")
        self.assertEqual(code_of(ctx.exception), "E102")

    # ------------------------------------------------ 4.1 门禁红点
    def test_pending_gate_blocks_advance(self) -> None:
        entry = self.orch.board.create_entry(
            self.pid,
            stage=Stage.IDEA,
            source_agent=AgentRole.BA,
            content="等待门禁的卡片",
            actor="BA",
        )
        self.orch.board.submit_for_review(entry.id, actor="BA")
        self.orch.force_converge(self.pid)
        with self.assertRaises(HTTPException) as ctx:
            self.orch.advance_stage(self.pid, Stage.DISCUSSION, "推进")
        self.assertEqual(code_of(ctx.exception), "E104")

    def test_pending_entry_blocks_advance(self) -> None:
        entry = self.orch.board.create_entry(
            self.pid,
            stage=Stage.IDEA,
            source_agent=AgentRole.BA,
            content="待审卡片",
            actor="BA",
        )
        entry, gate = self.orch.board.submit_for_review(entry.id, actor="BA")
        gate.gate_status = GateStatus.APPROVED  # 门禁已被处理，但条目仍停在 PENDING_REVIEW
        self.orch.force_converge(self.pid)
        with self.assertRaises(HTTPException) as ctx:
            self.orch.advance_stage(self.pid, Stage.DISCUSSION, "推进")
        self.assertEqual(code_of(ctx.exception), "E105")

    def test_advance_before_converge_blocked(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.orch.advance_stage(self.pid, Stage.DISCUSSION, "推进")
        self.assertEqual(code_of(ctx.exception), "R401")

    # ------------------------------------------------ T4 偏离拉回清零
    def test_deviation_pull_back_resets(self) -> None:
        store = Store()
        project = store.create_project("偏离测试")
        orch = Orchestrator(
            store,
            clock=self.clock,
            deviation_judge=lambda topic, content: "食堂" in content,
        )
        orch.start(project.id, "校园二手书交易")
        entry = orch.board.create_entry(
            project.id,
            stage=Stage.IDEA,
            source_agent=AgentRole.BA,
            content="输入卡片",
            actor="BA",
        )
        entry, gate = orch.board.submit_for_review(entry.id, actor="BA")
        orch.board.decide_gate(gate.id, GateStatus.APPROVED, actor="human")

        def send(role: AgentRole, index: int) -> dict:
            return orch.submit_message(
                AgentMessage(
                    id=f"m-{index}",
                    project_id=project.id,
                    stage=Stage.IDEA,
                    agent_role=role,
                    content="顺带聊聊食堂的新窗口。",
                    references=[entry.id],
                )
            )

        first = send(AgentRole.BA, 1)
        self.assertTrue(first["accepted"])  # 第一次只警告

        second = send(AgentRole.UX, 2)
        self.assertTrue(second["pulled_back"])
        state = orch.runtime(project.id).rounds.current
        self.assertEqual(state.entity.round_no, 1)  # 清零
        self.assertEqual(state.deviation_count, 0)  # 清零
        self.assertEqual(state.entity.status, RoundStatus.ONGOING)

    def test_pull_back_requires_reason(self) -> None:
        self.run_round_one()
        with self.assertRaises(HTTPException) as ctx:
            self.orch.pull_back(self.pid, reason="  ")
        self.assertEqual(code_of(ctx.exception), "R402")

    # ------------------------------------------------ 冻结基线（T10 联动）
    def test_freeze_flow_locks_blackboard(self) -> None:
        self.advance_n(5)
        self.assertEqual(self.project.current_stage, Stage.CONFIRMATION)

        self.orch.force_converge(self.pid, reason="会签前收尾")

        # 会签未全绿 → 不允许冻结（B102）
        with self.assertRaises(HTTPException) as ctx:
            self.orch.freeze_baseline(self.pid, scope="全部 APPROVED 条目")
        self.assertEqual(code_of(ctx.exception), "B102")

        for party in ("business", "development", "testing"):
            self.store.add_signoff(
                Signoff(
                    id=f"s-{party}",
                    project_id=self.pid,
                    party=party,
                    status=EntryStatus.APPROVED,
                )
            )
        result = self.orch.freeze_baseline(self.pid, scope="全部 APPROVED 条目")
        self.assertEqual(result["project_status"], ProjectStatus.FROZEN.value)
        self.assertEqual(self.project.status, ProjectStatus.FROZEN)

        # 冻结后黑板只读（B301）
        with self.assertRaises(HTTPException) as ctx:
            self.orch.board.create_entry(
                self.pid,
                stage=Stage.CONFIRMATION,
                source_agent=AgentRole.PM,
                content="冻结后新增",
                actor="human",
            )
        self.assertEqual(code_of(ctx.exception), "B301")

    def test_signoff_timeout_escalation(self) -> None:
        self.advance_n(5)
        self.orch.force_converge(self.pid, reason="会签前收尾")
        self.clock.advance(hours=25)
        text = self.orch.check_signoff_timeout(self.pid)
        self.assertIsNotNone(text)
        self.assertIn("24", text)
        self.assertGreaterEqual(self.orch.runtime(self.pid).log.count(EventType.ESCALATION), 1)

    # ------------------------------------------------ 4.1 信号
    def test_snapshot_supports_dashboard(self) -> None:
        snapshot = self.orch.snapshot(self.pid)
        for key in ("project", "round", "agents", "gates", "board", "signoff", "pm"):
            self.assertIn(key, snapshot)
        self.assertFalse(snapshot["gates"]["red_dot"])
        self.assertEqual(len(snapshot["project"]["stages"]), 6)

        agents = {item["role"]: item for item in snapshot["agents"]}
        self.assertEqual(agents[AgentRole.BA.value]["state"], "NEXT")
        self.assertTrue(all(not item["dimmed"] for item in snapshot["agents"]))

    def test_event_stream_incremental(self) -> None:
        self.run_round_one()
        first = self.orch.events(self.pid, after_seq=0)
        self.assertTrue(len(first["items"]) > 0)
        second = self.orch.events(self.pid, after_seq=first["last_seq"])
        self.assertEqual(second["items"], [])

    def test_snapshot_is_json_serializable(self) -> None:
        """HTTP 层会直接 json 序列化，datetime/enum 必须在服务层就转好。"""
        self.run_round_one()
        payload = self.orch.snapshot(self.pid)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("progress_label", text)
        self.assertIn("round", text)


if __name__ == "__main__":
    unittest.main()
