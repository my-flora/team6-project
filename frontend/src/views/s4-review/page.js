(function (VPR) {
  'use strict';

  /* ⑥ 阶段 4 · 评审打分：6 维度权重与最低分、致命缺陷、结论与退回
   * 真实目录：/frontend/src/views/s4-review/ */

  var u = VPR.util;

  function html() {
    var db = VPR.db;
    var rows = VPR.DIMENSIONS.map(function (d) {
      return '<tr>' +
        '<td>' + d.label + '<div class="mono">' + d.key + '</div></td>' +
        '<td class="num">' + (d.weight * 100) + '%</td>' +
        '<td class="num">' + d.min_score + '</td>' +
        '<td><input type="number" min="0" max="100" id="score-' + d.key + '" value="' + d.score + '"></td>' +
        '</tr>';
    }).join('');

    var result = '';
    if (db.review.conclusion) {
      result = '<div class="card">' +
        '<div class="row-between"><div class="card-title">评审结论 ReviewResult</div>' +
          u.chip(db.review.conclusion, db.review.conclusion) + '</div>' +
        '<div class="hint">加权总分 weighted=' + db.review.weighted +
          '　revision_count=' + db.review.revision_count +
          '　deadlock=' + (db.review.deadlock ? 'true' : 'false') + '</div>' +
        (db.review.failed.length
          ? '<div class="banner danger" style="margin-top:10px;">未达最低分维度：' + u.esc(db.review.failed.join('；')) + '</div>' : '') +
        (db.review.defects.length
          ? '<div class="banner danger">致命缺陷：' + u.esc(db.review.defects.join('；')) + '（无论分数一律 REJECTED）</div>' : '') +
        '</div>';
    }

    return '<div class="card">' +
      '<div class="card-title" style="margin-bottom:4px;">阶段 4 · 评审打分</div>' +
      '<div class="card-desc">人类先定维度与最低分，红队按维度质疑；任一维度低于 min_score 或存在致命缺陷则整案 REJECTED 并退回阶段 3。</div>' +
      '<table><thead><tr><th>评价维度</th><th>权重</th><th>最低分</th><th>打分</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>' +
      '<div class="field" style="margin-top:14px;">' +
        '<label>致命缺陷（勾选即 REJECTED）</label>' +
        '<div class="row" style="gap:16px;">' +
          '<label style="font-size:13px;color:var(--ink);"><input type="checkbox" id="def-cost"> 成本估算不可行</label>' +
          '<label style="font-size:13px;color:var(--ink);"><input type="checkbox" id="def-comp"> 合规不达标</label>' +
          '<label style="font-size:13px;color:var(--ink);"><input type="checkbox" id="def-core"> 核心功能不可行</label>' +
        '</div>' +
      '</div>' +
      '<div class="row"><button class="btn primary" data-act="review-submit">提交评审结论</button>' +
        '<span class="hint">连续两次 REJECTED（revision_count ≥ 2）→ 自动挂起，等待人类拍板</span></div>' +
    '</div>' + result;
  }

  VPR.pages.review = { render: html };

  VPR.actionMap['review-submit'] = function () {
    var db = VPR.db;
    var failed = [];

    VPR.DIMENSIONS.forEach(function (d) {
      var v = parseFloat(u.val('score-' + d.key));
      d.score = isNaN(v) ? 0 : v;
      if (d.score < d.min_score) {
        failed.push(d.label + '（' + d.score + ' < ' + d.min_score + '）');
      }
    });

    var defects = [];
    if (document.getElementById('def-cost').checked) defects.push('成本估算不可行');
    if (document.getElementById('def-comp').checked) defects.push('合规不达标');
    if (document.getElementById('def-core').checked) defects.push('核心功能不可行');

    var weighted = 0;
    VPR.DIMENSIONS.forEach(function (d) { weighted += d.score * d.weight; });
    weighted = Math.round(weighted * 10) / 10;

    db.review.weighted = weighted;
    db.review.failed = failed;
    db.review.defects = defects;

    var conclusion = 'PASS';
    if (defects.length || failed.length) conclusion = 'REJECTED';
    else if (weighted < 80) conclusion = 'PASS_WITH_FIX';
    db.review.conclusion = conclusion;

    if (conclusion === 'REJECTED') {
      db.review.revision_count += 1;
      VPR.fail(409, 'REVIEW_REJECTED');
      if (db.review.revision_count >= 2 || VPR.demo.force_deadlock) {
        db.review.deadlock = true;
        db.project.status = 'PAUSED';
        VPR.toast(409, 'GATE_DECIDE_NOT_ALLOWED',
          '方案已修改 ' + db.review.revision_count + ' 次仍被驳回 → 红蓝死锁，请人类在门禁面板拍板');
      }
    } else if (conclusion === 'PASS_WITH_FIX') {
      VPR.toast(200, 'REVIEW_PASS_WITH_FIX');
    } else {
      VPR.ok('REVIEW_PASS');
    }
    VPR.render();
  };
})(window.VPR);
