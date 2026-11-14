# ADR-004：补充 HUMAN 角色、拍板 DECIDED 入口与会签签署接口

- 状态：已接受
- 日期：2026-11-14
- 决策人：陈欣然（角色1）
- 触发：前端交互侧联调反馈的三个后端缺口

## 决策

### 1. AgentRole 增加 HUMAN

规格书 1.2 的 AgentRole 未含人类取值，导致阶段 1 人类输入初始上下文卡片时无合法 `source_agent`（被迫暂挂 PM）。
决策：`AgentRole` 增加 `HUMAN = "HUMAN"`，专用于人类直接产出的黑板条目（阶段 1 输入、人类门禁产出等）。
Agent 消息契约 `contracts/agent-message.schema.json` 与前端类型同步更新。

### 2. 拍板 DECIDED 入口

`GateService.decide_gate` 原来只接受 APPROVED/REJECTED（E203），前端拍板按钮无 API。
决策：裁决扩展为三值——
- `APPROVED`：通过；
- `REJECTED`：驳回，reason 必填（E202）；
- `DECIDED`：人类拍板，仅系统判定「争议死锁」时激活，理由必填并记录（E204）。
重复裁决仍拒绝（E201）。

### 3. 会签签署接口

原 `/baseline` 只有 freeze 与 change-requests，会签无签署入口。
决策新增三个错误码与两个端点：
- `POST /baseline/signoffs/init`：初始化三方会签单（business/development/testing）；
- `POST /baseline/signoffs`：签署；错误码 B401 签署人为空、B402 方位非法、B403 未初始化、B404A 重复签署、B405 不可一人代签（同一签署人只能签一个方位）。

## 后果

- 契约版本仍为 V1.0 的增补（新增枚举值与端点，不改动既有字段），前端按此升级即可；
- 张吴博 T9 会签联动：签署走 `/baseline/signoffs`，冻结仍走 `/baseline/freeze`；
- 江艳菲拍板按钮调用 `apiClient.decideGate({ decision: "DECIDED", reason })`。
