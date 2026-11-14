"""T4 轮次控制：5 轮截断、时间盒、强制收敛、拉回清零。"""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from backend.core.enums import AgentRole, RoundStatus, Stage
from backend.log import EventLog, EventType
from backend.orchestrator.rounds import RoundController
from tests.support import FakeClock


def code_of(exc: HTTPException) -> str:
    return (exc.detail or {}).get("code", "") if isinstance(exc.detail, dict) else ""


class RoundControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.log = EventLog("PRJ-T4", clock=self.clock)
        self.controller = RoundController(
            "PRJ-T4",
            self.log,
            max_rounds=5,
            timebox_seconds=300,
            clock=self.clock,
        )
        self.speakers = (AgentRole.BA, AgentRole.UX)

    def open(self, topic: str = "校园二手书交易") -> None:
        self.controller.open_round(
            topic=topic,
            stage=Stage.IDEA,
            expected_speakers=self.speakers,
        )

    # ------------------------------------------------------- 轮次推进
    def test_round_no_advances_after_full_pass(self) -> None:
        self.open()
        first = self.controller.record_turn(AgentRole.BA)
        self.assertFalse(first.pass_complete)
        self.assertEqual(first.round_no, 1)

        second = self.controller.record_turn(AgentRole.UX)
        self.assertTrue(second.pass_complete)
        self.assertTrue(second.advanced)
        self.assertEqual(second.round_no, 2)

    def test_five_rounds_truncate(self) -> None:
        """3.1：单议题达到 5 轮必须触发强制收敛信号。"""
        self.open()
        for _ in range(4):
            self.controller.record_turn(AgentRole.BA)
            progress = self.controller.record_turn(AgentRole.UX)
            self.assertFalse(progress.reached_max_rounds)

        self.controller.record_turn(AgentRole.BA)
        last = self.controller.record_turn(AgentRole.UX)
        self.assertTrue(last.reached_max_rounds)
        self.assertEqual(last.round_no, 5)
        self.assertFalse(last.advanced)

    def test_progress_label_matches_spec(self) -> None:
        self.open("测试议题")
        self.assertEqual(
            self.controller.current.progress_label(),
            "议题: 测试议题 · 轮次 [1]/[5]",
        )

    # ------------------------------------------------------- 时间盒
    def test_timebox_expiry(self) -> None:
        self.open()
        self.assertIsNone(self.controller.tick())
        self.clock.advance(seconds=299)
        self.assertIsNone(self.controller.tick())
        self.clock.advance(seconds=1)
        self.assertIsNotNone(self.controller.tick())

    def test_timebox_warning_under_one_minute(self) -> None:
        self.open()
        self.clock.advance(seconds=245)  # 剩 55 秒
        self.assertTrue(self.controller.current.is_timebox_warning(self.clock()))
        self.assertEqual(self.controller.remaining_seconds(self.clock()), 55)

    def test_tick_ignores_converged_round(self) -> None:
        self.open()
        self.controller.converge(reason="人工", summary="总结")
        self.clock.advance(minutes=10)
        self.assertIsNone(self.controller.tick())

    # ------------------------------------------------------- 收敛
    def test_converge_twice_is_rejected(self) -> None:
        self.open()
        self.controller.converge(reason="达到上限", summary="总结")
        self.assertEqual(self.controller.current.entity.status, RoundStatus.CONVERGED)
        with self.assertRaises(HTTPException) as ctx:
            self.controller.converge(reason="再来一次", summary="总结")
        self.assertEqual(code_of(ctx.exception), "R401")

    def test_cannot_speak_after_convergence(self) -> None:
        self.open()
        self.controller.converge(reason="人工", summary="总结")
        with self.assertRaises(HTTPException):
            self.controller.record_turn(AgentRole.BA)

    # ------------------------------------------------------- 拉回清零
    def test_pull_back_requires_reason(self) -> None:
        self.open()
        with self.assertRaises(HTTPException) as ctx:
            self.controller.pull_back(reason="   ", new_topic="新议题")
        self.assertEqual(code_of(ctx.exception), "R402")

    def test_pull_back_requires_new_topic(self) -> None:
        self.open()
        with self.assertRaises(HTTPException):
            self.controller.pull_back(reason="跑偏了", new_topic="")

    def test_pull_back_resets_round_counter(self) -> None:
        self.open("旧议题")
        for _ in range(2):
            self.controller.record_turn(AgentRole.BA)
            self.controller.record_turn(AgentRole.UX)
        self.controller.note_deviation(role=AgentRole.BA, reason="聊到食堂去了")
        self.assertEqual(self.controller.current.entity.round_no, 3)
        self.assertEqual(self.controller.current.deviation_count, 1)

        old = self.controller.current
        new = self.controller.pull_back(reason="偏离主题", new_topic="全新议题", actor="human")

        self.assertEqual(old.entity.status, RoundStatus.TERMINATED)
        self.assertEqual(new.entity.status, RoundStatus.ONGOING)
        self.assertEqual(new.entity.round_no, 1)  # 清零
        self.assertEqual(new.deviation_count, 0)  # 清零
        self.assertEqual(new.entity.topic, "全新议题")
        self.assertEqual(len(new.spoken), 0)

    def test_pull_back_emits_events(self) -> None:
        self.open()
        self.controller.pull_back(reason="跑偏", new_topic="新议题")
        types = [event.type for event in self.log.list_events()]
        self.assertIn(EventType.PULL_BACK, types)
        self.assertIn(EventType.ROUND_TERMINATED, types)
        self.assertIn(EventType.ROUND_OPENED, types)

    def test_cannot_open_two_topics_at_once(self) -> None:
        self.open()
        with self.assertRaises(HTTPException):
            self.open("第二个议题")

    def test_open_requires_topic(self) -> None:
        with self.assertRaises(HTTPException):
            self.open("   ")

    def test_invalid_max_rounds(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            RoundController("P", self.log, max_rounds=9)
        self.assertEqual(code_of(ctx.exception), "R403")


if __name__ == "__main__":
    unittest.main()
