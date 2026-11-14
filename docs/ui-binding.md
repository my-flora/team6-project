# 前端交互侧 · 信号与错误码绑定（ui-binding）

> 归属：⑥ 江艳菲　｜　配套代码：`prototype/interaction/`

## 0. 范围：这份文件只写“人类写入类”控件

**在范围内**：门禁通过 / 驳回 / 拍板、阶段 1 输入提交、评审结论提交、三方会签、冻结基线、变更申请、推进 / 拉回 / 强制收敛。

**不在范围内（归 ⑤ 徐欣雨）**：阶段进度条、黑板条目四色与冲突标签、轮次提示、Agent 状态灯、时间盒倒计时、PRD 阅读页。

**状态色与中文文案**由 ⑤ 在 `/frontend/src/components/display` 统一定义，本侧**只引用、不定义颜色值**。字段名以 `/contracts` 为准，本文件与 `/contracts` 冲突时以 `/contracts` 为准。

## 一、五个写类控件：各自只有一种启用条件

| 控件 | 所在页面 | 启用条件 | 前端前置校验 | 失败表现 |
|---|---|---|---|---|
| 进入下一阶段 | 底部固定条 | `human_prompt_input` 非空 | 意见为空则按钮置灰 | `400 STAGE_ADVANCE_NO_HUMAN_INPUT`；`409 STAGE_HAS_PENDING_GATE` 时提示去处理门禁；`403 UPSTREAM_NOT_APPROVED` 时提示项目已暂停 |
| 拉回主轴 | 底部固定条 | 议题 `RoundStatus=ONGOING` | 必须填拉回理由 Prompt | 理由为空本地拦截；成功后轮次计数清零 |
| 强制收敛 | 底部固定条 | `RoundStatus=ONGOING` | 非 ONGOING 不可点 | 非 ONGOING 本地拦截，不置 `CONVERGED` |
| 门禁通过 / 驳回 / 拍板 | 门禁面板 | 门禁 `GateStatus=PENDING`；拍板额外要求 `deadlock=true` | 驳回必须填 `reason` | `400 GATE_REJECT_NO_REASON`；`409 GATE_DECIDE_NOT_ALLOWED`；冻结后 `403 BLACKBOARD_READONLY` |
| 会签 / 冻结基线 | 阶段 6 | 会签：任一角色未签；冻结：三方全 `APPROVED` | 签署人姓名必填；同一人不得签两个角色 | `409 SIGN_DUPLICATE`；未全绿点冻结 → `409 SIGN_INCOMPLETE` |

## 二、九个契约错误码 → 界面上的具体表现

| code | HTTP | 出现在哪个控件 | 界面表现 |
|---|---|---|---|
| `STAGE_ADVANCE_NO_HUMAN_INPUT` | 400 | 推进按钮 | 按钮置灰 + tooltip「需填写人类确认意见」 |
| `STAGE_HAS_PENDING_GATE` | 409 | 推进按钮 | tooltip 显示「有 N 条门禁待处理」，点击跳转门禁面板 |
| `UPSTREAM_NOT_APPROVED` | 403 | 推进按钮 / 下游读取 | 按钮禁用 + 提示「上游条目未通过」；本侧不展示项目状态，状态由 ⑤ 呈现 |
| `GATE_REJECT_NO_REASON` | 400 | 门禁驳回 | 驳回输入框标红，处置不落库 |
| `GATE_DECIDE_NOT_ALLOWED` | 409 | 拍板按钮 | 非死锁时按钮 `aria-disabled`，点击提示「仅死锁可用」 |
| `SIGN_DUPLICATE` | 409 | 会签签署 | 第二个角色签署失败，已签记录保留并提示代签违规 |
| `BLACKBOARD_READONLY` | 403 | 所有写操作 | 顶部「写操作闸门」提示；写按钮禁用；变更申请入口保留 |
| `MSG_NO_REFERENCE` | 400 | 不在本侧（Agent 发言） | 由 ② 的后端拦截；若将来做人工代 Agent 补录，复用同一 code |
| `ROUND_LIMIT_EXCEEDED` | — | 强制收敛 | 达 `max_rounds` 时系统自动置 `CONVERGED`，本侧仅禁用“强制收敛”按钮 |

## 三、联调前自测清单

- [ ] 空意见点推进 → `400`，按钮确实置灰
- [ ] 有门禁待办时推进 → `409`，不改变阶段号
- [ ] 驳回不填理由 → `400`，不生成驳回记录
- [ ] 非死锁点拍板 → `409`；死锁后可点，且必须填理由
- [ ] 一人签两方 → `409 SIGN_DUPLICATE`
- [ ] 三方未全绿点冻结 → 失败；全绿后冻结 → 所有写入被拒
- [ ] 阶段 1 五字段逐个留空提交 → 对应字段标红，无请求发出
- [ ] 评分低于某维度 `min_score` → 结论 `REJECTED` 且列出未达标维度
- [ ] 连续两次 `REJECTED` → 死锁、拍板解锁
- [ ] 检查：本侧页面没有出现阶段进度条、轮次提示、状态灯、倒计时、PRD 阅读页
