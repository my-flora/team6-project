"""发言事件流：序号单调、增量拉取、订阅、JSONL 导出。"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.core.enums import AgentRole, Stage
from backend.log import EventLog, EventType
from tests.support import FakeClock


class EventLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.log = EventLog("PRJ-LOG", clock=self.clock)

    def append(self, seq_hint: str = "x") -> None:
        self.log.append(
            EventType.MESSAGE_ACCEPTED,
            actor="BA",
            role=AgentRole.BA,
            stage=Stage.IDEA,
            round_no=1,
            payload={"content": seq_hint},
        )

    def test_seq_is_monotonic_from_one(self) -> None:
        for index in range(3):
            self.append(str(index))
        events = self.log.list_events()
        self.assertEqual([event.seq for event in events], [1, 2, 3])
        self.assertEqual(self.log.last_seq, 3)

    def test_incremental_fetch(self) -> None:
        for index in range(5):
            self.append(str(index))
        events = self.log.list_events(after_seq=3)
        self.assertEqual([event.seq for event in events], [4, 5])

    def test_filter_by_role_and_round(self) -> None:
        self.append("BA 的发言")
        self.log.append(
            EventType.MESSAGE_ACCEPTED,
            actor="UX",
            role=AgentRole.UX,
            stage=Stage.IDEA,
            round_no=2,
            payload={"content": "UX 的发言"},
        )
        only_ux = self.log.list_events(role=AgentRole.UX)
        self.assertEqual(len(only_ux), 1)
        self.assertEqual(only_ux[0].round_no, 2)

        round_one = self.log.messages_of_round(1)
        self.assertEqual(len(round_one), 1)

    def test_subscribe_receives_events(self) -> None:
        received = []
        unsubscribe = self.log.subscribe(received.append)
        self.append("第一条")
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].seq, 1)
        unsubscribe()
        self.append("第二条")
        self.assertEqual(len(received), 1)

    def test_subscriber_error_does_not_break_log(self) -> None:
        def boom(event):  # noqa: ANN001
            raise RuntimeError("订阅方炸了")

        self.log.subscribe(boom)
        self.append("仍然要写入")
        self.assertEqual(self.log.last_seq, 1)

    def test_last_event_of_role(self) -> None:
        self.append("BA 第一条")
        self.clock.advance(seconds=5)
        latest = self.log.last_event_of_role()
        self.assertIn(AgentRole.BA.value, latest)

    def test_export_jsonl(self) -> None:
        self.append("导出用")
        target = Path(__file__).resolve().parent / "_artifacts" / "events.jsonl"
        try:
            self.log.export_jsonl(target)
            lines = target.read_text(encoding="utf-8").strip().splitlines()
        finally:
            if target.exists():
                target.unlink()
        self.assertEqual(len(lines), 1)
        self.assertIn("message.accepted", lines[0])


if __name__ == "__main__":
    unittest.main()
