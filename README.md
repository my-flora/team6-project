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

E002 空引用 · E004 引用未 APPROVED（幻觉传染）· E101 空人类输入（袖手旁观）· E202 驳回未填理由 · B301 黑板只读

## 与其他角色的依赖

- T2（张嘉辉）：黑板服务写入接口需集成 `assert_blackboard_writable`
- T4（张嘉辉）：编排引擎复用 `GateService.validate_agent_message` 做发言门槛
- T5~T9（范云娜 / 张昊博）：前端视图统一从 `frontend/src/api` 导入 apiClient
- T11（全员）：以 `backend/tests` 为异常分支联调基线
