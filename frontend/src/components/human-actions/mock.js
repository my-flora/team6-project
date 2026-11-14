(function (global) {
  'use strict';

  /* ------------------------------------------------------------------
   * ⑥ 前端·交互侧 · mock 数据与错误码字典
   * 仅本侧开发期使用：接真实后端后，把 VPR.ok / VPR.fail 换成 fetch 响应处理即可，
   * 数据换成 ① 的 schema 驱动。字段名严格按 docs/contract-freeze 的 snake_case 契约。
   * ------------------------------------------------------------------ */

  var VPR = global.VPR = global.VPR || {};
  VPR.pages = {};
  VPR.actionMap = {};

  VPR.CODE_TEXT = {
    /* 契约内错误码 */
    STAGE_ADVANCE_NO_HUMAN_INPUT: '推进前必须填写人类确认意见（human_prompt_input 不得为空）',
    UPSTREAM_NOT_APPROVED: '上游存在未通过条目，读取被阻断，项目已暂停',
    STAGE_HAS_PENDING_GATE: '当前阶段仍有未处理的门禁，不能推进',
    GATE_REJECT_NO_REASON: '驳回必须填写理由（reason 不得为空）',
    GATE_DECIDE_NOT_ALLOWED: '仅在红蓝死锁状态下允许人类拍板（DECIDED）',
    SIGN_DUPLICATE: '同一操作人不能签署两个角色，不可一人代签',
    BLACKBOARD_READONLY: '基线已冻结，黑板只读，任何改动须走变更申请',
    MSG_NO_REFERENCE: 'Agent 发言必须引用上下文（references 不得为空）',
    ROUND_LIMIT_EXCEEDED: '议题已达 max_rounds=5，系统强制 CONVERGED',
    /* 前端本地校验，非后端契约 */
    VALIDATION_REQUIRED_INPUT: '该操作需要先填写理由或意见（前端本地校验）',
    /* 流程结论，非错误 */
    REVIEW_REJECTED: '存在致命缺陷或维度未达最低分，退回阶段 3',
    REVIEW_PASS_WITH_FIX: '修改后通过：限期修复并复评指定维度',
    REVIEW_PASS: '评审通过：全部维度达最低分且无致命缺陷',
    SIGNED: '会签已记录',
    SIGN_INCOMPLETE: '三方未全部签署，无法冻结基线',
    FROZEN_OK: '基线已冻结，黑板进入只读',
    STAGE_ADVANCED: '阶段推进成功',
    ENTRY_SUBMITTED: '初始上下文卡片已写入黑板，状态 PENDING_REVIEW',
    CR_SUBMITTED: '变更申请已提交，等待影响评估与审批',
    APPROVED: '门禁已通过，条目置为 APPROVED，下游可读取',
    REJECTED: '已驳回并记录理由，条目回到 DRAFT，触发来源 Agent 重新生成',
    DECIDED: '已拍板并记录裁决理由，项目恢复运行',
    PULLED: '已终止当前议题并拉回主轴，轮次计数清零',
    CONVERGED: 'RoundStatus → CONVERGED，PM 停止 Agent 发言并输出总结'
  };

  /* 阶段 4 的评价维度：权重与最低可接受分（人类设定，红队按维度打分） */
  VPR.DIMENSIONS = [
    { key: 'SECURITY', label: '安全', weight: 0.25, min_score: 60, score: 75 },
    { key: 'PERFORMANCE', label: '性能', weight: 0.15, min_score: 50, score: 70 },
    { key: 'COMPLIANCE', label: '合规', weight: 0.20, min_score: 70, score: 68 },
    { key: 'ROI', label: '投资回报', weight: 0.20, min_score: 60, score: 72 },
    { key: 'UX', label: '用户体验', weight: 0.10, min_score: 50, score: 66 },
    { key: 'MAINTAINABILITY', label: '可维护性', weight: 0.10, min_score: 50, score: 64 }
  ];

  VPR.db = {
    project: { id: 'p-001', name: '校园二手书小程序', current_stage: 4, status: 'RUNNING' },
    stages: [
      { stage_no: 1, name: '想法', status: 'COMPLETED' },
      { stage_no: 2, name: '多体讨论', status: 'COMPLETED' },
      { stage_no: 3, name: '建设方案', status: 'COMPLETED' },
      { stage_no: 4, name: '多方评价', status: 'IN_PROGRESS' },
      { stage_no: 5, name: '需求', status: 'NOT_STARTED' },
      { stage_no: 6, name: '需求确认', status: 'NOT_STARTED' }
    ],
    entries: [
      { id: 'e-101', stage_no: 3, title: '方案草案 v1（裁剪后 4 条核心路径）', status: 'APPROVED', source_agent: 'ARCH' },
      { id: 'e-102', stage_no: 4, title: '红队质疑：成本估算偏低 30%', status: 'PENDING_REVIEW', source_agent: 'RED_TEAM' },
      { id: 'e-103', stage_no: 4, title: '合规：二手交易需实名与发票留存', status: 'PENDING_REVIEW', source_agent: 'TECH' }
    ],
    gates: [
      { id: 'g-201', entry_id: 'e-102', title: '红队质疑：成本估算偏低 30%', status: 'PENDING', reason: '', operator: '' },
      { id: 'g-202', entry_id: 'e-103', title: '合规：二手交易需实名与发票留存', status: 'PENDING', reason: '', operator: '' },
      { id: 'g-203', entry_id: 'e-101', title: '阶段 3 草案定稿审查', status: 'APPROVED', reason: '', operator: '张嘉辉' }
    ],
    /* 轮次只用于“拉回 / 强制收敛”的状态判断；轮次提示与时间盒倒计时归 ⑤，本侧不渲染 */
    round: { topic: '二手书定价与信任机制', round_no: 3, max_rounds: 5, status: 'ONGOING' },
    review: { revision_count: 0, deadlock: false, conclusion: null, weighted: null, failed: [], defects: [] },
    signoffs: [
      { role: 'BUSINESS', label: '业务', status: 'PENDING', operator: '' },
      { role: 'DEV', label: '开发', status: 'PENDING', operator: '' },
      { role: 'QA', label: '测试', status: 'PENDING', operator: '' }
    ],
    signing_started_at: null,
    baseline: null,
    change_requests: []
  };

  VPR.demo = { upstream_blocked: false, force_deadlock: false, extra_gate: false };

  VPR.util = {
    esc: function (v) {
      return String(v === null || v === undefined ? '' : v)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },
    val: function (id) {
      var el = document.getElementById(id);
      return el ? String(el.value || '').trim() : '';
    },
    chip: function (text, status) {
      var cls = 'chip chip-' + String(status || 'DRAFT').replace(/[^A-Za-z_]/g, '');
      return '<span class="' + cls + '">' + VPR.util.esc(text) + '</span>';
    }
  };

  VPR.pendingGateCount = function () {
    var n = VPR.db.gates.filter(function (g) { return g.status === 'PENDING'; }).length;
    return n + (VPR.demo.extra_gate ? 1 : 0);
  };

  VPR.toast = function (status, code, extra) {
    var wrap = document.getElementById('toasts');
    if (!wrap) return;
    var type = status >= 400 ? 'err' : (status >= 300 ? 'warn' : 'ok');
    var box = document.createElement('div');
    box.className = 'toast ' + (type === 'ok' ? 'ok' : (type === 'warn' ? 'warn' : ''));
    box.innerHTML = '<div class="t-code">[' + status + '] ' + VPR.util.esc(code) + '</div>' +
      '<div>' + VPR.util.esc(extra || VPR.CODE_TEXT[code] || '') + '</div>';
    wrap.appendChild(box);
    setTimeout(function () {
      if (box.parentNode) box.parentNode.removeChild(box);
    }, 4200);
  };

  VPR.ok = function (code, extra) { VPR.toast(200, code, extra); };
  VPR.fail = function (status, code, extra) { VPR.toast(status, code, extra); };
})(window);
