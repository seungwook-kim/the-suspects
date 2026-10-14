/* 최종 추리 목업 동작. 클래식 스크립트. 지목 -> 기회·수단·동기 증거 끼우기(틀리면 기회 감소) -> 결과 카드 미리보기.
   정답은 인물과 상관없는 고정 예시(기회=서버실 출입카드 기록, 수단=콘솔 로그인 기록, 동기=감사 로그 공백). 데이터는 전부 가짜. */
(function () {
  'use strict';
  var doc = document;
  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  /* 이름순(가나다) */
  var SUSPECTS = [
    { id: 'go', name: '고태식', role: 'DBA', photo: 'p3' },
    { id: 'nam', name: '남궁철', role: '야간 경비원', photo: 'p2' },
    { id: 'do', name: '서도윤', role: '신입 개발자', photo: null },
    { id: 'yun', name: '윤석진', role: '시니어 백엔드 개발자', photo: null },
    { id: 'chu', name: '추성만', role: '야간 청소원', photo: 'p5' },
    { id: 'sora', name: '한소라', role: '프로덕트 매니저', photo: 'p1' },
    { id: 'hwang', name: '황지호', role: '외주 개발자', photo: null }
  ];
  var EVN = { audit: '감사 로그 30분 공백', card: '서버실 출입카드 기록', console: '서버실 콘솔 로그인 기록', 'cctv-b1': '지하 1층 CCTV: 추성만의 이동', checklist: '청소 점검표의 빈 칸', 'cctv-hall': '복도 CCTV: 카드 전달 장면' };
  var REASON = {
    audit: '30분의 공백은 DB가 언제 지워졌는지 말해 줄 뿐, 누가 그 자리에 있었는지는 보여 주지 못한다.',
    card: '출입카드 기록은 들어갔다는 사실만 보여 준다. 무엇을 할 수 있었는지는 말해 주지 않는다.',
    console: '공용 계정으로 로그인해서 누가 로그인했는지 이 기록만으로는 알 수 없다.',
    'cctv-b1': '이 영상은 복도를 지나간 사람을 보여 줄 뿐, 서버실 안에서 한 일과 이어지지 않는다.',
    checklist: '점검표는 서명이 비었다는 사실뿐이라 누가 서버실 근처에 있었는지 보여 주지 못한다.',
    'cctv-hall': '얼굴이 보이지 않아 누구의 행동인지 확정할 수 없다.'
  };
  var CORRECT = ['card', 'console', 'audit'];
  var SLOT = ['기회', '수단', '동기'];

  var st = null;
  function fresh() { return { stage: 'pick', accused: null, lives: 3, slot: 0, placed: [null, null, null], sel: null, wrong: [{}, {}, {}], verdict: null, ended: null }; }
  st = fresh();
  function sus(id) { return SUSPECTS.filter(function (s) { return s.id === id; })[0]; }

  function photoHtml(s, alt) {
    return s.photo
      ? '<img src="../assets/portraits/' + s.photo + '.webp" alt="' + esc(alt ? s.name + ', AI로 생성한 가상의 인물 사진' : '') + '" width="480" height="640">'
      : '<div class="avatar-pending" role="img" aria-label="' + esc(s.name) + ', 사진 준비 중"><span class="ap-initial">' + esc(s.name.charAt(0)) + '</span><span class="ap-label">사진 준비 중</span></div>';
  }

  /* ---------- 1단계 격자 ---------- */
  var list = $('[data-suspects]');
  SUSPECTS.forEach(function (s) {
    var li = doc.createElement('li'), b = doc.createElement('button');
    b.type = 'button'; b.className = 'person is-tile'; b.setAttribute('data-id', s.id); b.setAttribute('aria-pressed', 'false');
    b.innerHTML = '<span class="person-photo">' + photoHtml(s, true) + '</span>' +
      '<span class="person-name">' + esc(s.name) + '</span><span class="person-role">' + esc(s.role) + '</span>' +
      '<span class="sel-label"><i data-icon="paperclip-fill"></i>지목 대기</span>';
    b.addEventListener('click', function () { st.accused = st.accused === s.id ? null : s.id; render(); });
    li.appendChild(b); list.appendChild(li);
  });
  if (window.renderIcons) window.renderIcons(list);

  /* ---------- 렌더 ---------- */
  var bar = $('[data-bar]'), go = $('[data-bar-go]'), back = $('[data-bar-back]');
  function setGo(label, reason, off) {
    $('[data-bar-label]').textContent = label;
    var r = $('[data-bar-reason]'); r.textContent = reason; r.hidden = !reason;
    go.setAttribute('aria-disabled', String(!!off));
  }
  function render() {
    $$('[data-stage]').forEach(function (s) { s.hidden = s.getAttribute('data-stage') !== st.stage; });
    var jump = st.stage === 'build' && st.verdict && st.verdict.kind === 'wrong' && st.slot === 0 && st.lives === 2 && st.demoWrong ? 'wrong' : st.stage;
    $$('[data-jump]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-jump') === jump)); });
    bar.hidden = st.stage === 'result';
    var sb = $('[data-strip-back]'); if (sb) sb.hidden = st.stage !== 'pick';

    if (st.stage === 'pick') {
      $$('.person.is-tile').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-id') === st.accused)); });
      back.hidden = false;
      $('[data-bar-note]').textContent = '지목하면 되돌릴 수 없습니다. 틀릴 수 있는 기회는 3번입니다.';
      setGo('이 사람을 지목한다', st.accused ? sus(st.accused).name + ' 지목' : '한 명을 고르세요', !st.accused);
    }
    if (st.stage === 'build') { renderBuild(); }
    if (st.stage === 'result') { renderResult(); }
    if (window.renderIcons) window.renderIcons(doc);
  }

  function renderBuild() {
    var a = sus(st.accused);
    $('[data-accused-name]').textContent = a.name; $('[data-accused-role]').textContent = a.role;
    $('[data-accused-photo]').innerHTML = photoHtml(a, true); $('[data-accused-photo]').className = 'df-photo';
    $('[data-lives]').textContent = st.lives;
    $$('i', $('[data-lives-cells]')).forEach(function (c, i) { c.className = i < st.lives ? 'on' : ''; });
    $('[data-lives-cells]').setAttribute('aria-label', '남은 기회 ' + st.lives + '번');

    $$('[data-slot]').forEach(function (li, i) {
      var box = $('.slot-box', li), cls = 'slot';
      if (st.placed[i]) {
        cls += ' is-filled';
        box.innerHTML = '<i data-icon="seal-check-fill"></i><span><b>확인됨</b> · ' + esc(EVN[st.placed[i]]) + '</span>';
      } else if (i === st.slot && !st.ended) {
        cls += ' is-now';
        box.innerHTML = '<i data-icon="paperclip"></i><span><b>지금 밝히는 칸</b> · 증거 목록에서 고르세요</span>';
      } else {
        cls += ' is-wait';
        box.innerHTML = '<span>' + (st.ended ? '밝히지 못함' : '앞 칸을 먼저 밝혀야 합니다') + '</span>';
      }
      li.className = cls;
      if (i === st.slot && !st.ended) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    });

    var used = {}; st.placed.forEach(function (p, i) { if (p) used[p] = i; });
    $$('.ev-panel [data-ev]').forEach(function (c) {
      var id = c.getAttribute('data-ev'), tag = $('[data-ev-tag]', c), off = false, t = '';
      if (id in used) { off = true; t = '사용함 · ' + SLOT[used[id]]; }
      else if (st.slot < 3 && st.wrong[st.slot][id]) { off = true; t = SLOT[st.slot] + ' 칸에는 맞지 않음'; }
      else if (st.ended || st.slot >= 3) { off = true; }
      c.setAttribute('aria-disabled', String(off));
      tag.textContent = t; tag.hidden = !t;
      var on = st.sel === id && !off; c.classList.toggle('selected', on); c.setAttribute('aria-pressed', String(on));
    });

    var v = $('[data-verdict]');
    if (st.verdict) {
      v.hidden = false; v.className = 'verdict ' + st.verdict.kind;
      v.innerHTML = st.verdict.html;
    } else { v.hidden = true; v.innerHTML = ''; }

    back.hidden = true;
    var help = $('[data-ev-help]');
    if (st.ended === 'lose') {
      help.textContent = '기회를 모두 썼습니다.';
      $('[data-bar-note]').textContent = '이번 추리는 실패했습니다. 결과 카드는 만들어집니다.';
      setGo('결과 보기', '', false);
    } else if (st.slot >= 3) {
      help.textContent = '세 칸을 모두 밝혔습니다.';
      $('[data-bar-note]').textContent = '확정하면 결과 카드가 만들어지고 되돌릴 수 없습니다.';
      setGo('추리 확정', '', false);
    } else {
      help.textContent = SLOT[st.slot] + ['를','을','를'][st.slot] + ' 밝힐 증거를 고르세요.';
      $('[data-bar-note]').textContent = '증거를 고른 뒤 "제시"를 누르면 판정합니다.';
      setGo('이 증거를 ' + SLOT[st.slot] + '에 제시', st.sel ? EVN[st.sel] : '증거를 고르세요', !st.sel);
    }
  }

  function renderResult() {
    var a = sus(st.accused), win = st.ended !== 'lose';
    $('[data-res-title]').textContent = win ? '사건 해결' : '사건 미해결';
    $('[data-res-stamp]').textContent = win ? '사건 종결' : '추리 실패';
    $('[data-res-name]').textContent = a.name; $('[data-res-role]').textContent = a.role;
    var ph = $('[data-res-photo]'); ph.innerHTML = photoHtml(a, true); ph.className = 'df-photo';
    $('[data-res-meta]').textContent = '기회 3번 중 ' + st.lives + '번 남음 · 1일차 · 행동 2번';
    $('[data-res-basis]').innerHTML = SLOT.map(function (n, i) {
      return '<li><span class="slot-label">' + n + '</span><span>' + (st.placed[i] ? esc(EVN[st.placed[i]]) : '밝히지 못함') + '</span></li>';
    }).join('');
  }

  /* ---------- 동작 ---------- */
  $$('.ev-panel [data-ev]').forEach(function (c) {
    c.addEventListener('click', function () {
      if (c.getAttribute('aria-disabled') === 'true') return;
      var id = c.getAttribute('data-ev'); st.sel = st.sel === id ? null : id; render();
    });
  });

  function present() {
    var id = st.sel, i = st.slot; if (!id) return;
    var n = SLOT[i];
    if (id === CORRECT[i]) {
      st.placed[i] = id; st.slot++; st.sel = null;
      st.verdict = { kind: 'ok', html: '<p class="v-line"><i data-icon="check-circle"></i><b>맞다</b> · ' + n + ' 칸이 채워졌다.' + (st.slot < 3 ? ' 다음은 ' + SLOT[st.slot] + '.' : ' 세 칸을 모두 밝혔다.') + '</p>' };
    } else {
      st.lives--; st.wrong[i][id] = true; st.sel = null;
      var line = '<p class="v-line"><i data-icon="warning-circle"></i><b>증거가 맞지 않는다</b> · 기회가 1번 줄었다 (3번 중 ' + st.lives + '번 남음)</p>' +
        '<p class="v-reason">이유: ' + esc(REASON[id]) + '</p>';
      if (st.lives <= 0) { st.ended = 'lose'; line += '<p class="v-reason"><b>기회를 모두 썼다.</b></p>'; }
      st.verdict = { kind: 'wrong', html: line };
    }
    if (window.MockUI) window.MockUI.say($('[data-verdict]').textContent || '');
    render();
  }
  go.addEventListener('click', function () {
    if (go.getAttribute('aria-disabled') === 'true') return;
    if (st.stage === 'pick') { st.stage = 'build'; st.verdict = null; render(); window.scrollTo(0, 0); return; }
    if (st.stage === 'build') {
      if (st.ended === 'lose' || st.slot >= 3) { st.stage = 'result'; render(); window.scrollTo(0, 0); }
      else present();
    }
  });

  /* ---------- 목업 도구줄: 단계 바로 보기 ---------- */
  function jump(to) {
    var acc = st.accused || 'sora';
    st = fresh(); st.accused = acc;
    if (to === 'pick') { st.accused = null; }
    if (to === 'build' || to === 'wrong') { st.stage = 'build'; }
    if (to === 'wrong') { st.sel = 'checklist'; st.demoWrong = true; present(); }
    if (to === 'result') { st.stage = 'result'; st.placed = CORRECT.slice(); st.slot = 3; st.lives = 2; }
    render(); window.scrollTo(0, 0);
  }
  $$('[data-jump]').forEach(function (b) { b.addEventListener('click', function () { jump(b.getAttribute('data-jump')); }); });

  /* 미리보기: 넓은 화면은 항상 펼치고, 휴대폰은 접어 둔다 */
  var prev = $('[data-prev]'), mqWide = window.matchMedia('(min-width: 721px)');
  function syncPrev() { if (prev) prev.open = mqWide.matches; }
  mqWide.addEventListener('change', syncPrev); syncPrev();

  render();
})();
