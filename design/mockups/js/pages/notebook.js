/* 수첩 · 증거 보드 목업 동작. 클래식 스크립트. 진술/증거/모순 쌍을 눌러 "비교"하고, 넓은 화면에서는 직선 점선 한 줄로 잇는다.
   탭 전환 자체는 js/mock.js 가 처리하고, 여기서는 폭에 따라 "3열 동시 표시"와 "탭 한 장 표시"만 바꾼다. */
(function () {
  'use strict';
  var doc = document;
  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  var board = $('[data-board]'), svg = $('[data-board-lines]');
  var mqTabs = window.matchMedia('(max-width: 899px)');
  var picked = null; // {type:'st'|'ev', id}

  /* 모순 쌍: 진술 id -> 증거 id */
  var PAIRS = [];
  $$('[data-st][data-conflict]').forEach(function (s) { PAIRS.push([s.getAttribute('data-st'), s.getAttribute('data-conflict')]); });
  function evEl(id) { return $('[data-ev="' + id + '"]'); }
  function stEl(id) { return $('[data-st="' + id + '"]'); }

  function pairsOf(sel) {
    if (!sel) return [];
    return PAIRS.filter(function (p) { return sel.type === 'st' ? p[0] === sel.id : p[1] === sel.id; });
  }

  function clearMarks() {
    $$('.is-picked, .is-linked').forEach(function (e) { e.classList.remove('is-picked', 'is-linked'); });
    $$('.contra-card.is-on').forEach(function (e) { e.classList.remove('is-on'); });
  }
  function apply() {
    clearMarks();
    var ps = pairsOf(picked);
    if (picked) {
      var me = picked.type === 'st' ? stEl(picked.id) : evEl(picked.id);
      if (me) me.classList.add('is-picked');
      ps.forEach(function (p) {
        var s = stEl(p[0]), e = evEl(p[1]);
        if (picked.type === 'st' && e) e.classList.add('is-linked');
        if (picked.type === 'ev' && s) s.classList.add('is-linked');
        $$('.contra-card').forEach(function (c) { if (c.getAttribute('data-pair-st') === p[0] && c.getAttribute('data-pair-ev') === p[1]) c.classList.add('is-on'); });
      });
    }
    drawLines();
  }

  function colRect(el) { var c = el.closest('[data-col]'); return c ? c.getBoundingClientRect() : null; }
  function drawLines() {
    svg.innerHTML = '';
    if (mqTabs.matches || !picked) return;
    var br = board.getBoundingClientRect();
    svg.setAttribute('viewBox', '0 0 ' + br.width + ' ' + br.height);
    svg.setAttribute('width', br.width); svg.setAttribute('height', br.height);
    var out = '';
    pairsOf(picked).forEach(function (p) {
      var s = stEl(p[0]), e = evEl(p[1]); if (!s || !e) return;
      var sr = s.getBoundingClientRect(), er = e.getBoundingClientRect(), sc = colRect(s), ec = colRect(e);
      var x1 = sr.left - br.left, y1 = clamp(sr.top + sr.height / 2, sc) - br.top;
      var x2 = er.right - br.left, y2 = clamp(er.top + er.height / 2, ec) - br.top;
      out += '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"/>' +
             '<circle cx="' + x1 + '" cy="' + y1 + '" r="4.5"/><circle cx="' + x2 + '" cy="' + y2 + '" r="4.5"/>';
    });
    svg.innerHTML = out;
  }
  function clamp(y, col) { if (!col) return y; return Math.min(Math.max(y, col.top + 12), col.bottom - 12); }
  var raf = 0;
  function schedule() { if (raf) return; raf = requestAnimationFrame(function () { raf = 0; drawLines(); }); }
  $$('[data-col]').forEach(function (c) { c.addEventListener('scroll', schedule, { passive: true }); });
  window.addEventListener('resize', schedule);

  function reveal() { if (mqTabs.matches) return; $$('.is-linked, .is-picked').forEach(function (e) { if (e.closest('[data-col]')) e.scrollIntoView({ block: 'nearest' }); }); drawLines(); }
  function toggle(type, id) {
    picked = (picked && picked.type === type && picked.id === id) ? null : { type: type, id: id };
    apply(); if (picked) reveal();
    if (window.MockUI && picked) {
      var n = pairsOf(picked).length;
      window.MockUI.say(n ? '어긋나는 쌍 ' + n + '개를 비교합니다.' : '이 항목은 어긋나는 쌍이 없습니다.');
    }
  }
  $$('[data-st]').forEach(function (b) { b.addEventListener('click', function () { toggle('st', b.getAttribute('data-st')); }); });
  $$('[data-ev]').forEach(function (b) { b.addEventListener('click', function () { toggle('ev', b.getAttribute('data-ev')); }); });
  $$('[data-pair-st]').forEach(function (b) {
    b.addEventListener('click', function () {
      picked = { type: 'st', id: b.getAttribute('data-pair-st') }; apply(); reveal();
      if (mqTabs.matches) { // 한 장 보기에서는 진술 탭으로 옮겨 어긋나는 증거 이름을 보여 준다
        $('#tab-statements').click();
        var s = stEl(picked.id); if (s) s.scrollIntoView({ block: 'center' });
      }
    });
  });

  /* ---------- 폭에 따른 보기 방식 ---------- */
  function syncMode() {
    if (mqTabs.matches) {
      var cur = $('[role=tab][aria-selected=true]');
      (cur || $('#tab-evidence')).click();
    } else {
      $$('[role=tabpanel]').forEach(function (p) { p.hidden = false; });
    }
    schedule();
  }
  mqTabs.addEventListener('change', syncMode);

  /* 처음 상태: 한소라의 진술과 출입카드 기록을 비교 중으로 둔다 */
  picked = { type: 'st', id: 's-do' };
  syncMode(); apply();
  doc.addEventListener('DOMContentLoaded', schedule);
  window.addEventListener('load', function () { schedule(); setTimeout(schedule, 300); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(schedule);
})();
