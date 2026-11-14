"""backend.core —— 数据模型与唯一状态枚举（T1，Owner：陈欣然）。

此包被 T2 黑板服务、T3 门禁校验、T4 编排引擎依赖，
修改枚举或实体字段前必须先在 /docs/adr 提交决策记录。
"""
from .enums import (  # noqa: F401
    AgentRole,
    EntryStatus,
    GateStatus,
    ProjectStatus,
    RoundStatus,
    Stage,
    StageStatus,
    STAGE_ORDER,
    MAX_ROUNDS,
)
from .models import (  # noqa: F401
    AgentMessage,
    Baseline,
    BlackboardEntry,
    ChangeRequest,
    DiscussionRound,
    HumanGate,
    Project,
    Signoff,
)
