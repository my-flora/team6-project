# /contracts —— 接口与 Agent 消息契约（Owner：陈欣然 · 角色1）

本目录是系统唯一契约源（Single Source of Truth），V1.0 已冻结。
所有服务（backend/orchestrator、blackboard、gate、baseline）与前端 `frontend/src/api` 均以本目录为准，修改须经 ADR 评审。

## 唯一状态枚举（全局统一标准）

| 枚举 | 取值 |
|---|---|
| ProjectStatus | RUNNING / PAUSED / FROZEN |
| StageStatus | NOT_STARTED / IN_PROGRESS / WAITING_HUMAN / COMPLETED / REJECTED |
| EntryStatus | DRAFT / PENDING_REVIEW / APPROVED / REJECTED |
| GateStatus | PENDING / APPROVED / REJECTED / DECIDED |
| RoundStatus | ONGOING / CONVERGED / TERMINATED |
| AgentRole | PM / BA / UX / TECH / ARCH / RED_TEAM / FORMATTER |

## 契约文件

| 文件 | 用途 | 关键硬校验 |
|---|---|---|
| `agent-message.schema.json` | AgentMessageRequest：Agent 发言输入 | 缺任一必填字段拒收；`references` 为空 → 直接丢弃并警告（发言门槛） |
| `stage-advance.schema.json` | StageAdvanceRequest：阶段推进 | `human_prompt_input` 为空 → 拒绝推进，返回 400（防人类袖手旁观） |

## 阶段流转顺序

Idea → Discussion → Proposal → Evaluation → Requirement → Confirmation → Frozen

## 依赖顺序

T1（本契约/数据模型）→ T2（黑板 API）、T3（门禁校验）、T4（编排引擎）→ T5~T9（各阶段）→ T10（冻结/变更）→ T11（联调）
