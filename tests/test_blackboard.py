"""T2 黑板服务：状态强约束、门禁联动、状态门槛、冻结只读。"""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from backend.blackboard import BlackboardService
from backend.core.enums import AgentRole, EntryStatus, GateStatus, Stage
from backend.store import Store


def code_of(exc: HTTPException) -> str:
    return (exc.detail or {}).get("code", "") if isinstance(exc.detail, dict) else ""


class BlackboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store()
        self.project = self.store.create_project("测试项目")
        self.pid = self.project.id
        self.board = BlackboardService(self.store)

    def create(self, *, stage: Stage = Stage.IDEA, content: str = "痛点：找书难、卖书慢"):
        return self.board.create_entry(
            self.pid,
            stage=stage,
            source_agent=AgentRole.BA,
            content=content,
            actor="BA",
        )

    def approve(self, entry):
        entry, gate = self.board.submit_for_review(entry.id, actor="BA")
        self.board.decide_gate(gate.id, GateStatus.APPROVED, actor="human")
        return entry

    # ------------------------------------------------------------ 创建
    def test_created_entry_is_draft(self) -> None:
        entry = self.create()
        self.assertEqual(entry.status, EntryStatus.DRAFT)
        self.assertEqual(entry.project_id, self.pid)
        self.assertEqual(len(self.board.history(entry.id)), 1)

    def test_cannot_write_other_stage(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.create(stage=Stage.DISCUSSION)
        self.assertEqual(code_of(ctx.exception), "E305")

    def test_empty_content_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.create(content="   ")
        self.assertEqual(code_of(ctx.exception), "E306")

    # ------------------------------------------------------------ 提交约束
    def test_submit_creates_gate_and_marks_pending(self) -> None:
        """提交审核 = DRAFT→PENDING_REVIEW 且生成人类门禁（4.1 红点数据源）。"""
        entry = self.create()
        entry, gate = self.board.submit_for_review(entry.id, actor="BA")
        self.assertEqual(entry.status, EntryStatus.PENDING_REVIEW)
        self.assertEqual(gate.gate_status, GateStatus.PENDING)
        self.assertEqual(self.store.pending_gate_count(self.pid), 1)

    def test_cannot_submit_twice(self) -> None:
        entry = self.create()
        self.board.submit_for_review(entry.id, actor="BA")
        with self.assertRaises(HTTPException) as ctx:
            self.board.submit_for_review(entry.id, actor="BA")
        self.assertEqual(code_of(ctx.exception), "E301")

    def test_cannot_edit_after_submit(self) -> None:
        entry = self.create()
        self.board.submit_for_review(entry.id, actor="BA")
        with self.assertRaises(HTTPException) as ctx:
            self.board.update_content(entry.id, "改一改", actor="BA")
        self.assertEqual(code_of(ctx.exception), "E303")

    # ------------------------------------------------------------ 裁决
    def test_approve(self) -> None:
        entry = self.create()
        entry, gate = self.board.submit_for_review(entry.id, actor="BA")
        gate, entry = self.board.decide_gate(gate.id, GateStatus.APPROVED, actor="human")
        self.assertEqual(entry.status, EntryStatus.APPROVED)
        self.assertEqual(gate.gate_status, GateStatus.APPROVED)
        self.assertEqual(self.store.pending_gate_count(self.pid), 0)

    def test_reject_requires_reason(self) -> None:
        entry = self.create()
        entry, gate = self.board.submit_for_review(entry.id, actor="BA")
        with self.assertRaises(HTTPException) as ctx:
            self.board.decide_gate(gate.id, GateStatus.REJECTED, reason="  ")
        self.assertEqual(code_of(ctx.exception), "E202")

    def test_reject_then_reopen(self) -> None:
        entry = self.create()
        entry, gate = self.board.submit_for_review(entry.id, actor="BA")
        self.board.decide_gate(gate.id, GateStatus.REJECTED, reason="缺少目标用户", actor="human")
        self.assertEqual(entry.status, EntryStatus.REJECTED)

        reopened = self.board.reopen(entry.id, reason="已补充", actor="BA")
        self.assertEqual(reopened.status, EntryStatus.DRAFT)

    def test_reopen_only_from_rejected(self) -> None:
        entry = self.create()
        with self.assertRaises(HTTPException) as ctx:
            self.board.reopen(entry.id, actor="BA")
        self.assertEqual(code_of(ctx.exception), "E301")

    # ------------------------------------------------------------ 状态门槛
    def test_downstream_reads_only_approved(self) -> None:
        approved = self.approve(self.create(content="已通过的输入卡片"))
        self.create(content="未走门禁的草稿")

        self.project.current_stage = Stage.DISCUSSION
        visible = self.board.readable_entries(self.pid, Stage.IDEA)
        self.assertEqual([entry.id for entry in visible], [approved.id])

    def test_cannot_read_downstream_stage(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.board.readable_entries(self.pid, Stage.PROPOSAL)
        self.assertEqual(code_of(ctx.exception), "E304")

    # ------------------------------------------------------------ 冻结
    def test_frozen_board_rejects_writes(self) -> None:
        self.store.blackboard_readonly.add(self.pid)  # 模拟 T10 冻结
        with self.assertRaises(HTTPException) as ctx:
            self.create()
        self.assertEqual(code_of(ctx.exception), "B301")

    def test_frozen_board_still_readable(self) -> None:
        entry = self.create()
        self.store.blackboard_readonly.add(self.pid)
        self.assertEqual(self.board.get_entry(entry.id).id, entry.id)

    # ------------------------------------------------------------ 其他
    def test_delete_only_draft(self) -> None:
        entry = self.create()
        self.board.submit_for_review(entry.id, actor="BA")
        with self.assertRaises(HTTPException) as ctx:
            self.board.delete_entry(entry.id, actor="BA")
        self.assertEqual(code_of(ctx.exception), "E301")

    def test_conflict_mark_and_resolve(self) -> None:
        entry = self.create()
        self.board.mark_conflict(entry.id, "BA 与 TECH 对范围有分歧")
        self.assertTrue(entry.is_conflict)
        self.assertEqual(self.board.conflict_note(entry.id), "BA 与 TECH 对范围有分歧")
        self.board.resolve_conflict(entry.id, "先做 MVP")
        self.assertFalse(entry.is_conflict)
        self.assertEqual(self.board.stats(self.pid)["conflicts"], 0)

    def test_stats(self) -> None:
        self.approve(self.create(content="通过一条"))
        self.create(content="草稿一条")
        stats = self.board.stats(self.pid)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["by_status"]["APPROVED"], 1)
        self.assertEqual(stats["by_status"]["DRAFT"], 1)
        self.assertFalse(stats["readonly"])


if __name__ == "__main__":
    unittest.main()
