"""第二部分可执行演示：把规格书里的每条护栏跑一遍（不依赖 FastAPI 服务）。

用法：  python demo.py

演示内容与规格书章节一一对应：
    [1] 开题                          —— 3.1 阶段状态机入口
    [2] 黑板状态强约束                —— T2 / 2.2 验收标准
    [3] 发言门槛 + 轮次推进 + 收敛    —— 3.1 发言门槛 / 轮次控制
    [4] 袖手旁观防御                  —— 3.2
    [5] 幻觉传染防御 → PAUSED         —— 3.2
    [6] 人类拉回清零                  —— T4 / 4.2
    [7] 时间盒到期 → 强制收敛         —— T4
    [8] 发言事件流回放                —— 4.1 Agent 状态灯数据源
"""

from __future__ import annotations

import sys
import time
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import _bootstrap

SOURCE = _bootstrap.prepare()

from fastapi import HTTPException  # noqa: E402

from backend.core.enums import AgentRole, GateStatus, Stage  # noqa: E402
from backend.core.models import AgentMessage  # noqa: E402
from backend.orchestrator import Orchestrator  # noqa: E402
from backend.store import Store  # noqa: E402


def title(text: str) -> None:
    print("\n" + "=" * 74)
    print(f"  {text}")
    print("=" * 74)


def step(text: str) -> None:
    print(f"  · {text}")


def show(label: str, value: object) -> None:
    print(f"    {label}: {value}")


def error_code(exc: HTTPException) -> str:
    return (exc.detail or {}).get("code", "?") if isinstance(exc.detail, dict) else "?"


