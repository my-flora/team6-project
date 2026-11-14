"""第二部分（T2 / T4）错误码。

沿用第一部分 ADR-002 的约定：所有校验失败抛 `fastapi.HTTPException`，
`detail` 为 `{"code": ..., "message": ...}`，必要时带 `action`，
前端 `ApiRequestError` 直接消费同一个结构。

错误码分段（建议登记为 ADR-004）：
    E3xx  黑板条目状态机（T2）
    E104 / E105  推进阶段被门禁或待审条目拦截
    R4xx  议题轮次与时间盒（T4）

复用的第一部分错误码：
    E001-E005  AgentMessage 契约校验（GateService）
    E101-E103  StageAdvance 校验（GateService）
    E202       门禁驳回未填理由（GateService）
    B301       基线冻结、黑板只读（BaselineService）
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    """带业务码的 HTTPException。子类只需声明 `code` 与 `default_status`。"""

    code: str = "E999"
    default_status: int = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        action: str | None = None,
        status_code: int | None = None,
        **extra: Any,
    ) -> None:
        detail: dict[str, Any] = {"code": code or self.code, "message": message}
        if action:
            detail["action"] = action
        detail.update(extra)
        super().__init__(status_code=status_code or self.default_status, detail=detail)


# ---------------------------------------------------------------- 黑板 E3xx
class ProjectNotFound(ApiError):
    """项目不存在（与第一部分 gate 的 E404 保持一致）。"""

    code = "E404"
    default_status = 404


class EntryNotFound(ApiError):
    """条目不存在。"""

    code = "E302"
    default_status = 404


class IllegalEntryTransition(ApiError):
    """非法流转，例如 DRAFT 直接跳 APPROVED、重复提交、对已裁决条目再裁决。"""

    code = "E301"


class EntryNotEditable(ApiError):
    """只有 DRAFT 可以修改/删除；已进入门禁流程的条目必须先驳回再重开。"""

    code = "E303"


class DownstreamReadForbidden(ApiError):
    """状态门槛：不允许提前读取下游阶段的黑板内容。"""

    code = "E304"
    default_status = 403


class EntryOutsideCurrentStage(ApiError):
    """只能向当前阶段写黑板，避免把下游产物提前塞进上游阶段。"""

    code = "E305"


class EmptyEntryContent(ApiError):
    """条目内容为空。"""

    code = "E306"


class PendingEntryBlocksAdvance(ApiError):
    """当前阶段仍有 PENDING_REVIEW 条目，不允许推进（4.2 推进按钮置灰）。"""

    code = "E105"


class GatePendingBlocksAdvance(ApiError):
    """门禁待办未清零，不允许推进（4.1 门禁红点拦截）。"""

    code = "E104"


# ---------------------------------------------------------------- 轮次 R4xx
class RoundNotOpen(ApiError):
    """当前项目没有进行中的议题：未开题、已收敛或已终止。"""

    code = "R401"


class InvalidRoundOperation(ApiError):
    """轮次/拉回参数不合法（缺少理由、缺少新议题）。"""

    code = "R402"


class StageMismatch(ApiError):
    """Agent 发言所属阶段与项目当前阶段不一致（旧阶段的消息不应再被接纳）。"""

    code = "E107"


class InvalidRoundConfig(ApiError):
    """轮次配置不合法（max_rounds / timebox_seconds 越界）。"""

    code = "R403"


class TopicDeviation(ApiError):
    """连续偏离议题，触发「拉回清零」（3.2 无限发散防御）。"""

    code = "R404"
