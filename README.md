# 第6组 · 虚拟项目室 —— 角色1（陈欣然）交付目录

角色：① 契约与门槛（组长）
负责任务：T1 数据模型与状态枚举 · T3 门禁与契约校验 · T10 基线冻结与变更申请接口 · 冻结 `/frontend/src/api` · 主拆 T11 联调
负责目录：`/contracts`、`/docs/adr`、`/backend/core`、`/backend/gate`、`/backend/baseline`、`/frontend/src/api`

## 目录结构

```
contracts/               唯一契约源（V1.0 冻结）：JSON Schema + 枚举说明
docs/adr/                关键决策记录（技术栈、校验规则、基线规则）
backend/core/            T1：6 个唯一状态枚举 + 核心实体（Pydantic）
backend/gate/            T3：门禁与契约校验服务（空引用拦截 E002 / 空人类输入拦截 E101）
backend/baseline/        T10：基线冻结（三方会签全绿）与变更申请（影响评估→审批→版本+1）
backend/store.py         进程内共享存储（联调最小依赖，持久化归 T2）
backend/app.py           FastAPI 应用入口
backend/tests/           验收自测（pytest，供 T11 联调基线）
frontend/src/api/        冻结版前端 API Client（TS，错误码与后端一致）
```

## 运行与自测

```powershell
pip install -r requirements.txt
pytest backend/tests -v          # 验收标准自测
uvicorn backend.app:app --reload --port 8000
# 打开 http://localhost:8000/docs 查看 OpenAPI
```

## 验收标准对照（规格书 2.2）

| 任务 | 验收标准 | 覆盖测试 |
|---|---|---|
| T1 | 唯一状态枚举字典生成；实体表/结构建立完毕 | `backend/core/enums.py`、`models.py` |
| T3 | AgentMessageRequest 拦截空引用 | `test_agent_message_rejects_empty_references` |
| T3 | StageAdvanceRequest 拦截空人类输入 | `test_stage_advance_rejects_empty_human_input` |
| T10 | 校验 signoffs 全部 APPROVED 后冻结、黑板只读 | `test_freeze_requires_all_signoffs_approved`、`test_freeze_success_and_blackboard_readonly` |
| T10 | 变更申请 → 审批 → 版本更新 | `test_change_request_updates_version` |

## 错误码（契约的一部分，见 ADR-002）

E002 空引用 · E004 引用未 APPROVED（幻觉传染）· E101 空人类输入（袖手旁观）· E202 驳回未填理由 · E204 拍板未填理由 · B301 黑板只读 · B405 不可一人代签

## 会签与拍板接口（ADR-004 增补）

- `POST /baseline/signoffs/init` 初始化三方会签单（business/development/testing）
- `POST /baseline/signoffs` 签署（同一签署人只能签一个方位，B405 拦截代签）
- `POST /gate/decision` 支持 `decision: "DECIDED"`（人类拍板，reason 必填）
- `AgentRole` 新增 `HUMAN`（人类直接产出条目的 source_agent，见 ADR-004）

## 与其他角色的依赖（六人分工）

- ① 陈欣然（契约与门禁 · 组长）：已交付本目录全部内容（T1 / T3 / T10 / 冻结 api client / 脚手架）
- ② 张嘉辉（编排与调度）：T4 轮次控制、时间盒、强制收敛、拉回清零；T2 黑板服务与状态强约束 → `/backend/orchestrator`、`/backend/blackboard`、`/backend/log`、`/agents/roles/pm`。注意：黑板写入需集成 `assert_blackboard_writable`；编排引擎复用 `GateService.validate_agent_message` 做发言门槛
- ③ 范云娜（发散域 · 阶段1-3）：T5 结构化输入、T6 多体讨论与去重、T7 方案生成与裁剪 → `/backend/stages/{1-input,2-discussion,3-proposal}`、`/agents/roles/{business,ux,tech-critic,architect}`
- ④ 张吴博（博弈域 · 阶段4-6）：T7.5 红蓝对抗评分、T8 PRD 生成、T9 会签与冻结联动 → `/backend/stages/{4-review,5-prd,6-signoff}`、`/agents/roles/{red-team,formatter}`
- ⑤ 徐欣雨（前端 · 展示侧）：阶段进度条、黑板四色状态、轮次提示、Agent 状态灯、时间盒倒计时、PRD 阅读页 → `/frontend/src/views/{dashboard,blackboard,s2-discussion,s3-proposal,s5-prd}`、`/components/display`
- ⑥ 江艳菲（前端 · 交互侧）：门禁面板（红点/驳回弹窗）、阶段1输入表单、评审页、会签页、变更申请页及全部人类介入控件 → `/frontend/src/views/{gate,s1-input,s4-review,s6-signoff}`、`/components/human-actions`

前端两位（徐欣雨 / 江艳菲）统一从 `frontend/src/api` 导入 apiClient，不得自行 fetch；错误码含义见 `docs/adr/ADR-002`。
T11 联调由陈欣然主持，全员参加，以 `backend/tests` 为异常分支基线。
