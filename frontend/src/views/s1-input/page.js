(function (VPR) {
  'use strict';

  /* ⑥ 阶段 1 · 结构化输入表单：5 个必填字段 + 待补充风险登记区
   * 真实目录：/frontend/src/views/s1-input/ */

  var u = VPR.util;

  var FIELDS = [
    { id: 'f-core', label: '核心目标（一句话）', ph: '例：把校内二手书流转从 3 天压到 1 天' },
    { id: 'f-aud', label: '目标受众（主要用户与购买者）', ph: '例：大一大二在校生为主' },
    { id: 'f-bound', label: '期望边界（成本上限 / 工期 / 合规 / 明确不做）', ph: '例：不接支付、不做物流、预算 5 万、12 周' },
    { id: 'f-success', label: '成功判据（如何衡量达成）', ph: '例：月活 500、成单率 ≥ 20%' },
    { id: 'f-value', label: '价值主张（一句话）', ph: '例：把书卖给隔壁班，比卖给平台快 3 天' }
  ];

  function html() {
    var form = FIELDS.map(function (f) {
      return '<div class="field"><label for="' + f.id + '">' + f.label + ' <span class="req">*</span></label>' +
        '<input type="text" id="' + f.id + '" placeholder="' + u.esc(f.ph) + '">' +
        '<div class="err" id="err-' + f.id + '" style="display:none;">必填项，空值会阻止提交</div></div>';
    }).join('');

    var submitted = VPR.db.entries.filter(function (e) { return e.id.indexOf('e-new') === 0; });
    var preview = submitted.length
      ? '<div class="card"><div class="row-between"><div class="card-title">初始上下文卡片（已写入黑板）</div>' +
        u.chip('PENDING_REVIEW', 'PENDING_REVIEW') + '</div>' +
        submitted.map(function (e) {
          return '<div class="hint mono">entry.id=' + e.id + '　status=' + e.status + '　stage_no=' + e.stage_no + '</div>';
        }).join('') +
        '<div class="hint">已生成门禁待办，等待门禁① 人类轻量审查。状态色与黑板列表由 ⑤ 的黑板页统一渲染，此处只给纯文本。</div></div>'
      : '';

    return '<div class="card">' +
      '<div class="card-title" style="margin-bottom:4px;">阶段 1 · 结构化输入</div>' +
      '<div class="card-desc">5 个字段全部必填；提交后写入黑板，状态 DRAFT → PENDING_REVIEW，并生成一条门禁待办。</div>' +
      form +
      '<div class="field"><label for="f-risk">待补充风险登记区（供阶段 2 直接填充，选填）</label>' +
        '<textarea id="f-risk" placeholder="例：卖家爽约、教材版本不匹配、同城面交安全"></textarea></div>' +
      '<div class="row"><button class="btn primary" data-act="input-submit">提交并写入黑板</button>' +
        '<button class="btn" data-act="view" data-view="gate">去看门禁</button></div>' +
    '</div>' + preview;
  }

  VPR.pages.input = { render: html };

  VPR.actionMap['input-submit'] = function () {
    var bad = [];
    FIELDS.forEach(function (f) {
      var ip = document.getElementById(f.id);
      var err = document.getElementById('err-' + f.id);
      var empty = u.val(f.id) === '';
      if (err) err.style.display = empty ? 'block' : 'none';
      if (ip) ip.style.borderColor = empty ? '#dc2626' : '';
      if (empty) bad.push(f.id);
    });
    if (bad.length) {
      VPR.fail(400, 'VALIDATION_REQUIRED_INPUT', bad.length + ' 个必填字段为空，已阻止提交');
      return;
    }

    var db = VPR.db;
    var n = db.entries.filter(function (e) { return e.id.indexOf('e-new') === 0; }).length + 1;
    var entry = {
      id: 'e-new' + n,
      stage_no: 1,
      title: u.val('f-core'),
      status: 'PENDING_REVIEW',
      source_agent: 'HUMAN'
    };
    db.entries.push(entry);
    db.gates.push({
      id: 'g-new' + n,
      entry_id: entry.id,
      title: '门禁① 审查：' + entry.title,
      status: 'PENDING',
      reason: '',
      operator: ''
    });
    VPR.ok('ENTRY_SUBMITTED');
    VPR.render();
  };
})(window.VPR);
