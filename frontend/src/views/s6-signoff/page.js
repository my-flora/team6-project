(function (VPR) {
  'use strict';

  /* ⑥ 阶段 6 · 会签与基线冻结 + 基线后变更申请
   * 真实目录：/frontend/src/views/s6-signoff/
   * 注意：变更申请页在分工清单里没有单独目录，暂放此目录，建目录前先跟组长确认 */

  var u = VPR.util;

  function signoffHTML() {
    var db = VPR.db;
    var allApproved = db.signoffs.every(function (s) { return s.status === 'APPROVED'; });
    var frozen = db.project.status === 'FROZEN';

    var rows = db.signoffs.map(function (s) {
      return '<tr>' +
        '<td>' + s.label + '<div class="mono">' + s.role + '</div></td>' +
        '<td>' + u.chip(s.status, s.status) + '</td>' +
        '<td>' + (s.operator ? u.esc(s.operator) : '<span class="hint">未签署</span>') + '</td>' +
        '<td><div class="row"><input type="text" id="op-' + s.role + '" placeholder="签署人姓名" style="width:120px;">' +
          '<button class="btn sm" data-act="sign" data-role="' + s.role + '">签署</button></div></td>' +
        '</tr>';
    }).join('');

    var left = '';
    if (db.signing_started_at) {
      var end = new Date(db.signing_started_at).getTime() + 24 * 3600 * 1000;
      var diff = end - Date.now();
      if (diff <= 0) {
        left = '<div class="banner danger">会签已超过 24 小时仍未全绿，按规则应升级告警 PM。</div>';
      } else {
        var h = Math.floor(diff / 3600000);
        var m = Math.floor((diff % 3600000) / 60000);
        left = '<div class="hint">会签剩余 <span class="countdown">' + h + ' 小时 ' + m +
          ' 分</span>（发起后 24 小时未全绿将升级 PM；此为会签超时，不是讨论时间盒）</div>';
      }
    }

    return '<div class="card">' +
      '<div class="row-between"><div class="card-title">阶段 6 · 三方会签与基线冻结</div>' +
        (frozen ? u.chip('FROZEN ' + (db.baseline ? db.baseline.version : ''), 'FROZEN') : u.chip('待会签', 'PENDING')) + '</div>' +
      '<div class="card-desc">业务 / 开发 / 测试三方并行签署，不可一人代签；三方全部 APPROVED 后才允许冻结基线，冻结后黑板只读。</div>' +
      '<table><thead><tr><th>角色</th><th>状态</th><th>签署人</th><th>操作</th></tr></thead><tbody>' + rows + '</tbody></table>' +
      left +
      '<div class="row" style="margin-top:12px;">' +
        '<button class="btn primary" data-act="freeze" ' + (allApproved ? '' : 'aria-disabled="true"') + '>冻结基线</button>' +
        '<button class="btn" data-act="view" data-view="change">去提交变更申请</button>' +
      '</div>' +
    '</div>';
  }

  function changeHTML() {
    var db = VPR.db;
    var frozen = db.project.status === 'FROZEN';
    var list = db.change_requests.length
      ? '<div class="card"><div class="card-title" style="margin-bottom:6px;">变更申请记录</div>' +
        db.change_requests.map(function (c) {
          return '<div class="hint">' + u.esc(c.id) + '　' + u.chip(c.status, 'PENDING') +
            '　impact=' + u.esc(c.impact) + '　' + u.esc(c.content.slice(0, 40)) + '</div>';
        }).join('') + '</div>'
      : '';

    return '<div class="card">' +
      '<div class="card-title" style="margin-bottom:4px;">基线后变更申请</div>' +
      '<div class="card-desc">基线冻结后任何改动须提交变更请求 → 影响评估（范围 / 成本 / 工期）→ 审批，批准后按版本更新基线。</div>' +
      (frozen ? '' : '<div class="banner info">当前项目尚未冻结，变更流程未激活。可先在会签页冻结基线后再来。</div>') +
      '<div class="field"><label for="cr-content">变更内容</label>' +
        '<textarea id="cr-content" placeholder="例：新增「书籍成色分级」字段，需同步改需求文档与验收标准"></textarea></div>' +
      '<div class="field"><label for="cr-impact">影响评估</label>' +
        '<select id="cr-impact" ' + (frozen ? '' : 'disabled') + '>' +
          '<option value="scope">范围影响</option>' +
          '<option value="cost">成本影响</option>' +
          '<option value="schedule">工期影响</option>' +
        '</select></div>' +
      '<button class="btn primary" data-act="cr-submit" ' + (frozen ? '' : 'aria-disabled="true"') + '>提交变更申请</button>' +
    '</div>' + list;
  }

  VPR.pages.signoff = { render: signoffHTML };
  VPR.pages.change = { render: changeHTML };

  VPR.actionMap.sign = function (el) {
    var db = VPR.db;
    var role = el.getAttribute('data-role');
    var op = u.val('op-' + role);
    if (op === '') { VPR.fail(400, 'VALIDATION_REQUIRED_INPUT', '请填写签署人姓名'); return; }

    var dup = db.signoffs.filter(function (s) {
      return s.role !== role && s.status === 'APPROVED' && s.operator === op;
    })[0];
    if (dup) { VPR.fail(409, 'SIGN_DUPLICATE'); return; }

    var s = db.signoffs.filter(function (x) { return x.role === role; })[0];
    s.status = 'APPROVED';
    s.operator = op;
    if (!db.signing_started_at) db.signing_started_at = new Date().toISOString();
    VPR.ok('SIGNED', (s.label || role) + ' 已签署：' + op);
    VPR.render();
  };

  VPR.actionMap.freeze = function () {
    var db = VPR.db;
    var allApproved = db.signoffs.every(function (s) { return s.status === 'APPROVED'; });
    if (!allApproved) { VPR.fail(409, 'SIGN_INCOMPLETE'); return; }
    db.baseline = { version: 'v1.0.0', frozen_at: new Date().toISOString() };
    db.project.status = 'FROZEN';
    VPR.ok('FROZEN_OK', 'Baseline ' + db.baseline.version + ' 已生成，黑板进入只读 + 变更申请状态');
    VPR.render();
  };

  VPR.actionMap['cr-submit'] = function () {
    var db = VPR.db;
    if (db.project.status !== 'FROZEN') {
      VPR.fail(409, 'BLACKBOARD_READONLY', '项目未冻结，变更流程未激活'); return;
    }
    var content = u.val('cr-content');
    if (content === '') { VPR.fail(400, 'VALIDATION_REQUIRED_INPUT', '变更内容不得为空'); return; }
    var impact = document.getElementById('cr-impact').value;
    db.change_requests.push({
      id: 'cr-' + (db.change_requests.length + 1),
      content: content,
      impact: impact,
      status: 'PENDING'
    });
    VPR.ok('CR_SUBMITTED');
    VPR.render();
  };
})(window.VPR);
