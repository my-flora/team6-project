"""阶段状态机与阶段元数据。

第一部分已经在 `backend/core/enums.py` 冻结了 `Stage` 与 `STAGE_ORDER`
（IDEA → DISCUSSION → PROPOSAL → EVALUATION → REQUIREMENT → CONFIRMATION），
注意 **没有 FROZEN 这个阶段**：冻结是项目状态 `ProjectStatus.FROZEN`，
`current_stage` 仍停在 CONFIRMATION。本文件严格按这个约定实现，不再自建枚举。

规格书 3.1：阶段状态机与路由规则由 PM 执行；项目/阶段状态只能用 1.2 的唯一枚举。
"""

from __future__ import annotations

from typing import Optional

from backend.core.enums import STAGE_ORDER, ProjectStatus, Stage, StageStatus
from backend.core.models import Project

#: 前端阶段进度条文案（4.1）
STAGE_LABEL: dict[Stage, str] = {
    Stage.IDEA: "阶段1 输入",
    Stage.DISCUSSION: "阶段2 讨论",
    Stage.PROPOSAL: "阶段3 方案",
    Stage.EVALUATION: "阶段4 评审",
    Stage.REQUIREMENT: "阶段5 需求",
    Stage.CONFIRMATION: "阶段6 确认",
}

#: 前端路由用的阶段编号
STAGE_CODE: dict[Stage, str] = {
    Stage.IDEA: "s1",
    Stage.DISCUSSION: "s2",
    Stage.PROPOSAL: "s3",
    Stage.EVALUATION: "s4",
    Stage.REQUIREMENT: "s5",
    Stage.CONFIRMATION: "s6",
}


def stage_index(stage: Stage) -> int:
    return STAGE_ORDER.index(stage)


def next_stage(stage: Stage) -> Optional[Stage]:
    index = stage_index(stage)
    return STAGE_ORDER[index + 1] if index + 1 < len(STAGE_ORDER) else None


def is_upstream(earlier: Stage, later: Stage) -> bool:
    return stage_index(earlier) < stage_index(later)


def stage_label(stage: Stage) -> str:
    return STAGE_LABEL.get(stage, stage.value)


def stage_code(stage: Stage) -> str:
    return STAGE_CODE.get(stage, stage.value.lower())


def stage_progress(project: Project) -> list[dict]:
    """4.1 阶段进度条：高亮当前阶段；已完成的打绿勾；WAITING_HUMAN 变黄。

    `Project` 只保存当前阶段的 StageStatus，因此已完成与否由当前阶段推导：
    当前阶段之前的都视为 COMPLETED，之后的都是 NOT_STARTED。
    """
    current_index = stage_index(project.current_stage)
    items: list[dict] = []
    for index, stage in enumerate(STAGE_ORDER):
        if index < current_index:
            status = StageStatus.COMPLETED
        elif index == current_index:
            status = project.stage_status
            if project.status == ProjectStatus.FROZEN:
                status = StageStatus.COMPLETED
        else:
            status = StageStatus.NOT_STARTED
        items.append(
            {
                "stage": stage.value,
                "code": stage_code(stage),
                "label": stage_label(stage),
                "order": index,
                "status": status.value,
                "is_current": index == current_index and project.status != ProjectStatus.FROZEN,
            }
        )
    return items


class StageMachine:
    """薄封装：所有状态都写回 T1 的 `Project` 实体，不另存一份。"""

    def __init__(self, project: Project) -> None:
        self.project = project

    # ---------------------------------------------------------------- 读
    @property
    def current(self) -> Stage:
        return self.project.current_stage

    @property
    def stage_status(self) -> StageStatus:
        return self.project.stage_status

    @property
    def project_status(self) -> ProjectStatus:
        return self.project.status

    def is_running(self) -> bool:
        return self.project.status == ProjectStatus.RUNNING

    # ---------------------------------------------------------------- 写
    def start(self) -> None:
        """进入当前阶段（通常是 IDEA）。"""
        self.project.stage_status = StageStatus.IN_PROGRESS

    def complete_current(self) -> None:
        self.project.stage_status = StageStatus.COMPLETED

    def advance_to(self, target: Stage) -> None:
        """推进到下一阶段；调用方负责先做完所有校验。"""
        self.project.current_stage = target
        self.project.stage_status = StageStatus.IN_PROGRESS
        if self.project.status == ProjectStatus.PAUSED:
            self.project.status = ProjectStatus.RUNNING

    def mark_rejected(self) -> None:
        """评审驳回（3.2 评审驳回分支，T7.5 调用）。"""
        self.project.stage_status = StageStatus.REJECTED

    def set_waiting_human(self) -> None:
        """有门禁未处理 → 阶段变黄（4.1）。"""
        if self.project.status == ProjectStatus.FROZEN:
            return
        self.project.stage_status = StageStatus.WAITING_HUMAN

    def clear_waiting_human(self) -> None:
        if self.project.stage_status == StageStatus.WAITING_HUMAN:
            self.project.stage_status = StageStatus.IN_PROGRESS

    def pause(self) -> None:
        """3.2 幻觉传染 / 红蓝死锁：项目挂起，等待人类介入。"""
        if self.project.status == ProjectStatus.FROZEN:
            return
        self.project.status = ProjectStatus.PAUSED

    def resume(self) -> None:
        if self.project.status == ProjectStatus.PAUSED:
            self.project.status = ProjectStatus.RUNNING

    def freeze(self) -> None:
        """4.2 冻结基线：项目 FROZEN，当前阶段保持 CONFIRMATION 并置 COMPLETED。"""
        self.project.stage_status = StageStatus.COMPLETED
        self.project.status = ProjectStatus.FROZEN

    # ---------------------------------------------------------------- 导出
    def to_dict(self) -> dict:
        return {
            "current_stage": self.project.current_stage.value,
            "current_stage_label": stage_label(self.project.current_stage),
            "current_stage_code": stage_code(self.project.current_stage),
            "stage_status": self.project.stage_status.value,
            "project_status": self.project.status.value,
            "stages": stage_progress(self.project),
        }
