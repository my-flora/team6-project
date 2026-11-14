(function (VPR) {
  'use strict';

  /* ------------------------------------------------------------------
   * ⑥ 前端·交互侧 · 人类介入工作台外壳
   * 负责：导航、写操作闸门提示、底部人类介入条（推进 / 拉回 / 强制收敛）、提示条
   * 不负责：阶段进度条、项目状态、轮次提示、Agent 状态灯、时间盒倒计时、黑板四色、PRD 阅读页（⑤）
   * ------------------------------------------------------------------ */

  var u = VPR.util;

  VPR.state = { view: 'gate', human_input: '' };

  VPR.navItems = [
    { key: 'gate', label: '门禁面板', dot: true },
    { key: 'input', label: '阶段 1 结构化输入' },
    { key: 'review', label: '阶段 4 评审' },
    { key: 'signoff', label: '阶段 6 会签' },
    { key: 'change', label: '变更申请' }
  ];

  VPR.headerHTML = function () {
    return '<div class="hdr">' +
      '<div style="min-width:0;">' +
        '<div class="hdr-title">' + u.esc(VPR.db.project.name) + ' · 人类介入工作台</div>' +
        '<div class="hdr-sub">⑥ 前端·交互侧 ｜ 门禁面板 / 阶段 1 输入 / 阶段 4 评审 / 阶段 6 会签 / 变更申请</div>' +
      '</div>' +
    '</div>';
  };

  VPR.navHTML = function () {
    return '<div class="nav">' + VPR.navItems.map(function (it) {
      var dot = it.dot && VPR.pendingGateCount() > 0
        ? '<span class="dot">' + VPR.pendingGateCount() + '</span>' : '';
      return '<button data-act="view" data-view="' + it.key + '" class="' +
        (VPR.state.view === it.key ? 'on' : '') + '">' + it.label + dot + '</button>';
    }).join('') + '</div>';
  };

  /* 只解释“为什么写不进去”，不承担项目状态展示（状态展示归 ⑤） */
  VPR.bannerHTML = function () {
    if (VPR.db.project.status === 'FROZEN') {
      return '<div class="banner ok">写操作闸门：基线已冻结，本页所有写入会被后端拒绝（403 BLACKBOARD_READONLY），任何改动须走变更申请。</div>';
    }
    if (VPR.db.review.deadlock) {
      return '<div class="banner danger">红蓝死锁：方案已修改 ' + VPR.db.review.revision_count +
        ' 次仍被驳回。请在门禁面板点击「拍板」并填写裁决理由。</div>';
    }
    return '';
  };

  VPR.footerHTML = function () {
    return '<div class="bar"><div class="bar-inner">' +
      '<div class="field"><label for="human-input">人类确认意见 human_prompt_input <span class="req">*</span>（不填则推进被后端拒绝：400 STAGE_ADVANCE_NO_HUMAN_INPUT）</label>' +
        '<textarea id="human-input" placeholder="例：同意进入下一步，成本上限按 5 万执行，不做支付">' +
        u.esc(VPR.state.human_input) + '</textarea></div>' +
      '<div class="bar-actions">' +
        '<button class="btn primary" data-act="advance" aria-disabled="' +
          (VPR.state.human_input.trim() === '' ? 'true' : 'false') + '">进入下一阶段</button>' +
        '<button class="btn" data-act="pull">拉回主轴</button>' +
        '<button class="btn" data-act="converge">强制收敛</button>' +
      '</div>' +
    '</div></div>';
  };

  VPR.demoHTML = function () {
    var d = VPR.demo;
    return '<div class="demo"><strong>演示开关</strong>（接入真实后端后删除）<br>' +
      '<label><input type="checkbox" data-act="demo" data-key="upstream_blocked" ' + (d.upstream_blocked ? 'checked' : '') + '> 上游存在未通过条目（触发 403）</label>' +
      '<label><input type="checkbox" data-act="demo" data-key="force_deadlock" ' + (d.force_deadlock ? 'checked' : '') + '> 强制第 4 阶段进入红蓝死锁</label>' +
      '<label><input type="checkbox" data-act="demo" data-key="extra_gate" ' + (d.extra_gate ? 'checked' : '') + '> 追加一条待处理门禁（触发 409）</label>' +
      '<div style="margin-top:6px;">时间盒与轮次不在此展示（归 ⑤）。</div>' +
      '</div>';
  };

  VPR.render = function () {
    var page = VPR.pages[VPR.state.view] || VPR.pages.gate;
    document.getElementById('app').innerHTML =
      VPR.headerHTML() + VPR.navHTML() + VPR.bannerHTML() +
      '<div class="main">' + page.render() + '</div>' +
      VPR.demoHTML() + VPR.footerHTML();
  };

  /* ------------------------- 底部条上的三个写动作 ------------------------- */

  VPR.actionMap.advance = function () {
    var input = u.val('human-input');
    if (input === '') { VPR.fail(400, 'STAGE_ADVANCE_NO_HUMAN_INPUT'); return; }
    if (VPR.db.project.status === 'FROZEN') {
      VPR.fail(403, 'BLACKBOARD_READONLY', '基线已冻结，只能提交变更申请'); return;
    }
    if (VPR.demo.upstream_blocked) {
      VPR.db.project.status = 'PAUSED';
      VPR.fail(403, 'UPSTREAM_NOT_APPROVED');
      VPR.render();
      return;
    }
    if (VPR.pendingGateCount() > 0) { VPR.fail(409, 'STAGE_HAS_PENDING_GATE'); return; }
    if (VPR.db.project.current_stage >= 6) {
      VPR.toast(200, 'STAGE_ADVANCED', '已在最后一个阶段'); return;
    }
    VPR.db.project.current_stage += 1;
    var cur = VPR.db.project.current_stage;
    VPR.db.stages.forEach(function (st) {
      if (st.stage_no < cur) st.status = 'COMPLETED';
      if (st.stage_no === cur) st.status = 'IN_PROGRESS';
    });
    VPR.ok('STAGE_ADVANCED', '已推进到阶段 ' + cur);
    VPR.render();
  };

  VPR.actionMap.pull = function () {
    var input = u.val('human-input');
    if (input === '') { VPR.fail(400, 'VALIDATION_REQUIRED_INPUT', '拉回主轴必须填写理由 Prompt'); return; }
    VPR.db.round.round_no = 1;
    VPR.db.round.status = 'ONGOING';
    VPR.ok('PULLED');
    VPR.render();
  };

  VPR.actionMap.converge = function () {
    if (VPR.db.round.status !== 'ONGOING') {
      VPR.fail(409, 'VALIDATION_REQUIRED_INPUT', '只能在 ONGOING 状态执行强制收敛'); return;
    }
    VPR.db.round.status = 'CONVERGED';
    VPR.ok('CONVERGED');
    VPR.render();
  };

  VPR.actionMap.demo = function (el) {
    VPR.demo[el.getAttribute('data-key')] = el.checked;
    if (VPR.demo.force_deadlock) {
      VPR.db.review.deadlock = true;
      VPR.db.project.status = 'PAUSED';
    }
    if (!VPR.demo.force_deadlock && VPR.db.review.deadlock && VPR.db.project.status === 'PAUSED') {
      VPR.db.review.deadlock = false;
      VPR.db.project.status = 'RUNNING';
    }
    VPR.render();
  };

  /* ------------------------------- 事件 ------------------------------- */

  function onClick(ev) {
    var el = ev.target.closest ? ev.target.closest('[data-act]') : null;
    if (!el) return;
    var act = el.getAttribute('data-act');
    if (act === 'view') {
      VPR.state.view = el.getAttribute('data-view');
      VPR.render();
      return;
    }
    var fn = VPR.actionMap[act];
    if (fn) fn(el);
  }

  function onInput(ev) {
    var t = ev.target;
    if (!t || !t.id) return;
    if (t.id === 'human-input') {
      VPR.state.human_input = t.value;
      var btn = document.querySelector('[data-act="advance"]');
      if (btn) btn.setAttribute('aria-disabled', t.value.trim() === '' ? 'true' : 'false');
    }
    if (t.id.indexOf('f-') === 0) {
      var err = document.getElementById('err-' + t.id);
      if (err && t.value.trim() !== '') { err.style.display = 'none'; t.style.borderColor = ''; }
    }
  }

  VPR.start = function () {
    var toasts = document.createElement('div');
    toasts.id = 'toasts';
    toasts.className = 'toast-wrap';
    document.body.appendChild(toasts);

    var app = document.getElementById('app');
    app.addEventListener('click', onClick);
    app.addEventListener('input', onInput);

    /* ?view=gate|input|review|signoff|change 直达某页，方便演示与单独截图 */
    var m = /[?&]view=([a-z]+)/.exec(window.location.search || '');
    if (m && VPR.navItems.some(function (it) { return it.key === m[1]; })) {
      VPR.state.view = m[1];
    }

    VPR.render();
  };
})(window.VPR);