def main() -> None:
    store = Store()
    orch = Orchestrator(store, max_rounds=5, timebox_seconds=300)
    project = store.create_project("校园二手书交易小程序")
    pid = project.id

    # ------------------------------------------------------------------ 1
    title("[1] 开题：进入阶段1 输入，PM 打开第一个议题")
    snapshot = orch.start(pid, "校园二手书交易小程序")
    show("当前阶段", snapshot["project"]["current_stage_label"])
    show("议题/轮次", snapshot["round"]["progress_label"])
    show("发言序", " → ".join(snapshot["pm"]["agenda"]))

    # ------------------------------------------------------------------ 2
    title("[2] 黑板 T2：DRAFT → PENDING_REVIEW → APPROVED 的强约束")
    board = orch.board
    card = board.create_entry(
        pid,
        stage=Stage.IDEA,
        source_agent=AgentRole.BA,
        content="痛点：二手书信息分散在班级群，找不到、卖不掉；目标用户：本校本科生。",
        actor="BA",
    )
    show("新建条目", f"{card.id} / {card.status.value}")

    try:
        board.decide_gate("g-not-exist", GateStatus.APPROVED)
    except HTTPException as exc:
        step(f"对不存在的门禁裁决 → 被拦截：{error_code(exc)}")

    card, gate = board.submit_for_review(card.id, actor="BA")
    show("提交审核后", f"{card.status.value}，生成门禁 {gate.id}")

    try:
        board.decide_gate(gate.id, GateStatus.REJECTED, reason="")
    except HTTPException as exc:
        step(f"驳回不写理由 → 被拦截：{error_code(exc)}（驳回必须填 reason）")

    board.decide_gate(gate.id, GateStatus.APPROVED, actor="human")
    show("门禁通过后", card.status.value)

    # 再留一张"没走完门禁"的草稿卡，供 [5] 演示幻觉传染防御
    draft = board.create_entry(
        pid,
        stage=Stage.IDEA,
        source_agent=AgentRole.BA,
        content="草稿：还没走门禁的输入卡片。",
        actor="BA",
    )
    show("另建草稿（不提交）", f"{draft.id} / {draft.status.value}")

    # ------------------------------------------------------------------ 3
    title("[3] 发言门槛 + 轮次推进：references 为空直接丢弃")
    try:
        orch.submit_message(
            AgentMessage(
                id="m-bad",
                project_id=pid,
                stage=Stage.IDEA,
                agent_role=AgentRole.BA,
                content="我觉得可以做一个 App。",
                references=[],
            )
        )
    except HTTPException as exc:
        step(f"空引用被拒收：{error_code(exc)}（发言门槛：references 为空即丢弃）")

    for round_index in range(3):
        for role, text in (
            (AgentRole.BA, f"第{round_index + 1}轮：目标是本校学生，核心诉求是「找得到、卖得掉」。"),
            (AgentRole.UX, f"第{round_index + 1}轮：动线应该是 搜索 → 详情 → 私信，先不做支付。"),
        ):
            result = orch.submit_message(
                AgentMessage(
                    id=f"m-{role.value}-{round_index}",
                    project_id=pid,
                    stage=Stage.IDEA,
                    agent_role=role,
                    content=text,
                    references=[card.id],
                )
            )
        show(
            f"第 {result['round_no']} 轮",
            f"{result['progress']['spoken_count']}/{result['progress']['expected_count']} 人已发言",
        )

    summary = orch.force_converge(pid, reason="人类确认要点已齐全")["summary"]
    show("收敛总结", summary["text"])

    # ------------------------------------------------------------------ 4
    title("[4] 袖手旁观防御：人类必须输入 Prompt 才能推进阶段")
    try:
        orch.advance_stage(pid, Stage.DISCUSSION, "   ")
    except HTTPException as exc:
        step(f"空 Prompt 推进 → 被拦截：{error_code(exc)}（袖手旁观防御）")

    result = orch.advance_stage(pid, Stage.DISCUSSION, "确认进入讨论阶段，聚焦 MVP 范围")
    show("推进结果", f"{result['from']} → {result['to']}")

    # ------------------------------------------------------------------ 5
    title("[5] 幻觉传染防御：引用未通过门禁的上游条目 → 阻断 + PAUSED")
    try:
        orch.submit_message(
            AgentMessage(
                id="m-hallucination",
                project_id=pid,
                stage=Stage.DISCUSSION,
                agent_role=AgentRole.BA,
                content="顺着草稿卡片继续讨论……",
                references=[draft.id],
            )
        )
    except HTTPException as exc:
        show("拦截异常", f"{error_code(exc)}（幻觉传染防御）")
        show("项目状态", project.status.value)

    # ------------------------------------------------------------------ 6
    title("[6] 人类拉回清零：终止当前议题 → 轮次与偏离计数归零")
    pulled = orch.pull_back(
        pid,
        reason="讨论跑偏到支付方案，拉回 MVP 范围",
        new_topic="只讨论搜索与私信两个核心动线",
    )
    round_info = pulled["round"]
    show("新议题", round_info["topic"])
    show("轮次", f"[{round_info['round_no']}]/[{round_info['max_rounds']}]")
    show("偏离计数", round_info["deviation_count"])
    show("项目状态", project.status.value)

    # ------------------------------------------------------------------ 7
    title("[7] 时间盒到期：自动强制收敛并输出总结")
    orch.force_converge(pid, reason="演示用：先收敛当前议题")
    orch.open_topic(pid, "时间盒演示议题", timebox_seconds=1)
    show("倒计时（秒）", orch.snapshot(pid)["round"]["remaining_seconds"])
    time.sleep(1.1)
    ticked = orch.tick(pid)
    show("tick 结果", "已收敛" if ticked and ticked.get("converged") else "未收敛")
    if ticked:
        show("收敛原因", ticked["summary"]["reason"])

    # ------------------------------------------------------------------ 8
    title("[8] 发言事件流回放（前端 Agent 状态灯 / 讨论区的数据源）")
    events = orch.events(pid, after_seq=0, limit=200)["items"]
    for event in events[:14]:
        role = event["role"] or "-"
        clock_text = datetime.fromisoformat(event["ts"]).astimezone().strftime("%H:%M:%S")
        print(f"    #{event['seq']:>2} {event['type']:<22} {role:<9} {clock_text}")
    print(f"    … 共 {len(events)} 条事件")
    print(f"    事件流末序号：{orch.events(pid)['last_seq']}")

    title("快照（4.1 信号-字段映射的落地）")
    snapshot = orch.snapshot(pid)
    show("项目状态", snapshot["project"]["project_status"])
    show("当前阶段", snapshot["project"]["current_stage_label"])
    show("门禁红点", snapshot["gates"]["red_dot"])
    show("黑板统计", snapshot["board"]["by_status"])
    show("Agent 状态灯", {item["role"]: item["state"] for item in snapshot["agents"]})

    print("\n演示结束：全部护栏均可复现。\n")


if __name__ == "__main__":
    main()
