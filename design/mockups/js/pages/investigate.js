/* 수사(장소) 화면 목업 동작. 클래식 스크립트(file:// 에서 동작). 공통 동작은 js/mock.js, 여기는 지도·장소 카드만.
   가짜 데이터: 시연 사건 "사라진 운영 DB" 8곳. 행동 수는 MockUI.spendAp 로 공통 값을 고친다. */
(function () {
  'use strict';
  var doc = document;
  function $(s, r) { return (r || doc).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || doc).querySelectorAll(s)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  /* 장소: col 1~3, row 0~5 (지도 칸 위치). 층 글자는 지도 왼쪽 줄에 쓴다. */
  var FLOORS = ['옥상', '3층', '2층', '1층', '지하 1층', '지하 2층'];
  var P = {
    roof:   { name: '옥상 휴게 공간', short: '옥상 휴게 공간', floor: '옥상', col: 3, row: 0, visited: false, done: false, people: [],
              desc: '벤치와 자판기가 있는 옥상. 밤에는 아무도 오지 않는다.', tags: [] },
    dev:    { name: '개발팀 사무실', short: '개발팀 사무실', floor: '3층', col: 1, row: 1, visited: true, done: false,
              desc: '모니터 불빛이 남은 개방형 사무실. 오픈 전날 밤까지 사람이 있었다.', tags: ['야간 조명 일부 꺼짐'],
              people: [['한소라', '프로덕트 매니저', 'p1'], ['서도윤', '신입 개발자', null], ['윤석진', '시니어 백엔드 개발자', null]] },
    pantry: { name: '탕비실', short: '탕비실', floor: '3층', col: 3, row: 1, visited: true, done: true,
              desc: '커피머신과 냉장고가 있는 작은 공간. 야식 포장이 쌓여 있다.', tags: [],
              people: [['황지호', '외주 개발자', null]] },
    meet:   { name: '회의실', short: '회의실', floor: '2층', col: 3, row: 2, visited: false, done: false, people: [],
              desc: '유리벽 회의실. 화이트보드에 지우다 만 글씨가 남아 있다.', tags: [] },
    lobby:  { name: '로비 · 보안데스크', short: '로비 · 보안데스크', floor: '1층', col: 1, row: 3, visited: true, done: true,
              desc: '출입 게이트와 CCTV 모니터가 있는 1층 로비.', tags: ['CCTV 확인함'],
              people: [['남궁철', '야간 경비원', 'p2']] },
    server: { name: '서버실', short: '서버실', floor: '지하 1층', col: 1, row: 4, visited: false, done: false, people: [],
              desc: '냉각 팬 소리가 가득한 서버실. 출입 카드가 있어야 들어간다.', tags: [] },
    hall:   { name: '복도 · 청소용품실', short: '복도 · 청소용품실', floor: '지하 1층', col: 3, row: 4, visited: false, done: false, people: [],
              desc: '청소 카트와 점검표가 걸린 지하 복도. 서버실과 주차장으로 이어진다.', tags: [] },
    park:   { name: '지하 주차장', short: '지하 주차장', floor: '지하 2층', col: 3, row: 5, visited: false, done: false, people: [],
              desc: '기둥이 늘어선 주차장. 출입구는 복도 쪽 한 곳뿐이다.', tags: [] }
  };
  var EDGES = [['dev', 'pantry'], ['dev', 'meet'], ['dev', 'lobby'], ['pantry', 'roof'], ['lobby', 'hall'], ['hall', 'server'], ['hall', 'park']];
  var PHOTO = { p1: '../assets/portraits/p1.webp', p2: '../assets/portraits/p2.webp' };

  var here = 'dev', picked = 'dev', ap = 10;
  function linked(a, b) { return EDGES.some(function (e) { return (e[0] === a && e[1] === b) || (e[0] === b && e[1] === a); }); }
  function stateOf(id) { return id === here ? 'here' : linked(here, id) ? 'link' : 'far'; }
  var STATE_TEXT = { here: '현재 위치', link: '지금 갈 수 있음', far: '경유 필요' };

  /* ---------- 지도 ---------- */
  var board = $('[data-map]'), lines = $('[data-map-lines]');
  function buildMap() {
    FLOORS.forEach(function (f, i) {
      var l = doc.createElement('span'); l.className = 'floor-label'; l.textContent = f; l.style.gridRow = String(i + 1); board.appendChild(l);
    });
    Object.keys(P).forEach(function (id) {
      var p = P[id], b = doc.createElement('button');
      b.type = 'button'; b.className = 'room'; b.setAttribute('data-room', id);
      b.style.gridColumn = String(p.col + 1); b.style.gridRow = String(p.row + 1);
      b.addEventListener('click', function () { pick(id); });
      board.appendChild(b);
    });
  }
  function roomSub(id) {
    var p = P[id], st = stateOf(id);
    var s1 = st === 'here' ? '현재 위치' : st === 'link' ? '갈 수 있음' : '경유 필요';
    var s2 = p.visited ? (p.people.length ? p.people.length + '명' : '아무도 없음') : '미방문';
    return '<span class="s">' + s1 + '</span><span class="v"> · ' + s2 + '</span>';
  }
  function renderMap() {
    $$('[data-room]').forEach(function (b) {
      var id = b.getAttribute('data-room'), st = stateOf(id), p = P[id];
      b.className = 'room is-' + st + (id === picked ? ' is-picked' : '');
      b.setAttribute('aria-pressed', String(id === picked));
      b.innerHTML = '<span class="room-name">' + (st === 'here' ? '<i data-icon="map-trifold"></i>' : '') + esc(p.short) + '</span><span class="room-sub">' + roomSub(id) + '</span>';
      if (window.renderIcons) window.renderIcons(b);
    });
    var out = '';
    EDGES.forEach(function (e) {
      var a = P[e[0]], b = P[e[1]], on = e[0] === here || e[1] === here;
      var x1 = (a.col - 0.5) / 3 * 100, y1 = (a.row + 0.5) / 6 * 100, x2 = (b.col - 0.5) / 3 * 100, y2 = (b.row + 0.5) / 6 * 100;
      out += '<line class="' + (on ? 'on' : '') + '" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '"/>';
    });
    lines.innerHTML = out;
  }

  /* ---------- 장소 칩 (휴대폰) ---------- */
  var chipsUl = $('[data-place-chips]');
  function renderChips() {
    chipsUl.innerHTML = '';
    Object.keys(P).filter(function (id) { return stateOf(id) !== 'far'; }).forEach(function (id) {
      var li = doc.createElement('li'), b = doc.createElement('button');
      b.type = 'button'; b.className = 'chip place-chip'; b.setAttribute('aria-pressed', String(id === picked));
      b.textContent = P[id].floor + ' ' + P[id].short + (id === here ? ' (현재)' : '');
      b.addEventListener('click', function () { pick(id); });
      li.appendChild(b); chipsUl.appendChild(li);
    });
  }

  /* ---------- 장소 카드 ---------- */
  var card = $('[data-place-card]');
  function peopleHtml(p) {
    if (!p.visited) return '<p class="people-empty">아직 가 보지 않아 누가 있는지 모른다.</p>';
    if (!p.people.length) return '<p class="people-empty">이곳에는 아무도 없다.</p>';
    return '<ul class="people">' + p.people.map(function (m) {
      var thumb = m[2]
        ? '<img src="' + PHOTO[m[2]] + '" alt="' + esc(m[0]) + ', AI로 생성한 가상의 인물 사진" width="96" height="128">'
        : '<div class="avatar-pending" role="img" aria-label="' + esc(m[0]) + ', 사진 준비 중"><span class="ap-initial">' + esc(m[0].charAt(0)) + '</span><span class="ap-label">사진 준비 중</span></div>';
      return '<li><a class="person" href="interrogation.html" style="--photo-w:96px"><span class="person-photo">' + thumb + '</span>' +
        '<span class="person-name">' + esc(m[0]) + '</span><span class="person-role">' + esc(m[1]) + '</span></a></li>';
    }).join('') + '</ul>';
  }
  function primaryOf(id) {
    var p = P[id], st = stateOf(id);
    if (st === 'here') {
      if (ap <= 0) return { label: '현장 조사', icon: 'notebook', reason: '행동이 없음', off: true };
      if (p.done) return { label: '현장 조사', icon: 'notebook', reason: '이미 조사함', off: true };
      return { label: '현장 조사', icon: 'notebook', reason: '행동 1번 씀', off: false, run: 'investigate' };
    }
    if (st === 'link') {
      if (ap <= 0) return { label: '이동하기', icon: 'map-trifold', reason: '행동이 없음', off: true };
      return { label: '이동하기', icon: 'map-trifold', reason: '행동 1번 씀', off: false, run: 'move' };
    }
    return { label: '이동하기', icon: 'map-trifold', reason: '다른 장소를 거쳐야 함', off: true };
  }
  function route(id) {
    if (id === 'server' || id === 'park') return '지하 복도를 거쳐 가야 한다. 로비 → 지하 1층 복도 → ' + (id === 'server' ? '서버실' : '주차장') + ' 순서.';
    if (id === 'hall') return '1층 로비를 거쳐 가야 한다.';
    if (id === 'roof') return '3층 탕비실을 거쳐 가야 한다.';
    return '';
  }
  function renderCard() {
    var p = P[picked], st = stateOf(picked), pr = primaryOf(picked);
    card.innerHTML =
      '<span class="folder-tab">사건 01</span>' +
      '<div class="pc-head"><h2 id="place-name">' + esc(p.name) + '</h2>' +
      '<p class="pc-state"><span class="kind">' + esc(p.floor) + '</span><span class="state-tag is-' + st + '">' + STATE_TEXT[st] + '</span>' +
      (p.done ? '<span class="state-tag">조사 완료</span>' : '') + '</p></div>' +
      '<p class="pc-desc">' + esc(p.desc) + '</p>' +
      (p.tags.length ? '<p class="pc-tags">' + p.tags.map(function (t) { return '<span class="kind">' + esc(t) + '</span>'; }).join('') + '</p>' : '') +
      (st === 'far' ? '<p class="pc-route"><i data-icon="warning-circle"></i><span>' + esc(route(picked)) + '</span></p>' : '') +
      '<div class="pc-act"><button type="button" class="btn btn-cta pc-primary" ' + (pr.off ? 'aria-disabled="true"' : '') + ' data-primary>' +
      '<span class="btn-label"><i data-icon="' + pr.icon + '"></i>' + esc(pr.label) + '</span><small class="btn-reason">' + esc(pr.reason) + '</small></button></div>' +
      '<section class="pc-people" aria-label="이 장소에 있는 사람"><h3>이 장소에 있는 사람</h3>' + peopleHtml(p) + '</section>';
    if (window.renderIcons) window.renderIcons(card);
    syncPrimary(pr);
  }
  function syncPrimary(pr) {
    var bar = $('.actionbar [data-primary]');
    if (bar) {
      $('.btn-label', bar).innerHTML = '<i data-icon="' + pr.icon + '"></i>' + esc(pr.label);
      $('.btn-reason', bar).textContent = pr.reason;
      bar.setAttribute('aria-disabled', String(pr.off));
      if (window.renderIcons) window.renderIcons(bar);
    }
  }
  function primaryAction() {
    var pr = primaryOf(picked); if (pr.off) return;
    if (pr.run === 'investigate') {
      P[picked].done = true; spend();
      toast('현장을 조사했다. 단서가 될 만한 것은 이번에는 없었다. (목업)');
    } else if (pr.run === 'move') {
      here = picked; P[here].visited = true; spend();
      toast(P[here].name + '으로 이동했다. 행동 1번을 썼다.');
    }
    render();
  }
  function spend() {
    ap = Math.max(0, ap - 1);
    if (window.MockUI && window.MockUI.spendAp) window.MockUI.spendAp(1);
  }
  function toast(t) { if (window.MockUI) { window.MockUI.toast({ text: t }); window.MockUI.say(t); } }
  function pick(id) { picked = id; render(); }
  function render() { renderMap(); renderChips(); renderCard(); }

  doc.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-primary]') : null;
    if (b) primaryAction();
  });

  buildMap(); render();
})();
