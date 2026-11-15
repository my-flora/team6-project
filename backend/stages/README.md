# 角色③ 发散域阶段服务

本目录实现范云娜负责的 T5–T7，复用第一、二部分的 `BlackboardService`、全局状态枚举、`BaseAgent` 和 `Orchestrator`，不另造状态枚举或黑板状态机。

## 交付点

- `1-input/service.py`：T5 五项必填字段（核心目标、目标受众、期望边界、成功判据、价值主张）及待补充风险登记区。风险条目包含类型、严重度、触发条件、来源、是否需人类裁决。提交后走 T2 `DRAFT → PENDING_REVIEW`，自动生成门禁。
- `2-discussion/service.py`：T6 复用 R1 当前议题和轮次，按 BA→UX→TECH→ARCH（R2→R3→R4→R5）顺序调用角色并通过 T4 接收发言；每条发言必须引用阶段1已批准卡片。重复观点合并，保留首次来源和重复来源；冲突关系保留双方方案并调用 T2 冲突标记；观点与风险清单写入黑板并各自进入门禁。
- `3-proposal/service.py` 与 `agents/roles/architect/agent.py`：T7 基于已批准的输入和讨论结果生成七章完整草案。候选观点/冲突方案可逐项保留或剔除；剔除必须有理由，操作者、时间、理由及裁剪前快照写入 `trim_archive`。
- `agents/roles/{business,ux,tech_critic,architect}/agent.py`：R2–R5 的确定性角色 Agent，不连接外部模型，便于课堂重复演示；可后续替换为模型实现。
- `router.py`：将以上能力挂接到 FastAPI 应用，使用现有黑板及编排单例。

## HTTP 接口

1. `POST /stages/1-input`：提交 T5 输入并返回黑板条目与门禁 ID。
2. 经门禁批准并按流程推进到 DISCUSSION、由 R1 打开议题后，调用 `POST /stages/2-discussion/run-round`。每次执行当前轮未发言的 R2–R5，并通过 T4 写事件。最多五轮由 T4 控制。
3. 讨论观点与风险条目经门禁批准后，`POST /stages/3-proposal/generate`，body 提供已批准的阶段1、阶段2条目 ID 列表，生成 DRAFT 方案。
4. 对方案 `trim_items` 调用 `POST /stages/3-proposal/{entry_id}/trim`；`action=exclude` 时 `reason` 必填。裁剪完成后调用 `/stages/3-proposal/{entry_id}/submit` 进入门禁。

T6 发言门槛、时间盒、轮次上限、收敛由现有 R1/T4 和 T3 `GateService` 执行；本代码不重复实现。
