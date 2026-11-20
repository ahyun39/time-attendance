// 화면 전환과 실행 가이드 (가이드는 ① 구성원, ② 인사팀 화면에만).
// 각 단계는 눌러야 할 요소(find)와 완료 조건(done)을 가진다. 조건이 맞으면 다음 단계로 넘어간다.
(function () {
  const SCREENS = {
    main: 'screens/Main.dc.html',
    hr: 'screens/HR.dc.html',
    overview: 'screens/Overview.dc.html',
    eval: 'screens/Eval.dc.html'
  };

  const root = () => document.getElementById('screen');
  const buttons = (scope) => Array.from((scope || root()).querySelectorAll('button'));
  const btn = (text, exact) => buttons().find((b) => {
    const t = b.textContent.replace(/\s+/g, ' ').trim();
    return exact ? t === text : t.startsWith(text);
  });
  const tab = (id) => document.querySelector('.tab[data-screen="' + id + '"]');
  const sectionOf = (heading) => {
    const h = Array.from(root().querySelectorAll('h2')).find((x) => x.textContent.trim() === heading);
    return h && h.closest('section');
  };

  const STEPS = {
    main: [
      { title: '부족한 시간 확인', text: '11/13 출퇴근 기록과 휴가 신청이 모두 없어서 8시간이 부족하다고 알려줘요. 휴가 신청을 깜빡한 상황이라 생각하고 눌러보세요.', find: () => btn('휴가 상신 누락'), done: (s) => s.leaveOpen },
      { title: '휴가 종류 고르기', text: '종류마다 인정되는 시간과 차감되는 연차가 달라요. 연차를 골라보세요.', find: () => buttons().find((b) => b.firstElementChild && b.firstElementChild.textContent.trim() === '연차'), done: (s) => s.leaveType },
      { title: '휴가 상신', text: '상신하면 승인 전이라도 예상치로 근로시간을 다시 계산해요.', find: () => btn('상신하기', true), done: (s) => s.resolved === 'leave' },
      { title: '바뀐 숫자 확인', text: '이번 달 근로시간이 120시간으로 채워지고, 11/9–11/13 주 막대가 초록색으로 바뀌고, 연차는 승인 대기 1일을 포함해 10일 남음으로 바뀌었어요.', find: () => sectionOf('이번 달 근로시간'), manual: true },
      { title: '되돌리기', text: '되돌린 뒤 근태 정정 요청을 눌러 다른 처리 방법도 볼 수 있어요.', find: () => btn('되돌리기', true), done: (s) => !s.resolved },
      { title: '계산 근거 보기', text: '근태 관리 봇은 시간을 규칙으로 계산하고, 계산 과정을 펼쳐서 보여줘요.', find: () => btn('계산 근거'), done: (s) => s.basisOpen },
      { title: '담당자에게 넘어간 질문', text: '규정만으로 답할 수 없는 질문은 인사팀 담당자에게 넘어가요. 담당자 답변이 도착한 상황을 재현해 보세요.', find: () => btn('인사팀 답변 도착'), done: (s) => s.answered },
      { title: '다음 행동 실행', text: '답변에 맞춰 필요한 사후 승인 요청을 바로 보낼 수 있어요.', find: () => btn('사후 승인 요청하기'), done: (s) => s.requested },
      { title: '직접 질문하기', text: '질문을 입력하고 보내보세요. 연차, 휴가, 반차가 들어간 질문은 규칙으로 계산해 답하고, 그 외 질문은 담당자에게 넘겨요.', find: () => { const i = root().querySelector('input[type="text"]'); return i && (i.closest('label') || i); }, done: (s) => (s.msgs || []).length > 0 },
      { title: '인사팀 화면으로', text: '구성원 화면은 여기까지예요. 인사팀 담당자 화면으로 넘어가 보세요.', find: () => tab('hr'), goto: 'hr' }
    ],
    hr: [
      { title: '유형 카드로 거르기', text: '카드를 누르면 표가 해당 유형만 보이도록 걸러지고 처리 기한이 나와요.', find: () => btn('연장근로 한도 근접'), done: (s) => s.filter === 'cap' },
      { title: '리더에게 알림', text: '정산기간 누적으로 보면 연장근로 한도에 가까워진 구성원이에요. 리더에게 알려보세요.', find: () => btn('리더에게 알림', true), done: (s) => s.done && s.done['윤OO'] },
      { title: '근태 기록 불일치', text: '불일치는 휴가 취소 기록을 먼저 찾아보고, 기록이 없는 사람만 표에 남겨요.', find: () => btn('근태 기록 불일치'), done: (s) => s.filter === 'mismatch' },
      { title: '자동 확인된 건', text: '취소 기록이 있어서 사람이 볼 필요 없이 자동으로 확인된 건이에요.', find: () => btn('연차 취소 기록으로 자동 확인'), done: (s) => s.autoOpen },
      { title: '전체 보기', text: '필터를 풀고 전체 목록으로 돌아가요.', find: () => btn('전체 보기', true), done: (s) => !s.filter },
      { title: '한 번에 안내하기', text: '안내 전인 구성원에게 한 번에 보내기 전에 대상과 인원을 먼저 보여줘요.', find: () => btn('안내 전 상태 모두에게 보내기'), done: (s) => s.bulkOpen },
      { title: '안내 보내기', text: '대상을 확인했으면 보내기를 눌러보세요. 표의 상태가 안내 완료로 바뀌어요.', find: () => buttons().find((b) => b.textContent.trim() === '보내기' && b.parentNode && /닫기/.test(b.parentNode.textContent)), done: (s) => !s.bulkOpen },
      { title: '담당자 답변이 필요한 문의', text: '규정만으로 판단하기 어려워 에이전트가 넘긴 질문이에요. 답변하기를 눌러보세요.', find: () => btn('답변하기', true), done: (s) => Object.values(s.editing || {}).some(Boolean) },
      { title: '답변 보내기', text: '답변을 적고 보내기를 누르면 구성원의 봇 대화로 전달되고, FAQ 후보로 저장돼요.', find: () => { const t = root().querySelector('textarea'); return t && t.closest('label') && t.closest('label').parentNode; }, done: (s) => Object.values(s.answered || {}).some(Boolean) },
      { title: '자동 안내 확인', text: '예약된 자동 안내는 보내기 전에 문구를 확인하고, 필요하면 이번 발송을 취소할 수 있어요.', find: () => btn('안내 문구 확인'), done: (s) => s.previewOpen },
      { title: '설계 설명 보기', text: '실행 가이드는 여기까지예요. 규칙, LLM, 사람의 역할 분담은 ③ 설계 설명에서, Solar Pro 응답 평가는 ④ 문의 응답 평가에서 볼 수 있어요.', find: () => tab('overview'), manual: true, last: true }
    ]
  };
  // 가이드와 화면 맞춤(창 높이에 맞게 축소)은 실행 화면인 ①, ②에만 적용한다
  const GUIDED = new Set(['main', 'hr']);
  const guided = () => GUIDED.has(screen);

  const ring = document.getElementById('ring');
  const badge = document.getElementById('badge');
  const panel = document.getElementById('panel');
  const el = (id) => document.getElementById(id);

  let screen = 'main';
  let comp = null;
  let stepIdx = { main: 0, hr: 0 };
  let guideOn = true;
  let lastTarget = null;

  const steps = () => STEPS[screen];
  const step = () => (guided() ? steps()[stepIdx[screen]] : null);
  const toggle = el('guideToggle');

  // ①, ②는 화면 전체가 창 안에 들어오도록 축소 (최소 60%), ③, ④는 설명 화면이라 살짝만 축소 (넓은 화면에서만)
  const DOC_ZOOM = 0.85;
  function fit() {
    const s = root();
    s.style.zoom = '';
    if (window.innerWidth < 900) return;
    if (!guided()) { s.style.zoom = String(DOC_ZOOM); return; }
    const top = document.querySelector('.topbar').getBoundingClientRect().height;
    const z = Math.max(0.6, Math.min(1, (window.innerHeight - top - 8) / s.scrollHeight));
    if (z < 1) s.style.zoom = String(Math.floor(z * 1000) / 1000);
  }

  function check() {
    if (!comp) return;
    if (!guided()) { paint(); return; }
    const st = step();
    if (st && st.done && st.done(comp.state || {})) {
      if (stepIdx[screen] < steps().length - 1) { stepIdx[screen]++; lastTarget = null; }
    }
    paint();
  }

  function paint() {
    toggle.hidden = !guided();
    if (!guided()) { panel.hidden = ring.hidden = badge.hidden = true; lastTarget = null; return; }
    panel.hidden = !guideOn;
    const list = steps();
    const i = stepIdx[screen];
    const st = list[i];
    el('pStep').textContent = '실행 가이드 ' + (i + 1) + ' / ' + list.length;
    el('pTitle').textContent = st.title;
    el('pText').textContent = st.text;
    const target = guideOn ? st.find() : null;
    el('pHint').textContent = !target && guideOn
      ? '지금 화면에서 이 단계를 찾을 수 없어요. 화면 처음부터를 누르면 다시 시작해요.'
      : st.manual ? '확인했으면 다음을 눌러주세요.' : st.goto ? '표시된 탭을 눌러주세요.' : '주황색으로 표시된 곳을 눌러주세요.';
    el('pDots').innerHTML = list.map((_, k) => '<span class="dot ' + (k < i ? 'done' : k === i ? 'now' : '') + '"></span>').join('');
    el('pPrev').disabled = i === 0;
    el('pNext').disabled = !!st.last && i === list.length - 1;
    el('pNext').textContent = st.goto ? '건너뛰기' : '다음';
    if (target && target !== lastTarget) {
      lastTarget = target;
      const r = target.getBoundingClientRect();
      if (r.top < 80 || r.bottom > window.innerHeight - 40) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    ring.hidden = badge.hidden = !target;
    position(target, i + 1);
  }

  function position(target, n) {
    if (!target) return;
    const r = target.getBoundingClientRect();
    const pad = 6;
    Object.assign(ring.style, { top: r.top - pad + 'px', left: r.left - pad + 'px', width: r.width + pad * 2 + 'px', height: r.height + pad * 2 + 'px' });
    badge.textContent = n;
    Object.assign(badge.style, { top: Math.max(4, r.top - pad - 14) + 'px', left: Math.max(4, r.left - pad - 14) + 'px' });
  }

  (function follow() {
    if (guided() && guideOn && lastTarget && document.contains(lastTarget)) position(lastTarget, stepIdx[screen] + 1);
    else if (guided() && guideOn && lastTarget) paint();
    requestAnimationFrame(follow);
  })();

  async function show(id, reset) {
    screen = id;
    document.querySelectorAll('.tab').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.screen === id)));
    if (reset && guided()) stepIdx[id] = 0;
    lastTarget = null;
    root().style.zoom = '';
    root().innerHTML = '<div class="loading">화면을 불러오는 중이에요.</div>';
    comp = null;
    comp = await DCLite.mount(SCREENS[id], root(), () => setTimeout(check, 0));
    window.scrollTo(0, 0);
    fit();
    check();
  }

  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => {
    const cur = step();
    if (cur && cur.goto === t.dataset.screen) stepIdx[screen] = steps().length - 1;
    show(t.dataset.screen, false);
  }));
  el('pNext').addEventListener('click', () => {
    const st = step();
    if (!st) return;
    if (st.goto) { show(st.goto, false); return; }
    if (stepIdx[screen] < steps().length - 1) { stepIdx[screen]++; lastTarget = null; paint(); }
  });
  el('pPrev').addEventListener('click', () => { if (stepIdx[screen] > 0) { stepIdx[screen]--; lastTarget = null; paint(); } });
  el('pReset').addEventListener('click', () => show(screen, true));
  const setGuide = (on) => {
    guideOn = on;
    toggle.setAttribute('aria-checked', String(on));
    lastTarget = null;
    paint();
  };
  el('pClose').addEventListener('click', () => setGuide(false));
  toggle.addEventListener('click', () => setGuide(!guideOn));
  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { fit(); lastTarget = null; paint(); }, 120);
  });

  show('main', true);
})();
