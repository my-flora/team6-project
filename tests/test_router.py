"""路由层冒烟：能导入、能注册、路径符合联调约定。

真正的 HTTP 行为由第一部分 `backend/tests`（TestClient）覆盖；
这里只保证第二部分的路由模块在合并后不会 import 失败、端点不丢。
"""

from __future__ import annotations

import unittest

from backend.blackboard import router as blackboard_router_module
from backend.orchestrator import router as orchestrator_router_module


class RouterSmokeTest(unittest.TestCase):
    def test_orchestrator_routes_registered(self) -> None:
        paths = {path for _, path, _ in orchestrator_router_module.router.routes}
        expected = {
            "/orchestrator/start",
            "/orchestrator/messages",
            "/orchestrator/rounds/pull-back",
            "/orchestrator/rounds/converge",
            "/orchestrator/rounds/open",
            "/orchestrator/rounds/tick",
            "/orchestrator/stages/advance",
            "/orchestrator/stages/freeze",
            "/orchestrator/project/resume",
            "/orchestrator/state",
            "/orchestrator/events",
        }
        self.assertTrue(expected.issubset(paths), f"缺少路由：{expected - paths}")

    def test_blackboard_routes_registered(self) -> None:
        paths = {path for _, path, _ in blackboard_router_module.router.routes}
        expected = {
            "/blackboard/entries",
            "/blackboard/entries/{entry_id}/submit",
            "/blackboard/entries/{entry_id}/reopen",
            "/blackboard/entries/{entry_id}/conflict",
            "/blackboard/entries/{entry_id}/resolve",
            "/blackboard/gates/{gate_id}/decision",
            "/blackboard/stats",
        }
        self.assertTrue(expected.issubset(paths), f"缺少路由：{expected - paths}")


if __name__ == "__main__":
    unittest.main()
