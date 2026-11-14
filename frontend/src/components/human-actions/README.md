# ⑥ 前端·交互侧：人类介入工作台

> 归属：⑥ 江艳菲　｜　形态：零依赖静态原型（双击 `workbench.html` 即用，不需要 npm、不需要后端）

## 一、文件都在这几个我负责的目录里

| 目录（分工清单中 ⑥ 的目录） | 文件 | 作用 |
|---|---|---|
| `frontend/src/views/gate/` | `page.js` | 门禁面板：通过 / 驳回（reason 必填）/ 拍板（仅死锁）、待办计数 |
| `frontend/src/views/s1-input/` | `page.js` | 阶段 1 结构化输入：5 个必填字段 + 风险登记区 |
| `frontend/src/views/s4-review/` | `page.js` | 阶段 4 评审：6 维度打分、致命缺陷、结论与退回 |
| `frontend/src/views/s6-signoff/` | `page.js` | 阶段 6 会签与冻结；变更申请页暂放此处（清单未单独分配目录，建目录前先报组长） |
| `frontend/src/components/human-actions/` | `workbench.html` | 工作台入口（外壳 + 导航） |
| 同上 | `human-actions.js` | 底部人类介入条：推进 / 拉回 / 强制收敛、提示条、页面装配 |
| 同上 | `human-actions.css` | 写类控件与页面样式 |
| 同上 | `mock.js` | 开发期假数据、错误码字典、维度配置；接后端后替换 |

没有额外的“原型专用目录”，所有文件都落在上面这些目录内。

## 二、不碰的范围（⑤ 徐欣雨）

- 目录：`/frontend/src/views/{dashboard,blackboard,s2-discussion,s3-proposal,s5-prd}`、`/components/display`
- 信号：阶段进度条、黑板四色状态与冲突标签、轮次提示、Agent 状态灯、时间盒倒计时、PRD 阅读页
- `/frontend/src/api` 是 ① 的，本侧不往里写请求封装，等它的 client 生成后替换 `mock.js`

## 三、打开方式

- 双击 `frontend/src/components/human-actions/workbench.html`
- 支持 `?view=gate|input|review|signoff|change` 直达某页（如 `workbench.html?view=review`）

## 四、可以当场演示的错误码

| 错误码 | 触发方式 |
|---|---|
| `STAGE_ADVANCE_NO_HUMAN_INPUT` | 意见框留空点推进 |
| `STAGE_HAS_PENDING_GATE` | 有门禁待办时填好意见再推进 |
| `UPSTREAM_NOT_APPROVED` | 勾「上游存在未通过条目」后推进 |
| `GATE_REJECT_NO_REASON` | 驳回不填理由 |
| `GATE_DECIDE_NOT_ALLOWED` | 非死锁点拍板；勾「强制死锁」后解锁 |
| `SIGN_DUPLICATE` | 同一姓名签两个角色 |
| `BLACKBOARD_READONLY` | 冻结后点门禁“通过”，或未冻结时提交变更申请 |

## 五、接真实后端要改哪几处

1. `VPR.ok` / `VPR.fail` 换成真实 `fetch` 响应处理，`code` 分支保持不变。
2. `VPR.db` 换成 store（字段形状不变），或直接用 ① 生成的 client 返回值。
3. 页面文件保持一个页面一个 `page.js`，不要跨目录引用 ⑤ 的视图。
4. 需要新的共用控件（比如通用弹窗）时先报 ① 定目录，不要塞进 `components/display`。

## 六、已知简化

- 置灰按钮仍可点击，为了让评审当场看到对应 `code`；真实实现用 `disabled` + tooltip。
- 无真实 Agent、无持久化，刷新回到初始 mock。
- 会签 24 小时倒计时为演示值；时间盒归 ⑤，本侧不做。
