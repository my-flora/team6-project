(function (VPR) {
  'use strict';

  /* ⑥ 门禁面板：红点角标、通过 / 驳回（reason 必填）/ 拍板（仅死锁）
   * 真实目录：/frontend/src/views/gate/ */

  var u = VPR.util;

  function html() {
    var db = VPR.db;
    var frozen = db.project.status === 'FROZEN';
    var pending = db.gates.filter(function (g) { return g.status === 'PENDING'; }).length;
    var approved = db.gates.filter(function (g) { return g.status === 'APPROVED'; }).length;

    var cards = db.gates.map(function (g) {
      var e = db.entries.filter(function (x) { return x.id === g.entry_id; })[0] || {};
      var body = '';
      if (g.status === 'PENDING') {
        body = '<div class="field" style="margin:10px 0 8px;">' +
            '<input type="text" id="reason-' + g.id + '" placeholder="驳回理由 reason（驳回必填，通过可空）">' +
          '</div>' +
          '<div class="row">' +
            '<button class="btn ok sm" data-act="gate-approve" data-id="' + g.id + '">通过 APPROVED</button>' +
            '<button class="btn danger sm" data-act="gate-reject" data-id="' + g.id + '">驳回 REJECTED</button>' +
            (db.review.deadlock
              ? '<button class="btn sm" data-act="gate-decide" data-id="' + g.id + '">拍板 DECIDED</button>'
              : '<button class="btn sm" aria-disabled="true" data-act="gate-decide" data-id="' + g.id + '">拍板（仅死锁可用）</button>') +
          '</div>';
      }
      return '<div class="card">' +
        '<div class="row-between" style="margin-bottom:4px;">' +
          '<div class="card-title">' + u.esc(g.title) + '</div>' + u.chip(g.status, g.status) +
        '</div>' +
        '<div class="card-desc mono" style="margin-bottom:0;">gate.id=' + g.id +
          '　entry_id=' + u.esc(g.entry_id) +
          '　source_agent=' + u.esc(e.source_agent || '') + '</div>' +
        body +
        (g.reason ? '<div class="hint">处置理由：' + u.esc(g.reason) + (g.operator ? '（' + u.esc(g.operator) + '）' : '') + '</div>' : '') +
        '</div>';
    }).join('');

    return '<div class="card">' +
      '<div class="row-between">' +
        '<div class="card-title">门禁面板</div>' +
        '<div class="row">' + u.chip('待处理 ' + pending, 'PENDING') + u.chip('已通过 ' + approved, 'APPROVED') + '</div>' +
      '</div>' +
      '<div class="card-desc">驳回必须填 reason（否则返回 400 GATE_REJECT_NO_REASON）；「拍板」仅在红蓝死锁时可用（否则 409 GATE_DECIDE_NOT_ALLOWED）。</div>' +
      (frozen ? '<div class="banner warn">当前项目已冻结，门禁操作会被后端以 403 BLACKBOARD_READONLY 拒绝（可点击验证）。</div>' : '') +
    '</div>' + cards;
  }

  VPR.pages.gate = { render: html };

  VPR.actionMap['gate-approve'] = function (el) {
    var db = VPR.db;
    if (db.project.status === 'FROZEN') { VPR.fail(403, 'BLACKBOARD_READONLY'); return; }
    var g = db.gates.filter(function (x) { return x.id === el.getAttribute('data-id'); })[0];
    if (!g) return;
    g.status = 'APPROVED';
    g.operator = '人类（本机）';
    var e = db.entries.filter(function (x) { return x.id === g.entry_id; })[0];
    if (e) e.status = 'APPROVED';
    VPR.ok('APPROVED');
    VPR.render();
  };

  VPR.actionMap['gate-reject'] = function (el) {
    var db = VPR.db;
    if (db.project.status === 'FROZEN') { VPR.fail(403, 'BLACKBOARD_READONLY'); return; }
    var id = el.getAttribute('data-id');
    var reason = u.val('reason-' + id);
    if (reason === '') { VPR.fail(400, 'GATE_REJECT_NO_REASON'); return; }
    var g = db.gates.filter(function (x) { return x.id === id; })[0];
    if (!g) return;
    g.status = 'REJECTED';
    g.reason = reason;
    g.operator = '人类（本机）';
    var e = db.entries.filter(function (x) { return x.id === g.entry_id; })[0];
    if (e) e.status = 'DRAFT';
    VPR.ok('REJECTED');
    VPR.render();
  };

  VPR.actionMap['gate-decide'] = function (el) {
    var db = VPR.db;
    if (!db.review.deadlock) { VPR.fail(409, 'GATE_DECIDE_NOT_ALLOWED'); return; }
    var id = el.getAttribute('data-id');
    var reason = u.val('reason-' + id);
    if (reason === '') { VPR.fail(400, 'VALIDATION_REQUIRED_INPUT', '拍板必须记录裁决理由'); return; }
    var g = db.gates.filter(function (x) { return x.id === id; })[0];
    if (!g) return;
    g.status = 'DECIDED';
    g.reason = reason;
    g.operator = '人类（本机）';
    db.project.status = 'RUNNING';
    db.review.deadlock = false;
    VPR.ok('DECIDED');
    VPR.render();
  };
})(window.VPR);
