"""唯一状态枚举（全局统一标准）—— T1 交付物。

来源：《第6组-虚拟项目室设计规格书》1.2 节。
全系统（后端各服务、前端、Agent）只允许使用本文件定义的枚举取值，
任何新增状态必须走 ADR 变更流程。
"""
from enum import Enum


class ProjectStatus(str, Enum):
    """项目状态"""
    RUNNING = "RUNNING"        # 进行中
    PAUSED = "PAUSED"          # 暂停/需人类介入
    FROZEN = "FROZEN"          # 已冻结基线


class StageStatus(str, Enum):
    """阶段状态"""
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_HUMAN = "WAITING_HUMAN"  # 有门禁未处理
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"            # 被打回


class EntryStatus(str, Enum):
    """黑板条目状态"""
    DRAFT = "DRAFT"                    # 草稿
    PENDING_REVIEW = "PENDING_REVIEW"  # 待审
    APPROVED = "APPROVED"              # 已通过
    REJECTED = "REJECTED"              # 已驳回


class GateStatus(str, Enum):
    """门禁状态"""
    PENDING = "PENDING"      # 待处理
    APPROVED = "APPROVED"    # 通过
    REJECTED = "REJECTED"    # 驳回
    DECIDED = "DECIDED"      # 已拍板


class RoundStatus(str, Enum):
    """议题轮次状态"""
    ONGOING = "ONGOING"            # 进行中
    CONVERGED = "CONVERGED"        # 已收敛
    TERMINATED = "TERMINATED"      # 强制终止


class AgentRole(str, Enum):
    """Agent 角色"""
    PM = "PM"
    BA = "BA"            # 商业
    UX = "UX"            # 体验
    TECH = "TECH"        # 技术
    ARCH = "ARCH"        # 架构
    RED_TEAM = "RED_TEAM"      # 评价
    FORMATTER = "FORMATTER"    # 格式化


class Stage(str, Enum):
    """六阶段（状态机流转：Idea → ... → Frozen）"""
    IDEA = "IDEA"
    DISCUSSION = "DISCUSSION"
    PROPOSAL = "PROPOSAL"
    EVALUATION = "EVALUATION"
    REQUIREMENT = "REQUIREMENT"
    CONFIRMATION = "CONFIRMATION"


# 阶段推进的合法顺序（用于 StageAdvanceRequest 校验）
STAGE_ORDER: list[Stage] = [
    Stage.IDEA,
    Stage.DISCUSSION,
    Stage.PROPOSAL,
    Stage.EVALUATION,
    Stage.REQUIREMENT,
    Stage.CONFIRMATION,
]

# 单议题最大轮次（防无限发散护栏）
MAX_ROUNDS = 5
