/* 목업 동작 (클래식 스크립트, file:// 에서 동작). 순수 JS, 모듈·fetch 없음.
   기능: 테마·분위기 전환, 표정 크로스페이드, 모순 연출, 증거 선택·제시 목록(popover), 서랍/시트(inert·포커스 복귀·Esc), 탭, 토스트.
   다른 화면에서 쓰는 법: 같은 data-* 속성을 쓰면 된다(common.css 맨 위 주석 참고). 없는 요소는 조용히 건너뛴다. */
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } return null; }
  function mq(q) { return window.matchMedia(q).matches; }
  var reduced = function () { return mq('(prefers-reduced-motion: reduce)'); };

  /* ---------- 테마 · 분위기 ---------- */
  function setTheme(t) {
    root.setAttribute('data-theme', t);
    $$('[data-set-theme]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-set-theme') === t)); });
    store('mock-theme', t);
  }
  function setMood(m) {
    if (m === 'normal') root.removeAttribute('data-mood'); else root.setAttribute('data-mood', m);
    $$('[data-set-mood]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-set-mood') === m)); });
    store('mock-mood', m);
  }
  $$('[data-set-theme]').forEach(function (b) { b.addEventListener('click', function () { setTheme(b.getAttribute('data-set-theme')); }); });
  $$('[data-set-mood]').forEach(function (b) { b.addEventListener('click', function () { setMood(b.getAttribute('data-set-mood')); }); });
  setTheme(store('mock-theme') || 'light');
  setMood(store('mock-mood') || 'normal');

  /* ---------- 토스트 · 스크린 리더 안내 ---------- */
  var MockUI = window.MockUI = {};
  MockUI.say = function (text) { var el = $('#sr-live'); if (el) { el.textContent = ''; setTimeout(function () { el.textContent = text; }, 30); } };
  MockUI.toast = function (o) {
    var stack = $('#toasts'); if (!stack) return;
    var t = doc.createElement('div'); t.className = 'toast';
    var p = doc.createElement('p'); p.textContent = o.text; t.appendChild(p);
    if (o.action) {
      var a = doc.createElement('button'); a.type = 'button'; a.className = 'btn';
      a.innerHTML = '<span class="btn-label"></span>'; a.firstChild.textContent = o.action.label;
      a.addEventListener('click', function () { o.action.run(); t.remove(); });
      t.appendChild(a);
    }
    var x = doc.createElement('button'); x.type = 'button'; x.className = 'btn'; x.setAttribute('aria-label', '알림 닫기');
    x.style.cssText = 'min-width:36px;min-height:36px;padding:0;border-color:transparent';
    x.innerHTML = '<span class="btn-label"><i data-icon="x"></i></span>';
    x.addEventListener('click', function () { t.remove(); });
    t.appendChild(x); stack.appendChild(t);
    if (window.renderIcons) window.renderIcons(t);
    setTimeout(function () { if (t.parentNode) t.remove(); }, o.ms || 7000);
  };

  /* ---------- 서랍 / 시트: inert + 포커스 복귀 + Esc ---------- */
  var scrim = $('[data-scrim]'), openDrawer = null, opener = null;
  var outside = $$('.status-strip, .stage-col, .actionbar, .map-col, .note-col');
  function inDrawerMode(d) { var q = d.getAttribute('data-drawer-mq'); return !q || mq(q); }
  function syncDrawers() {
    $$('.drawer[data-drawer]').forEach(function (d) {
      var mode = inDrawerMode(d);
      if (mode && !d.classList.contains('is-open')) d.setAttribute('inert', ''); else d.removeAttribute('inert');
      if (!mode) d.classList.remove('is-open');
    });
    if (openDrawer && !inDrawerMode(openDrawer)) closeDrawer(true);
  }
  function openD(name, btn) {
    var d = $('.drawer[data-drawer="' + name + '"]'); if (!d || !inDrawerMode(d)) return;
    if (openDrawer) closeDrawer(true);
    opener = btn || doc.activeElement; openDrawer = d;
    root.classList.add('drawer-open'); d.removeAttribute('inert'); d.classList.add('is-open'); if (scrim) scrim.classList.add('is-open');
    outside.forEach(function (el) { if (el !== d) el.setAttribute('inert', ''); });
    var f = $('[data-close]', d) || d; setTimeout(function () { f.focus(); }, reduced() ? 0 : 30);
  }
  function closeDrawer(silent) {
    if (!openDrawer) return;
    var d = openDrawer; openDrawer = null;
    root.classList.remove('drawer-open'); d.classList.remove('is-open'); if (scrim) scrim.classList.remove('is-open');
    outside.forEach(function (el) { el.removeAttribute('inert'); });
    syncDrawers();
    if (!silent && opener && opener.focus) opener.focus();
  }
  $$('[data-open]').forEach(function (b) { b.addEventListener('click', function () { openD(b.getAttribute('data-open'), b); }); });
  $$('[data-close]').forEach(function (b) { b.addEventListener('click', function () { closeDrawer(); }); });
  if (scrim) scrim.addEventListener('click', function () { closeDrawer(); });
  doc.addEventListener('keydown', function (e) { if (e.key === 'Escape' && openDrawer) { e.preventDefault(); closeDrawer(); } });
  window.matchMedia('(max-width: 1099px)').addEventListener('change', syncDrawers);
  window.matchMedia('(max-width: 720px)').addEventListener('change', function () { syncDrawers(); syncEarlier(); sizeActionbar(); });
  syncDrawers();

  /* ---------- 하단 행동바 높이를 CSS 변수로 (토스트·휴대폰 여백) ---------- */
  function sizeActionbar() {
    var ab = $('.actionbar'); if (!ab) return;
    root.style.setProperty('--actionbar-h', Math.ceil(ab.getBoundingClientRect().height) + 'px');
  }
  if (window.ResizeObserver && $('.actionbar')) new ResizeObserver(sizeActionbar).observe($('.actionbar'));
  window.addEventListener('resize', sizeActionbar);
  sizeActionbar();

  /* ---------- 탭 ---------- */
  function selectTab(tab) {
    var list = tab.parentNode;
    $$('[role=tab]', list).forEach(function (t) {
      var on = t === tab; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1;
      var p = doc.getElementById(t.getAttribute('aria-controls')); if (p) p.hidden = !on;
    });
  }
  $$('[role=tablist]').forEach(function (list) {
    $$('[role=tab]', list).forEach(function (t, i, all) {
      t.addEventListener('click', function () {
        selectTab(t);
        if (t.id === 'tab-contra') { var b = $('.tab-badge', t); if (b) b.classList.remove('is-new'); }
      });
      t.addEventListener('keydown', function (e) {
        var n = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0; if (!n) return;
        var next = all[(i + n + all.length) % all.length]; next.focus(); selectTab(next); e.preventDefault();
      });
    });
  });

  /* ---------- 충분도 (가짜 데이터) ---------- */
  var gauge = $('[data-gauge]');
  if (gauge) {
    [['한소라', 1], ['남궁철', 1], ['고태식', 2], ['추성만', 2], ['서도윤', 1], ['윤석진', 0], ['황지호', 0]].forEach(function (r) {
      var row = doc.createElement('div'); row.className = 'gauge-row';
      var cells = ''; for (var i = 0; i < 5; i++) cells += '<i class="' + (i < r[1] ? 'on' : '') + '"></i>';
      row.innerHTML = '<span>' + r[0] + '</span><span class="cells" aria-hidden="true">' + cells + '</span><span class="mono">' + r[1] + '/5</span>';
      gauge.appendChild(row);
    });
  }

  /* ---------- 이전 문답: 휴대폰은 접어 둔다 ---------- */
  function syncEarlier() { var d = $('#earlier'); if (d) d.open = !mq('(max-width: 720px)'); }
  syncEarlier();

  /* ---------- 행동 점 ---------- */
  var ap = { now: 10, total: 12 };
  function renderAp() {
    $$('.pips').forEach(function (p) {
      p.innerHTML = ''; for (var i = 0; i < ap.total; i++) { var s = doc.createElement('span'); s.className = 'pip' + (i < ap.now ? ' on' : ''); p.appendChild(s); }
    });
    $$('[data-ap-now]').forEach(function (e) { e.textContent = ap.now; });
  }
  renderAp();
  MockUI.spendAp = function (n) { ap.now = Math.max(0, ap.now - (n || 1)); renderAp(); };
  MockUI.setAp = function (now, total) { ap.now = now; if (total) ap.total = total; renderAp(); };

  /* ---------- 표정 크로스페이드 ---------- */
  var LABEL = { neutral: '평온', nervous: '긴장', flustered: '당황', angry: '분노', sad: '슬픔', happy: '기쁨' };
  var portrait = $('[data-portrait]'), curEmotion = 'neutral';
  function setEmotion(e) {
    if (!portrait || e === curEmotion) return;
    var base = portrait.getAttribute('data-portrait-base');
    var imgs = $$('img', portrait), front = $('img.is-front', portrait), back = imgs.filter(function (i) { return i !== front; })[0];
    var url = base + (e === 'neutral' ? '' : '--' + e) + '.webp';
    function swap() { back.classList.add('is-front'); if (front) front.classList.remove('is-front'); front && front.setAttribute('alt', ''); back.setAttribute('alt', portrait.getAttribute('data-portrait-alt') || ''); }
    back.onload = swap; back.src = url; if (back.complete && back.naturalWidth) swap();
    curEmotion = e;
    $$('[data-emotion-label]').forEach(function (l) { l.textContent = LABEL[e]; });
    $$('[data-emotion]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-emotion') === e)); });
    MockUI.say('표정: ' + LABEL[e]);
  }
  $$('[data-emotion]').forEach(function (b) { b.addEventListener('click', function () { setEmotion(b.getAttribute('data-emotion')); }); });
  var awayBtn = $('#demo-away');
  if (awayBtn && portrait) awayBtn.addEventListener('click', function () { portrait.classList.toggle('is-away'); });

  /* ---------- 증거 선택 · 제시 ---------- */
  var selected = null, NAMES = {};
  $$('.nb-body [data-evidence]').forEach(function (c) { NAMES[c.getAttribute('data-evidence')] = $('strong', c).textContent; });
  var pickerList = $('[data-picker-list]');
  if (pickerList) {
    $$('.nb-body [data-evidence]').forEach(function (c) { var k = c.cloneNode(true); pickerList.appendChild(k); });
  }
  function renderSelection() {
    $$('[data-evidence]').forEach(function (c) {
      var on = c.getAttribute('data-evidence') === selected; c.classList.toggle('selected', on); c.setAttribute('aria-pressed', String(on));
    });
    $$('[data-pending]').forEach(function (p) { p.hidden = !selected; });
    $$('[data-pending-name]').forEach(function (n) { n.textContent = selected ? NAMES[selected] : ''; });
    var r = $('[data-present-reason]'); if (r) { r.hidden = !selected; r.textContent = selected ? '고른 증거: ' + NAMES[selected] : ''; }
    var cp = $('#confirm-present');
    if (cp) {
      cp.setAttribute('aria-disabled', String(!selected));
      var rs = $('.btn-reason', cp); if (rs) { rs.textContent = selected ? NAMES[selected] : '증거를 고르세요'; }
    }
    sizeActionbar();
  }
  $$('[data-evidence]').forEach(function (c) {
    c.addEventListener('click', function () { var id = c.getAttribute('data-evidence'); selected = selected === id ? null : id; renderSelection(); });
  });
  renderSelection();

  var picker = $('#evidence-picker'), presentBtn = $('#present-btn');
  function placeNear(pop, trigger, mode) {
    if (mq('(max-width: 720px)')) { pop.style.top = pop.style.left = pop.style.right = pop.style.bottom = ''; return; }
    var r = trigger.getBoundingClientRect();
    if (mode === 'above') {
      pop.style.top = 'auto'; pop.style.bottom = Math.round(window.innerHeight - r.top + 8) + 'px';
      pop.style.left = 'auto'; pop.style.right = Math.max(16, Math.round(window.innerWidth - r.right)) + 'px';
    } else {
      pop.style.bottom = 'auto'; pop.style.top = Math.round(r.bottom + 8) + 'px';
      pop.style.left = 'auto'; pop.style.right = Math.max(16, Math.round(window.innerWidth - r.right)) + 'px';
    }
  }
  if (picker && presentBtn) {
    picker.addEventListener('beforetoggle', function (e) { if (e.newState === 'open') placeNear(picker, presentBtn, 'above'); });
    picker.addEventListener('toggle', function (e) {
      if (e.newState === 'open') { var f = $('.selected', picker) || $('.evidence-card', picker); if (f) f.focus(); }
    });
  }
  [['#menu-pop', '.menu-btn'], ['#demo-pop', '[popovertarget=demo-pop]']].forEach(function (pair) {
    var pop = $(pair[0]), trg = $(pair[1]); if (!pop || !trg) return;
    pop.addEventListener('beforetoggle', function (e) { if (e.newState === 'open') { placeNear(pop, trg, 'below'); if (pair[0] === '#menu-pop') { var fc = $('#final-confirm'); if (fc) fc.hidden = true; } } });
  });
  var finalOpen = $('#final-open');
  if (finalOpen) finalOpen.addEventListener('click', function () {
    var fc = $('#final-confirm'); fc.hidden = !fc.hidden; finalOpen.setAttribute('aria-expanded', String(!fc.hidden));
  });

  function think(ms, done) {
    $$('[data-thinking]').forEach(function (t) { t.hidden = false; });
    setTimeout(function () { $$('[data-thinking]').forEach(function (t) { t.hidden = true; }); if (done) done(); }, ms || 900);
  }
  function spendAp() { if (ap.now > 0) { ap.now -= 1; renderAp(); } }
  var cp2 = $('#confirm-present');
  if (cp2) cp2.addEventListener('click', function () {
    if (cp2.getAttribute('aria-disabled') === 'true') return;
    var name = NAMES[selected]; picker.hidePopover();
    selected = null; renderSelection(); spendAp(); think(900, function () { setEmotion('flustered'); });
    MockUI.toast({ text: '한소라에게 "' + name + '"을(를) 제시했다.' });
  });

  /* ---------- 질문 입력 ---------- */
  var input = $('#ask-input'), askBtn = $('#ask-btn'), askForm = $('#ask-form');
  function syncAsk() {
    var ok = input && input.value.trim().length > 0;
    askBtn.setAttribute('aria-disabled', String(!ok));
    var rs = $('.btn-reason', askBtn); if (rs) rs.hidden = ok;
  }
  if (input && askBtn) {
    input.addEventListener('input', syncAsk); syncAsk();
    $$('[data-ask]').forEach(function (c) { c.addEventListener('click', function () { input.value = c.getAttribute('data-ask'); syncAsk(); input.focus(); }); });
    askForm.addEventListener('submit', function (e) {
      e.preventDefault(); if (askBtn.getAttribute('aria-disabled') === 'true') return;
      input.value = ''; syncAsk(); spendAp(); think(1000);
    });
  }

  /* ---------- 모순 발견 연출: 형광 띠 300ms -> 탭 뱃지 +1 -> 토스트 (탭은 강제로 바꾸지 않는다) ---------- */
  var claim = $('#claim'), contraDone = false;
  function bumpContra(n) { $$('[data-contra-count]').forEach(function (b) { b.textContent = n; }); }
  function clearContra() {
    contraDone = false; if (claim) claim.classList.remove('is-flagged');
    var st = $('#st-now'); if (st) st.classList.remove('contra');
    var nc = $('[data-contra="new"]'); if (nc) { nc.hidden = true; nc.classList.remove('is-fresh'); }
    bumpContra(1); var tb = $('#tab-contra .tab-badge'); if (tb) tb.classList.remove('is-new');
  }
  /* 기본 상태에서 모순이 이미 표시된 화면(data-default-flagged): 연출 없이 결과 상태로 */
  function setContraInitial() {
    if (!claim || !claim.hasAttribute('data-default-flagged')) return;
    contraDone = true; claim.classList.add('is-flagged');
    var st = $('#st-now'); if (st) st.classList.add('contra');
    var nc = $('[data-contra="new"]'); if (nc) nc.hidden = false;
    bumpContra(2); var tb = $('#tab-contra .tab-badge'); if (tb) tb.classList.add('is-new');
  }
  setContraInitial();
  function runContradiction() {
    if (!claim || contraDone) return; contraDone = true;
    claim.classList.add('is-flagged');
    var st = $('#st-now'); if (st) st.classList.add('contra');
    var delay = reduced() ? 0 : 300;
    setTimeout(function () {
      var nc = $('[data-contra="new"]'); if (nc) { nc.hidden = false; nc.classList.add('is-fresh'); }
      bumpContra(2);
      var tb = $('#tab-contra .tab-badge'); if (tb) tb.classList.add('is-new');
      MockUI.say('한소라의 진술이 서버실 출입카드 기록과 어긋납니다.');
      MockUI.toast({
        text: '수첩에 모순이 기록됐다.',
        action: { label: '보기', run: function () { var go = function () { selectTab($('#tab-contra')); $('#tab-contra .tab-badge').classList.remove('is-new'); }; if (mq('(max-width: 720px)')) { openD('note', $('[data-open="note"]')); } go(); } }
      });
    }, delay);
  }
  var dc = $('#demo-contra'); if (dc) dc.addEventListener('click', function () { var p = $('#demo-pop'); if (p && p.hidePopover) p.hidePopover(); clearContra(); setTimeout(runContradiction, 120); });

  var rs = $('#demo-reset');
  if (rs) rs.addEventListener('click', function () {
    clearContra(); setContraInitial();
    selected = null; renderSelection(); ap.now = 10; renderAp(); setEmotion('neutral');
    if (portrait) portrait.classList.remove('is-away');
    $$('#toasts .toast').forEach(function (t) { t.remove(); });
  });

  /* ---------- 하루 끝내기 (가짜) ---------- */
  ['#end-day', '#end-day-menu'].forEach(function (s) {
    var b = $(s); if (b) b.addEventListener('click', function () {
      var p = $('#menu-pop'); if (p && p.matches(':popover-open')) p.hidePopover();
      MockUI.toast({ text: '밤이 지나 2일차 아침이 된다. (목업: 실제 전환 없음)' });
    });
  });

  /* ---------- 표준 메뉴: 수사 · 증거 보드 · 최종 추리 · 정보 · 처음으로 (현재 화면은 뺀다) ---------- */
  var sm = $('#menu-pop[data-standard-menu]');
  if (sm) {
    var cur = sm.getAttribute('data-current');
    var items = [['investigate', 'map-trifold', '수사', 'investigate.html'], ['notebook', 'notebook', '증거 보드', 'notebook.html'],
      ['finale', 'seal-check', '최종 추리', 'finale.html', '되돌릴 수 없음'], ['about', 'info', '정보 · 사진 출처', 'about.html'], ['start', 'arrow-left', '처음으로', 'start.html']];
    var hr = doc.createElement('hr'); hr.className = 'menu-sep'; if (sm.children.length) sm.appendChild(hr);
    items.forEach(function (it) {
      if (it[0] === cur) return;
      var a = doc.createElement('a'); a.className = 'btn btn-quiet'; a.href = it[3];
      a.innerHTML = '<span class="btn-label"><i data-icon="' + it[1] + '"></i>' + it[2] + '</span>' + (it[4] ? '<small>' + it[4] + '</small>' : '');
      sm.appendChild(a);
    });
    if (window.renderIcons) window.renderIcons(sm);
  }
})();
