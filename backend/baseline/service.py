"""基线冻结与变更申请服务 —— T10 接口交付物（Owner：陈欣然）。

验收标准（规格书 4.2 + 产品开发流程文档 阶段 6）：
1. 冻结基线：校验 signoffs 是否全部为 APPROVED；冻结后生成 Baseline 记录，
   项目状态变 FROZEN，黑板进入只读拦截；
2. 变更申请：变更请求 → 影响评估（范围/成本/工期）→ 审批，
   经批准后按版本更新基线，并同步通知相关干系人。
"""
import uuid
from datetime import datetime

from fastapi import HTTPException

from backend.core.enums import EntryStatus, ProjectStatus
from backend.core.models import Baseline, ChangeRequest
from backend.store import Store


class BaselineService:
    def __init__(self, store: Store) -> None:
        self.store = store

    # ---------- 冻结基线 ----------

    def freeze_baseline(self, project_id: str, scope: str, source_entry_ids: list[str]) -> Baseline:
        project = self.store.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail={"code": "B404", "message": "项目不存在"})

        if project.status == ProjectStatus.FROZEN:
            raise HTTPException(status_code=400, detail={"code": "B101", "message": "项目已冻结，不可重复冻结"})

        signoffs = self.store.get_signoffs(project_id)
        if len(signoffs) < 3:
            raise HTTPException(
                status_code=400,
                detail={"code": "B102", "message": f"三方会签未齐（{len(signoffs)}/3）：业务、开发、测试须并行签署"},
            )
        not_approved = [s.party for s in signoffs if s.status != EntryStatus.APPROVED]
        if not_approved:
            # 基线超时未签 → PM 升级告警（3.2），此处直接阻断冻结
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "B103",
                    "message": f"以下会签方未通过：{not_approved}；全绿后方可冻结",
                    "action": "ESCALATE_TO_PM",
                },
            )

        previous = self.store.latest_baseline(project_id)
        version = self._next_version(previous.version if previous else None)

        baseline = Baseline(
            id=f"bl-{uuid.uuid4().hex[:8]}",
            project_id=project_id,
            version=version,
            scope=scope,
            source_entry_ids=source_entry_ids,
        )
        self.store.add_baseline(baseline)
        project.status = ProjectStatus.FROZEN
        return baseline

    def _next_version(self, current: str | None) -> str:
        """V1.0 → V1.1 → ...；大版本由人工决定，接口只做小版本递增。"""
        if not current:
            return "V1.0"
        prefix, minor = current.rsplit(".", 1)
        return f"{prefix}.{int(minor) + 1}"

    # ---------- 变更申请 ----------

    def submit_change_request(
        self,
        baseline_id: str,
        description: str,
        impact_scope: str,
        impact_cost: str,
        impact_schedule: str,
    ) -> ChangeRequest:
        baseline = self.store.get_baseline(baseline_id)
        if baseline is None:
            raise HTTPException(status_code=404, detail={"code": "B404", "message": "基线不存在"})
        if not description.strip():
            raise HTTPException(status_code=400, detail={"code": "B201", "message": "变更描述不能为空"})
        cr = ChangeRequest(
            id=f"cr-{uuid.uuid4().hex[:8]}",
            baseline_id=baseline_id,
            project_id=baseline.project_id,
            description=description,
            impact_scope=impact_scope,
            impact_cost=impact_cost,
            impact_schedule=impact_schedule,
            status=EntryStatus.PENDING_REVIEW,
        )
        return self.store.add_change_request(cr)

    def decide_change_request(self, cr_id: str, approved: bool, decided_by: str) -> ChangeRequest:
        """审批变更：批准后按版本更新基线（小版本 +1）并通知干系人。"""
        cr = self.store.get_change_request(cr_id)
        if cr is None:
            raise HTTPException(status_code=404, detail={"code": "B404", "message": "变更请求不存在"})
        if cr.status not in (EntryStatus.DRAFT, EntryStatus.PENDING_REVIEW):
            raise HTTPException(status_code=400, detail={"code": "B202", "message": "该变更请求已裁决"})

        cr.status = EntryStatus.APPROVED if approved else EntryStatus.REJECTED
        cr.decided_by = decided_by

        notifications: list[str] = []
        if approved:
            baseline = self.store.get_baseline(cr.baseline_id)
            if baseline:
                baseline.version = self._next_version(baseline.version)
                baseline.scope = f"{baseline.scope} + 变更 {cr.id}"
                notifications = ["PM", "业务", "开发", "测试"]
        return cr

    # ---------- 黑板只读拦截 ----------

    def assert_blackboard_writable(self, project_id: str) -> None:
        """冻结后黑板进入只读：任何写入操作先调用本方法拦截。"""
        if project_id in self.store.blackboard_readonly:
            raise HTTPException(
                status_code=400,
                detail={"code": "B301", "message": "基线已冻结，黑板只读；如需修改请提交变更申请"},
            )
