"""门禁与契约校验服务 —— T3 交付物（Owner：陈欣然）。

验收标准（规格书 2.2）：
1. 实现 AgentMessageRequest 拦截空引用（发言门槛：references 为空直接丢弃并警告）；
2. 实现 StageAdvanceRequest 拦截空人类输入（防人类袖手旁观：返回 400）。

另实现 HumanGateDecision（门禁通过/驳回），驳回必须填 reason（规格书 4.2）。
"""
from fastapi import HTTPException

from backend.core.enums import (
    EntryStatus,
    GateStatus,
    ProjectStatus,
    STAGE_ORDER,
    Stage,
)
from backend.core.models import AgentMessage, BlackboardEntry, HumanGate, Project


class GateService:
    """契约与门禁校验。所有校验失败一律抛 HTTPException(400)，错误码见各方法。"""

    # ---------- AgentMessageRequest 校验 ----------

    def validate_agent_message(
        self,
        msg: AgentMessage,
        referenced_entries: dict[str, BlackboardEntry],
        project: Project,
    ) -> AgentMessage:
        """校验 Agent 发言。任一失败即拒收。

        规则（规格书 1.3 / 3.1）：
        - content 为空 → E001 拒收
        - references 为空 → E002 空引用，直接丢弃并警告（发言门槛）
        - 引用的条目 ID 不存在 → E003 空引用
        - 项目处于 PAUSED/FROZEN → E004 拒收
        """
        if not msg.content or not msg.content.strip():
            raise HTTPException(status_code=400, detail={"code": "E001", "message": "发言内容为空，拒收"})

        if not msg.references:
            # 发言门槛：references 为空的消息直接丢弃并警告
            raise HTTPException(
                status_code=400,
                detail={"code": "E002", "message": "空引用：AgentMessageRequest.references 不能为空，消息已丢弃并告警"},
            )

        missing = [ref for ref in msg.references if ref not in referenced_entries]
        if missing:
            raise HTTPException(
                status_code=400,
                detail={"code": "E003", "message": f"空引用：引用的黑板条目不存在 {missing}"},
            )

        # 状态门槛（幻觉传染防御）：只能引用上游 EntryStatus=APPROVED 的条目
        for ref in msg.references:
            entry = referenced_entries[ref]
            if entry.status != EntryStatus.APPROVED:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "E004",
                        "message": f"引用条目 {ref} 状态为 {entry.status.value}，非 APPROVED，阻断读取",
                        "action": "PROJECT_PAUSED",
                    },
                )

        if project.status != ProjectStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail={"code": "E005", "message": f"项目状态为 {project.status.value}，不接受新发言"},
            )

        return msg

    # ---------- StageAdvanceRequest 校验 ----------

    def validate_stage_advance(
        self,
        project: Project,
        target_stage: Stage,
        human_prompt_input: str,
    ) -> None:
        """校验阶段推进。防『人类袖手旁观』护栏（规格书 3.2）：
        human_prompt_input 为空 → 后端拒绝推进，返回 400。
        """
        if not human_prompt_input or not human_prompt_input.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "E101", "message": "缺少人类确认的 Prompt 输入，拒绝推进到下一阶段"},
            )

        current_idx = STAGE_ORDER.index(project.current_stage)
        target_idx = STAGE_ORDER.index(target_stage) if target_stage in STAGE_ORDER else None
        if target_idx is None or target_idx != current_idx + 1:
            raise HTTPException(
                status_code=400,
                detail={"code": "E102", "message": "只能按顺序推进到下一阶段"},
            )

        if project.status == ProjectStatus.FROZEN:
            raise HTTPException(
                status_code=400,
                detail={"code": "E103", "message": "项目基线已冻结，黑板只读，不可推进"},
            )

    # ---------- HumanGateDecision 门禁裁决 ----------

    def decide_gate(self, gate: HumanGate, decision: GateStatus, reason: str) -> HumanGate:
        """人类门禁通过/驳回（规格书 4.2）：驳回必须填 reason。"""
        if gate.gate_status != GateStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail={"code": "E201", "message": f"门禁已处理（{gate.gate_status.value}），不可重复裁决"},
            )
        if decision == GateStatus.REJECTED and (not reason or not reason.strip()):
            raise HTTPException(
                status_code=400,
                detail={"code": "E202", "message": "驳回必须填写 reason"},
            )
        if decision not in (GateStatus.APPROVED, GateStatus.REJECTED):
            raise HTTPException(
                status_code=400,
                detail={"code": "E203", "message": "裁决只能是 APPROVED 或 REJECTED"},
            )
        gate.gate_status = decision
        gate.reason = reason or None
        return gate
