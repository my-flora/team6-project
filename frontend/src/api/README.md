# /frontend/src/api —— 冻结版前端 API Client（Owner：陈欣然）

版本：V1.0（2026-11 冻结）。与 `/contracts` JSON Schema、`backend/core` 枚举一一对应。

## 使用约定

1. 视图层只允许 `import { apiClient } from "@/api"`（即本目录 `index.ts`），不得自行 fetch。
2. 校验失败统一抛 `ApiRequestError`，其 `error.code` 与后端错误码一致：
   - `E002` AgentMessageRequest 空引用（发言门槛）
   - `E004` 引用未 APPROVED 条目（幻觉传染防御，附 `action: "PROJECT_PAUSED"`）
   - `E101` StageAdvanceRequest 空人类输入（防袖手旁观 → 推进按钮灰显 + tooltip）
   - `E202` 门禁驳回未填 reason
   - `B301` 黑板只读（基线冻结后）
3. 任何字段/端点变更必须先改 `/contracts` 并提 ADR，再同步本目录。
