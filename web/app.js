/* 小说写作助手 — 原生 JS + setState/render + template */

// ── State ───────────────────────────────────────
const state = {
  mode: 'write',
  sidebar: 'codex',
  currentChapter: null,
  currentSceneId: null,
  editTarget: null,
  chapters: [],
  writingProvider: 'kie',
};

const dataCache = {
  chapters: [],
  planByNum: {},
  codex: { entries: [], active: [] },
};

const API_TIMEOUT_MS = 120000;
const STREAM_FIRST_BYTE_MS = 90000;
const STREAM_CHUNK_IDLE_MS = 180000;
const RENDER_DEBOUNCE_MS = 16;
let _isSending = false;
let _planSortable = null;
let _autosaveTimer = null;
let _renderTimer = null;
let _renderOpts = { chrome: false, main: false, sidebar: false };

const GLOBAL_LABELS = {
  world: '世界观 world.md',
  characters: '人物总表 characters.md',
  char_current: '当前状态',
  summaries: '章节概述',
  plot_threads: '伏笔线索',
};

const SIDEBAR_CONFIG = {
  plan: [{ id: 'scenes', label: '场景' }],
  write: [
    { id: 'codex', label: '设定库' },
    { id: 'chats', label: '写书记录' },
    { id: 'global', label: '全局文件' },
  ],
  chat: [
    { id: 'chats', label: '写书记录' },
    { id: 'codex', label: '设定库' },
  ],
  free: [{ id: 'freechats', label: '聊天记录' }],
};

// ── setState / render ───────────────────────────
function setState(patch, renderHint = 'auto') {
  Object.assign(state, patch);
  scheduleRender(renderHint);
}

function scheduleRender(hint) {
  if (hint === 'none') return;
  if (hint === 'auto' || hint === 'full') {
    _renderOpts = { chrome: true, main: true, sidebar: true };
  } else if (hint === 'chrome') {
    _renderOpts.chrome = true;
  } else if (hint === 'main') {
    _renderOpts.main = true;
  } else if (hint === 'sidebar') {
    _renderOpts.sidebar = true;
  } else if (typeof hint === 'object') {
    Object.assign(_renderOpts, hint);
  }
  if (_renderTimer) clearTimeout(_renderTimer);
  _renderTimer = setTimeout(() => {
    _renderTimer = null;
    flushRender();
  }, RENDER_DEBOUNCE_MS);
}

async function flushRender() {
  const opts = _renderOpts;
  _renderOpts = { chrome: false, main: false, sidebar: false };

  if (opts.chrome) applyChrome();
  if (opts.main) await renderMainView();
  if (opts.sidebarPartial) {
    applySidebarPartial(opts.sidebarPartial);
  } else if (opts.sidebar) {
    await refreshSidebarFull();
  }
  if (opts.planPartial) applyPlanPartial(opts.planPartial);
  if ('highlightScene' in opts) highlightActiveScene(opts.highlightScene);
}

function applyChrome() {
  const { mode, sidebar } = state;
  document.querySelectorAll('.mode-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.mode === mode));
  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  const viewId = 'view' + mode.charAt(0).toUpperCase() + mode.slice(1);
  document.getElementById(viewId)?.classList.remove('hidden');
  document.getElementById('sidebar')?.classList.toggle('hidden', mode === 'review');

  const tabs = SIDEBAR_CONFIG[mode] || SIDEBAR_CONFIG.write;
  let nextSidebar = sidebar;
  if (mode === 'free') nextSidebar = 'freechats';
  else if (!tabs.find(t => t.id === sidebar)) nextSidebar = tabs[0].id;
  if (nextSidebar !== sidebar) state.sidebar = nextSidebar;

  renderSidebarTabs(tabs);
  updateSidebarAddBtn();
  updateWordCount();
  updateChatHints();
}

async function renderMainView() {
  switch (state.mode) {
    case 'plan':
      await renderPlanBoardFull();
      break;
    case 'write':
      await renderWriteView();
      break;
    case 'chat':
      await loadChat(false);
      break;
    case 'free':
      await loadFreeChat();
      break;
    case 'review':
      await renderReview();
      break;
  }
}

// ── Template helpers ────────────────────────────
function cloneTpl(id) {
  const tpl = document.getElementById(id);
  return tpl ? tpl.content.cloneNode(true) : null;
}

function cloneTplEl(id) {
  const tpl = document.getElementById(id);
  if (!tpl) throw new Error(`模板 #${id} 不存在，请检查 index.html`);
  const el = tpl.content.cloneNode(true).firstElementChild;
  if (!el) throw new Error(`模板 #${id} 内容为空`);
  return el;
}

function clearEl(el) {
  if (el) el.replaceChildren();
}

function fillSelect(sel, chapters, planByNum) {
  clearEl(sel);
  for (const c of chapters) {
    const opt = document.createElement('option');
    opt.value = String(c.num);
    const title = planByNum[c.num]?.title;
    opt.textContent =
      title && title !== `第${c.num}章` ? `第${c.num}章 · ${title}` : `第${c.num}章`;
    sel.appendChild(opt);
  }
}

// ── Data cache ──────────────────────────────────
async function ensurePlanData(force = false) {
  if (force || !dataCache.chapters.length) {
    const [{ chapters }, { chapters: planChapters }] = await Promise.all([
      api('/chapters'),
      api('/plan/full'),
    ]);
    dataCache.chapters = chapters;
    dataCache.planByNum = Object.fromEntries(planChapters.map(p => [p.num, p]));
    state.chapters = chapters;
  }
  return dataCache;
}

function invalidateCache(keys = ['all']) {
  const all = keys.includes('all');
  if (all || keys.includes('plan')) {
    dataCache.chapters = [];
    dataCache.planByNum = {};
  }
  if (all || keys.includes('codex')) {
    dataCache.codex = { entries: [], active: [] };
  }
}

function invalidatePlanCache() {
  invalidateCache(['plan']);
}

function invalidateCodexCache() {
  invalidateCache(['codex']);
}

function patchSceneInCache(sceneId, patch) {
  for (const ch of Object.values(dataCache.planByNum)) {
    const scene = ch.scenes?.find(s => s.id === sceneId);
    if (scene) Object.assign(scene, patch);
  }
}

function getSceneFromCache(sceneId) {
  for (const [num, ch] of Object.entries(dataCache.planByNum)) {
    const scene = ch.scenes?.find(s => s.id === sceneId);
    if (scene) return { scene, chapterNum: parseInt(num, 10) };
  }
  return null;
}

// ── API / UI utils ──────────────────────────────
function beginSending(btnId, loadingText = '处理中…') {
  if (_isSending) {
    toast('请等待当前请求完成');
    return null;
  }
  _isSending = true;
  const btn = btnId ? document.getElementById(btnId) : null;
  const defaultText = btn?.textContent || '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = loadingText;
  }
  return { btn, defaultText };
}

function endSending(session) {
  _isSending = false;
  if (!session) return;
  const { btn, defaultText } = session;
  if (btn) {
    btn.disabled = false;
    btn.textContent = defaultText;
  }
}

async function api(path, opts = {}, timeoutMs = API_TIMEOUT_MS) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const userSignal = opts.signal;
  if (userSignal?.aborted) {
    controller.abort();
  } else if (userSignal) {
    userSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }
  const { signal: _ignored, ...fetchOpts } = opts;
  try {
    const r = await fetch('/api' + path, {
      headers: { 'Content-Type': 'application/json' },
      ...fetchOpts,
      signal: controller.signal,
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || data.error || r.statusText);
    return data;
  } catch (e) {
    if (e.name === 'AbortError') {
      // 用户取消（userSignal）与超时（timedOut）分开提示
      if (!timedOut && (userSignal?.aborted || e.message?.includes('aborted'))) {
        const err = new Error('请求已取消');
        err.cancelled = true;
        throw err;
      }
      throw new Error('请求超时，请检查网络或稍后重试');
    }
    if (e instanceof TypeError) {
      throw new Error('无法连接到服务，请确认后端已启动（python web_app.py）');
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function runWithLoading(fn, { btnId, loadingText = '处理中…' } = {}) {
  if (_isSending) {
    toast('请等待当前请求完成');
    return null;
  }
  _isSending = true;
  const btn = btnId ? document.getElementById(btnId) : null;
  const defaultText = btn?.textContent || '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = loadingText;
  }
  try {
    return await fn();
  } finally {
    _isSending = false;
    if (btn) {
      btn.disabled = false;
      btn.textContent = defaultText;
    }
  }
}

function toast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.display = 'none'; }, 2800);
}

function countChars(text) {
  return (text || '').replace(/\s/g, '').length;
}

function updateWordCount() {
  const ed = document.getElementById('mainEditor');
  const pill = document.getElementById('wordCountPill');
  if (!pill) return;
  if (state.mode === 'write' && ed && !ed.classList.contains('hidden')) {
    pill.textContent = `${countChars(ed.value).toLocaleString()} 字`;
    pill.classList.remove('hidden');
  } else if (state.mode !== 'write') {
    pill.classList.add('hidden');
  }
}

function configLabel(p) {
  return p === 'kie' ? 'Claude' : 'DeepSeek';
}

function updateFreeProviderHint(provider) {
  const hint = document.getElementById('freeProviderHint');
  if (hint) hint.textContent = `${configLabel(provider)} · 纯对话，无系统提示词`;
}

function updateApiKeyBanner(s) {
  const el = document.getElementById('apiKeyBanner');
  if (!el) return;
  el.classList.toggle('hidden', !!s.api_key_ok);
}

function updateChatHints() {
  const hint = document.getElementById('chatSceneHint');
  if (!hint) return;
  hint.textContent = state.currentSceneId
    ? `当前场景已选中 · 第${state.currentChapter}章`
    : '建议先在 Plan 选中场景';
}

function highlightActiveScene(sceneId) {
  document.querySelectorAll('[data-scene-id]').forEach(el => {
    el.classList.toggle('active', el.dataset.sceneId === sceneId);
  });
  document.querySelectorAll('.scene-card[data-id]').forEach(el => {
    el.classList.toggle('active', el.dataset.id === sceneId);
  });
  document.getElementById('planBeatPanel')?.classList.toggle('hidden', !sceneId);
}

// ── Mode / sidebar chrome ───────────────────────
function setMode(mode) {
  setState({ mode }, 'full');
}

function renderSidebarTabs(tabs) {
  const host = document.getElementById('sidebarTabs');
  clearEl(host);
  for (const t of tabs) {
    const el = cloneTplEl('tpl-sidebar-tab');
    el.textContent = t.label;
    el.classList.toggle('active', state.sidebar === t.id);
    el.addEventListener('click', () => setSidebar(t.id));
    host.appendChild(el);
  }
}

function setSidebar(tab) {
  setState({ sidebar: tab }, { chrome: true, sidebar: true });
}

function updateSidebarAddBtn() {
  const btn = document.getElementById('sidebarAddBtn');
  const labels = { scenes: '场景', codex: '条目', chats: '', global: '', plan: '场景' };
  const key = state.sidebar;
  if (key === 'chats' || key === 'global') {
    btn.style.display = 'none';
    return;
  }
  btn.style.display = 'block';
  btn.textContent = '+';
  btn.title = '新建' + (labels[key] || '');
}

function sidebarAdd() {
  if (state.sidebar === 'codex') createCodexEntry();
  else if (state.sidebar === 'scenes') addScene(state.currentChapter || 1);
}

function toggleSettings() {
  document.getElementById('settingsDrawer').classList.toggle('hidden');
  document.getElementById('overlay').classList.toggle('hidden');
}

// ── Sidebar: full + partial ─────────────────────
async function refreshSidebarFull() {
  const body = document.getElementById('sidebarBody');
  const q = (document.getElementById('sidebarSearch').value || '').toLowerCase();
  if (state.sidebar === 'scenes') await renderScenesSidebar(body, q);
  else if (state.sidebar === 'codex') await renderCodexSidebar(body, q);
  else if (state.sidebar === 'chats') await renderChatsSidebar(body);
  else if (state.sidebar === 'freechats') await renderFreeChatsSidebar(body);
  else if (state.sidebar === 'global') renderGlobalSidebar(body);
}

function applySidebarPartial({ type, sceneId, patch }) {
  if (type === 'scene') updateSceneSidebarItem(sceneId, patch);
}

function makeSceneSidebarItem(scene, chapterNum) {
  const el = cloneTplEl('tpl-scene-sidebar-item');
  el.dataset.sceneId = scene.id;
  el.classList.toggle('active', state.currentSceneId === scene.id);
  el.querySelector('.title').textContent = `${scene.done ? '✓ ' : ''}${scene.title}`;
  el.querySelector('.meta').textContent = (scene.beat || '').slice(0, 60) || '无 beat';
  el.addEventListener('click', () => selectScene(scene.id, chapterNum));
  return el;
}

function updateSceneSidebarItem(sceneId, patch) {
  const el = document.querySelector(`[data-scene-id="${sceneId}"]`);
  if (!el) return;
  if (patch.title != null || patch.done != null) {
    const found = getSceneFromCache(sceneId);
    const title = patch.title ?? found?.scene?.title ?? '';
    const done = patch.done ?? found?.scene?.done ?? false;
    el.querySelector('.title').textContent = `${done ? '✓ ' : ''}${title}`;
  }
  if (patch.beat != null) {
    el.querySelector('.meta').textContent = patch.beat.slice(0, 60) || '无 beat';
  }
  if (patch.active != null) el.classList.toggle('active', patch.active);
}

async function renderScenesSidebar(body, q) {
  await ensurePlanData();
  clearEl(body);
  const { chapters, planByNum } = dataCache;
  let hasItems = false;

  for (const ch of chapters) {
    const plan = planByNum[ch.num] || { scenes: [] };
    const scenes = (plan.scenes || []).filter(s =>
      !q || s.title.toLowerCase().includes(q) || (s.beat || '').toLowerCase().includes(q));
    if (!scenes.length && q) continue;

    const section = document.createElement('div');
    section.dataset.chapterSection = String(ch.num);
    const label = cloneTplEl('tpl-chapter-label');
    label.textContent = `第${ch.num}章`;
    section.appendChild(label);

    const list = document.createElement('div');
    list.className = 'chapter-scenes';
    for (const s of scenes) list.appendChild(makeSceneSidebarItem(s, ch.num));
    section.appendChild(list);
    body.appendChild(section);
    if (scenes.length) hasItems = true;
  }

  if (!hasItems && !chapters.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.innerHTML = '暂无场景<br>';
    const btn = document.createElement('button');
    btn.className = 'btn btn-sm';
    btn.style.marginTop = '8px';
    btn.textContent = '新建章节';
    btn.addEventListener('click', newChapter);
    empty.appendChild(btn);
    body.appendChild(empty);
  } else if (!hasItems) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.textContent = '无匹配场景';
    body.appendChild(empty);
  }
}

async function refreshChapterScenesInSidebar(chapterNum) {
  if (state.sidebar !== 'scenes') return;
  await ensurePlanData();
  const body = document.getElementById('sidebarBody');
  let section = body.querySelector(`[data-chapter-section="${chapterNum}"]`);
  const q = (document.getElementById('sidebarSearch').value || '').toLowerCase();
  const plan = dataCache.planByNum[chapterNum] || { scenes: [] };
  const scenes = (plan.scenes || []).filter(s =>
    !q || s.title.toLowerCase().includes(q) || (s.beat || '').toLowerCase().includes(q));

  if (!section) {
    await refreshSidebarFull();
    return;
  }
  const list = section.querySelector('.chapter-scenes') || section;
  if (list.classList.contains('chapter-scenes')) clearEl(list);
  for (const s of scenes) list.appendChild(makeSceneSidebarItem(s, chapterNum));
}

function makeCodexSidebarItem(entry, active) {
  const el = cloneTplEl('tpl-codex-sidebar-item');
  const cb = el.querySelector('input');
  cb.checked = active.includes(entry.id);
  cb.addEventListener('change', () => toggleCodex(entry.id, cb.checked));
  el.querySelector('.title').textContent = entry.name;
  el.querySelector('.meta').textContent = entry.preview || '';
  el.querySelector('.codex-check-body').addEventListener('click', () => openCodexEntry(entry.id));
  return el;
}

async function renderCodexSidebar(body, q) {
  const { entries, active } = await api('/codex-entries');
  dataCache.codex = { entries, active };
  clearEl(body);
  const filtered = entries.filter(e => !q || e.name.toLowerCase().includes(q));
  if (!filtered.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.innerHTML = 'Codex 存放人物、地点、规则<br>写作时勾选即注入 AI 上下文';
    body.appendChild(empty);
    return;
  }
  for (const e of filtered) body.appendChild(makeCodexSidebarItem(e, active));
}

function makeSidebarHistoryItem(role, index, preview, onClick) {
  const el = cloneTplEl('tpl-sidebar-list-item');
  el.querySelector('.title').textContent = `${role} #${index + 1}`;
  el.querySelector('.meta').textContent = preview;
  el.addEventListener('click', onClick);
  return el;
}

async function renderChatsSidebar(body) {
  const { messages } = await api('/chat/history');
  clearEl(body);
  if (!messages.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.innerHTML = '写书对话为空<br>在「写书对话」模式发送指令';
    body.appendChild(empty);
    return;
  }
  messages.forEach((m, i) => {
    const role = m.role === 'user' ? '你' : 'AI';
    body.appendChild(makeSidebarHistoryItem(role, i, (m.content || '').slice(0, 80), () => setMode('chat')));
  });
}

async function renderFreeChatsSidebar(body) {
  const { messages } = await api('/free-chat/history');
  clearEl(body);
  if (!messages.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.textContent = '自由聊为空';
    body.appendChild(empty);
    return;
  }
  messages.forEach((m, i) => {
    const role = m.role === 'user' ? '你' : 'AI';
    body.appendChild(makeSidebarHistoryItem(role, i, (m.content || '').slice(0, 80), () => setMode('free')));
  });
}

function renderGlobalSidebar(body) {
  clearEl(body);
  for (const [k, label] of Object.entries(GLOBAL_LABELS)) {
    const el = cloneTplEl('tpl-global-item');
    el.dataset.globalKey = k;
    el.textContent = label;
    el.addEventListener('click', () => openGlobal(k));
    body.appendChild(el);
  }
}

// ── Plan board ──────────────────────────────────
function makeSceneCard(scene, chapterNum) {
  const el = cloneTplEl('tpl-scene-card');
  el.dataset.id = scene.id;
  el.classList.toggle('active', state.currentSceneId === scene.id);
  const cb = el.querySelector('input[type=checkbox]');
  cb.checked = !!scene.done;
  cb.addEventListener('click', e => e.stopPropagation());
  cb.addEventListener('change', () => toggleSceneDone(scene.id, cb.checked));
  el.querySelector('.scene-card-title').textContent = scene.title;
  el.querySelector('.scene-card-beat').textContent = scene.beat || '点击添加 Scene Beat…';
  el.querySelector('.tag').textContent = `第${chapterNum}章 · 场景 · 可拖拽排序`;
  el.addEventListener('click', () => selectScene(scene.id, chapterNum));
  return el;
}

function applyPlanPartial({ sceneId, patch }) {
  updatePlanSceneCard(sceneId, patch);
  patchSceneInCache(sceneId, patch);
}

function updatePlanSceneCard(sceneId, patch) {
  const el = document.querySelector(`.scene-card[data-id="${sceneId}"]`);
  if (!el) return;
  if (patch.done != null) el.querySelector('input[type=checkbox]').checked = patch.done;
  if (patch.title != null) el.querySelector('.scene-card-title').textContent = patch.title;
  if (patch.beat != null) {
    el.querySelector('.scene-card-beat').textContent = patch.beat || '点击添加 Scene Beat…';
  }
  if (patch.active != null) el.classList.toggle('active', patch.active);
}

function showPlanEmpty(board, message, btnText, onClick) {
  clearEl(board);
  const empty = cloneTplEl('tpl-nc-empty');
  empty.querySelector('p').textContent = message;
  const btn = document.createElement('button');
  btn.className = 'btn btn-primary btn-lg';
  btn.textContent = btnText;
  btn.addEventListener('click', onClick);
  empty.querySelector('.nc-empty-box').appendChild(btn);
  board.appendChild(empty);
}

async function renderPlanBoardFull() {
  await ensurePlanData();
  const { chapters, planByNum } = dataCache;
  const sel = document.getElementById('planChapterSel');
  fillSelect(sel, chapters, planByNum);

  const board = document.getElementById('planBoard');
  const beatPanel = document.getElementById('planBeatPanel');

  if (!chapters.length) {
    showPlanEmpty(board, '还没有场景。先创建章节，再添加 Scene Beat 规划每一个场景。', '+ 创建第一章', newChapter);
    beatPanel.classList.add('hidden');
    destroyPlanSortable();
    return;
  }

  const num = state.currentChapter || chapters[chapters.length - 1].num;
  state.currentChapter = num;
  sel.value = String(num);
  const plan = planByNum[num] || (await api(`/plan/${num}`));
  const scenes = plan.scenes || [];

  if (!scenes.length) {
    showPlanEmpty(
      board,
      `第${num}章还没有场景。写一个 Scene Beat，再交给 Chat 生成正文。`,
      '+ 创建第一个场景',
      () => addScene(num),
    );
    beatPanel.classList.add('hidden');
    destroyPlanSortable();
    return;
  }

  clearEl(board);
  const list = document.createElement('div');
  list.id = 'planSceneList';
  list.className = 'plan-scene-list';
  for (const s of scenes) list.appendChild(makeSceneCard(s, num));
  board.appendChild(list);

  const addCard = cloneTplEl('tpl-scene-add-card');
  addCard.addEventListener('click', () => addScene(num));
  board.appendChild(addCard);

  initPlanSortable(num);
  beatPanel.classList.toggle('hidden', !state.currentSceneId);
  highlightActiveScene(state.currentSceneId);
}

function destroyPlanSortable() {
  if (_planSortable) {
    _planSortable.destroy();
    _planSortable = null;
  }
}

function initPlanSortable(chapterNum) {
  const list = document.getElementById('planSceneList');
  if (!list || typeof Sortable === 'undefined') return;
  destroyPlanSortable();
  _planSortable = Sortable.create(list, {
    animation: 150,
    draggable: '.scene-card:not(.no-sort)',
    filter: '.no-sort',
    ghostClass: 'dragging',
    onEnd: async () => {
      const ids = [...list.querySelectorAll('.scene-card[data-id]')].map(el => el.dataset.id);
      await api(`/plan/${chapterNum}/reorder`, {
        method: 'PUT',
        body: JSON.stringify({ scene_ids: ids }),
      });
      const plan = dataCache.planByNum[chapterNum];
      if (plan?.scenes) {
        const map = Object.fromEntries(plan.scenes.map(s => [s.id, s]));
        plan.scenes = ids.map(id => map[id]).filter(Boolean);
      }
      toast('场景顺序已更新');
      if (state.sidebar === 'scenes') await refreshChapterScenesInSidebar(chapterNum);
    },
  });
}

async function toggleSceneDone(sceneId, done) {
  await api(`/plan/scenes/${sceneId}`, { method: 'PUT', body: JSON.stringify({ done }) });
  scheduleRender({
    planPartial: { sceneId, patch: { done } },
    sidebarPartial: state.sidebar === 'scenes' ? { type: 'scene', sceneId, patch: { done } } : null,
  });
}

async function renameChapter() {
  const num = state.currentChapter;
  if (!num) return toast('请先选择章节');
  const plan = await api(`/plan/${num}`);
  const newTitle = prompt('章节标题', plan.title || `第${num}章`);
  if (newTitle === null) return;
  const title = newTitle.trim();
  if (!title) return toast('标题不能为空');
  await api(`/plan/${num}/title`, { method: 'PUT', body: JSON.stringify({ title }) });
  invalidatePlanCache();
  scheduleRender({ main: true, sidebar: state.sidebar === 'scenes' });
  toast('章节标题已更新');
}

async function selectScene(sceneId, chapterNum) {
  if (!sceneId) {
    setState({ currentSceneId: null, currentChapter: chapterNum }, {
      chrome: true,
      highlightScene: null,
    });
    return;
  }

  await api(`/plan/active/${sceneId}`, { method: 'PUT' });
  await ensurePlanData();
  const plan = dataCache.planByNum[chapterNum] || (await api(`/plan/${chapterNum}`));
  const scene = plan.scenes?.find(s => s.id === sceneId);

  setState(
    { currentSceneId: scene ? sceneId : null, currentChapter: chapterNum },
    'none',
  );

  if (scene) {
    document.getElementById('beatEditor').value = scene.beat || '';
    document.getElementById('planSceneTitle').textContent = scene.title;
  }

  scheduleRender({
    chrome: true,
    highlightScene: scene ? sceneId : null,
  });
}

async function addScene(chapterNum) {
  if (!chapterNum) { toast('请先创建章节'); return; }
  const title = prompt('场景标题', '新场景')?.trim();
  if (!title) return;
  const r = await api('/plan/scenes', { method: 'POST', body: JSON.stringify({ chapter_num: chapterNum, title }) });
  invalidatePlanCache();
  await ensurePlanData();
  await selectScene(r.scene.id, chapterNum);
  scheduleRender({ main: state.mode === 'plan', sidebar: state.sidebar === 'scenes' });
  toast('场景已创建');
}

async function saveBeat() {
  if (!state.currentSceneId) return;
  const beat = document.getElementById('beatEditor').value;
  await api(`/plan/scenes/${state.currentSceneId}`, { method: 'PUT', body: JSON.stringify({ beat }) });
  scheduleRender({
    planPartial: { sceneId: state.currentSceneId, patch: { beat } },
    sidebarPartial: state.sidebar === 'scenes'
      ? { type: 'scene', sceneId: state.currentSceneId, patch: { beat } }
      : null,
  });
  toast('Beat 已保存');
}

function onPlanChapterChange() {
  setState(
    {
      currentChapter: parseInt(document.getElementById('planChapterSel').value, 10),
      currentSceneId: null,
    },
    { chrome: true, main: true },
  );
}

// ── Write ──────────────────────────────────────
async function renderWriteView() {
  await ensurePlanData();
  const { chapters, planByNum } = dataCache;
  const sel = document.getElementById('writeChapterSel');
  const empty = document.getElementById('writeEmpty');
  const editor = document.getElementById('mainEditor');

  if (!chapters.length) {
    clearEl(sel);
    empty.classList.remove('hidden');
    editor.classList.add('hidden');
    return;
  }

  empty.classList.add('hidden');
  editor.classList.remove('hidden');
  fillSelect(sel, chapters, planByNum);
  const num = state.currentChapter || chapters[chapters.length - 1].num;
  await openChapter(num);
}

async function flushAutosave() {
  clearTimeout(_autosaveTimer);
  _autosaveTimer = null;
  if (!state.editTarget) return;
  await saveEditor({ silent: true });
}

async function openChapter(num) {
  const switching = state.editTarget?.type !== 'chapter' || state.editTarget?.num !== num;
  if (switching && state.editTarget) await flushAutosave();
  const ch = await api(`/chapters/${num}`);
  setState(
    { currentChapter: num, editTarget: { type: 'chapter', num } },
    'none',
  );
  document.getElementById('mainTitle').textContent = `第${num}章 正文`;
  document.getElementById('mainEditor').value = ch.content;
  document.getElementById('writeChapterSel').value = num;
  updateWordCount();
}

function onWriteChapterChange() {
  openChapter(parseInt(document.getElementById('writeChapterSel').value, 10));
}

function scheduleAutosave() {
  updateWordCount();
  if (!state.editTarget) return;
  clearTimeout(_autosaveTimer);
  _autosaveTimer = setTimeout(() => saveEditor({ silent: true }), 2000);
}

async function saveEditor({ silent = false } = {}) {
  const t = state.editTarget;
  const content = document.getElementById('mainEditor').value;
  if (!t) return toast('请先选择章节或设定');
  const titleEl = document.getElementById('mainTitle');
  try {
    if (t.type === 'chapter') {
      await api(`/chapters/${t.num}`, { method: 'PUT', body: JSON.stringify({ content }) });
      if (silent) {
        document.getElementById('wordCountPill')?.classList.add('saved-flash');
        setTimeout(() => document.getElementById('wordCountPill')?.classList.remove('saved-flash'), 1200);
      } else {
        toast(`第${t.num}章已保存`);
      }
      if (titleEl) titleEl.textContent = `第${t.num}章 正文`;
    } else if (t.type === 'codex-entry') {
      await api(`/codex-entries/${t.id}`, { method: 'PUT', body: JSON.stringify({ content }) });
      toast(silent ? 'Codex 已自动保存' : 'Codex 已保存');
      invalidateCodexCache();
    } else if (t.type === 'global') {
      await api(`/codex/${t.name}`, { method: 'PUT', body: JSON.stringify({ content }) });
      toast(silent ? '设定已自动保存' : '设定已保存');
    }
  } catch (e) {
    if (t.type === 'chapter' && titleEl) titleEl.textContent = `第${t.num}章 ⚠️ 保存失败`;
    if (!silent) toast(e.message || '保存失败');
  }
}

async function newChapter() {
  if (!confirm('将创建新的空章节，是否继续？')) return;
  const r = await api('/chapters/new', { method: 'POST' });
  invalidatePlanCache();
  setState({ currentChapter: r.num }, 'none');
  toast(`第${r.num}章已创建`);
  setMode(state.mode === 'plan' ? 'plan' : 'write');
  await loadStatus();
}

async function openCodexEntry(id) {
  if (state.editTarget?.type !== 'codex-entry' || state.editTarget?.id !== id) await flushAutosave();
  const entry = await api(`/codex-entries/${id}`);
  setState({ editTarget: { type: 'codex-entry', id } }, 'none');
  setMode('write');
  document.getElementById('mainTitle').textContent = `Codex · ${entry.name}`;
  document.getElementById('mainEditor').value = entry.content;
  document.getElementById('writeEmpty').classList.add('hidden');
  document.getElementById('mainEditor').classList.remove('hidden');
}

async function openGlobal(name) {
  if (state.editTarget?.type !== 'global' || state.editTarget?.name !== name) await flushAutosave();
  const data = await api(`/codex/${name}`);
  setState({ editTarget: { type: 'global', name } }, 'none');
  setMode('write');
  document.getElementById('mainTitle').textContent = GLOBAL_LABELS[name];
  document.getElementById('mainEditor').value = data.content;
  document.getElementById('writeEmpty').classList.add('hidden');
  document.getElementById('mainEditor').classList.remove('hidden');
}

async function createCodexEntry() {
  const name = prompt('Codex 名称（人物/地点/物品）');
  if (!name) return;
  const trimmed = name.trim();
  const r = await api('/codex-entries', { method: 'POST', body: JSON.stringify({ name: trimmed }) });
  invalidateCodexCache();
  scheduleRender({ sidebar: state.sidebar === 'codex' });
  if (r.name && r.name !== trimmed) {
    toast(`名称已规范为：${r.name}`);
  }
  openCodexEntry(r.id);
}

async function toggleCodex(id, checked) {
  const { active } = await api('/codex-entries');
  let ids = [...active];
  if (checked && !ids.includes(id)) ids.push(id);
  else ids = ids.filter(x => x !== id);
  await api('/codex-entries/active', { method: 'PUT', body: JSON.stringify({ active: ids }) });
  dataCache.codex.active = ids;
  toast(checked ? `已注入上下文：${id}` : `已移除：${id}`);
}

// ── Chat ───────────────────────────────────────
function showTypingIndicator(containerId = 'chatMessages') {
  const msgs = document.getElementById(containerId);
  if (!msgs || document.getElementById('typingIndicator')) return;
  const el = document.createElement('div');
  el.id = 'typingIndicator';
  el.className = 'msg assistant';
  el.innerHTML = '<div class="label">AI</div><span class="typing-dots">生成中…</span>';
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTypingIndicator() {
  document.getElementById('typingIndicator')?.remove();
}

function renderChatMessages(messages) {
  const log = document.getElementById('chatMessages');
  clearEl(log);
  if (!messages.length) {
    const empty = cloneTplEl('tpl-chat-empty');
    empty.querySelector('p').textContent = '这是新对话。输入指令开始 — 提到的 Codex 条目会自动加入上下文。';
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = '先去 Plan 写 Beat';
    btn.addEventListener('click', () => setMode('plan'));
    empty.querySelector('.nc-empty-box').appendChild(btn);
    log.appendChild(empty);
    return;
  }
  for (const m of messages) {
    const el = cloneTplEl('tpl-chat-msg');
    el.classList.add(m.role);
    el.querySelector('.label').textContent = m.role === 'user' ? '你的指令' : 'AI 回复';
    let text = m.content || '';
    if (text.length > 4000) text = text.slice(0, 4000) + '\n…';
    el.querySelector('.msg-body').textContent = text;
    log.appendChild(el);
  }
  log.scrollTop = log.scrollHeight;
}

async function loadChat(refreshSidebarPanel = true) {
  const { messages } = await api('/chat/history');
  renderChatMessages(messages);
  if (refreshSidebarPanel && state.sidebar === 'chats') scheduleRender({ sidebar: true });
}

function appendStreamBubble(containerId) {
  const log = document.getElementById(containerId);
  if (!log) return null;
  log.querySelector('.nc-empty')?.remove();
  const el = document.createElement('div');
  el.id = 'streamBubble';
  el.className = 'msg assistant';
  el.innerHTML = '<div class="label">AI 回复</div><div class="stream-body"></div>';
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return el.querySelector('.stream-body');
}

async function sendChatStream(body) {
  const controller = new AbortController();
  let timedOut = false;
  let streamStarted = false;
  let timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, STREAM_FIRST_BYTE_MS);

  const touchIdleTimer = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, STREAM_CHUNK_IDLE_MS);
  };

  try {
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || data.error || resp.statusText);
    }
    if (!resp.body) throw new Error('AI 连接异常，未收到流式响应');

    removeTypingIndicator();
    const bubble = appendStreamBubble('chatMessages');
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let doneMeta = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!streamStarted) {
        streamStarted = true;
        touchIdleTimer();
      } else {
        touchIdleTimer();
      }
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data: ')) continue;
        let evt;
        try { evt = JSON.parse(line.slice(6)); } catch { continue; }
        if (evt.type === 'chunk' && bubble) {
          bubble.textContent += evt.text;
          const log = document.getElementById('chatMessages');
          if (log) log.scrollTop = log.scrollHeight;
        } else if (evt.type === 'done') {
          doneMeta = evt;
        } else if (evt.type === 'error') {
          throw new Error(evt.message || '生成失败');
        }
      }
    }
    if (!doneMeta && !streamStarted) throw new Error('AI 未返回内容，请检查 API Key 或网络');
    return doneMeta;
  } catch (e) {
    if (e.name === 'AbortError' && timedOut) {
      throw new Error(streamStarted ? '生成超时（长时间无新内容），请重试' : '连接超时，请检查网络或 API Key');
    }
    throw e;
  } finally {
    clearTimeout(timer);
    document.getElementById('streamBubble')?.removeAttribute('id');
  }
}

function applyStreamDoneMeta(doneMeta) {
  if (!doneMeta || doneMeta.total_cost == null) return;
  const footer = document.getElementById('footerStat');
  if (!footer) return;
  const text = footer.textContent || '';
  const prefix = text.split('· $')[0] || text;
  footer.textContent = `${prefix.trim()} · $${Number(doneMeta.total_cost).toFixed(4)}`;
}

async function sendChat() {
  const instruction = document.getElementById('chatInstruction').value.trim();
  if (!instruction) return toast('请输入指令');
  const session = beginSending('sendChatBtn', '生成中…');
  if (!session) return;

  let scene_beat = '';
  if (state.currentSceneId) {
    scene_beat = document.getElementById('beatEditor')?.value || '';
  }
  const errEl = document.getElementById('chatError');
  errEl.textContent = '';
  showTypingIndicator('chatMessages');

  try {
    const doneMeta = await sendChatStream({
      instruction,
      scene_beat,
      scene_id: state.currentSceneId || '',
    });
    document.getElementById('chatInstruction').value = '';
    applyStreamDoneMeta(doneMeta);
    if (doneMeta?.chapter_saved) invalidateCache(['plan']);
    await loadChat(true);
    await loadStatus();
    if (doneMeta?.chapter_saved) toast(`已写入第${doneMeta.chapter_num}章`);
  } catch (e) {
    if (!e.cancelled) {
      const msg = e.message || 'AI 连接异常，请检查 API Key 或网络';
      errEl.textContent = msg;
      toast(msg);
    }
    removeTypingIndicator();
  } finally {
    endSending(session);
  }
}

async function clearChat() {
  if (!confirm('清空写书对话？（章节文件保留）')) return;
  await api('/chat/clear', { method: 'POST' });
  await loadChat(true);
}

// ── 自由聊 ─────────────────────────────────────
function renderFreeChatMessages(messages) {
  const log = document.getElementById('freeChatMessages');
  clearEl(log);
  if (!messages.length) {
    const empty = cloneTplEl('tpl-chat-empty');
    empty.querySelector('p').innerHTML = '普通聊天窗口，没有额外提示词。<br>和写书分开，不会写入章节。';
    log.appendChild(empty);
    return;
  }
  for (const m of messages) {
    const el = cloneTplEl('tpl-chat-msg');
    el.classList.add(m.role);
    el.querySelector('.label').textContent = m.role === 'user' ? '你' : 'AI';
    let text = m.content || '';
    if (text.length > 5000) text = text.slice(0, 5000) + '\n…';
    el.querySelector('.msg-body').textContent = text;
    log.appendChild(el);
  }
  log.scrollTop = log.scrollHeight;
}

async function loadFreeChat() {
  const { messages, provider } = await api('/free-chat/history');
  renderFreeChatMessages(messages);
  const sel = document.getElementById('freeProviderSel');
  if (sel && provider) sel.value = provider;
  updateFreeProviderHint(provider || 'deepseek');
}

async function switchFreeProvider() {
  const provider = document.getElementById('freeProviderSel').value;
  await api('/free-chat/provider', { method: 'PUT', body: JSON.stringify({ provider }) });
  updateFreeProviderHint(provider);
  await loadStatus();
  toast(`自由聊已切换为 ${configLabel(provider)}`);
}

async function sendFreeChat() {
  const input = document.getElementById('freeChatInput');
  const content = input.value.trim();
  if (!content) return toast('请输入内容');
  await runWithLoading(async () => {
    const provider = document.getElementById('freeProviderSel').value;
    const errEl = document.getElementById('freeChatError');
    errEl.textContent = '';
    showTypingIndicator('freeChatMessages');
    try {
      await api('/free-chat', { method: 'POST', body: JSON.stringify({ content, provider }) });
      input.value = '';
      await loadFreeChat();
      await loadStatus();
    } catch (e) {
      errEl.textContent = e.message;
    } finally {
      removeTypingIndicator();
    }
  }, { btnId: 'sendFreeChatBtn', loadingText: '生成中…' });
}

async function clearFreeChat() {
  if (!confirm('清空自由聊天记录？')) return;
  await api('/free-chat/clear', { method: 'POST' });
  await loadFreeChat();
}

async function runSummary() {
  await runWithLoading(async () => {
    const r = await api('/summary', { method: 'POST' });
    toast('概述已追加到 summaries.md');
    invalidateCache(['plan']);
    alert(r.reply);
  }, { btnId: 'runSummaryBtn', loadingText: '生成中…' });
}

async function runCheck() {
  await runWithLoading(async () => {
    const r = await api('/check', { method: 'POST' });
    alert(r.reply);
  }, { btnId: 'runCheckBtn', loadingText: '检查中…' });
}

async function runOutline() {
  const raw = prompt('预测后续几章剧情？', '3');
  if (raw === null) return;
  const nextCount = parseInt(raw.trim(), 10);
  if (!Number.isFinite(nextCount) || nextCount < 1 || nextCount > 10) {
    return toast('请输入 1-10 之间的数字');
  }
  await runWithLoading(async () => {
    const r = await api('/outline', {
      method: 'POST',
      body: JSON.stringify({ next_count: nextCount }),
    });
    alert(r.reply);
    await loadStatus();
  }, { btnId: 'runOutlineBtn', loadingText: '生成中…' });
}

// ── Review ─────────────────────────────────────
function makeStatCard(title, num, desc, wide = false) {
  const el = cloneTplEl('tpl-stat-card');
  if (wide) el.style.gridColumn = '1 / -1';
  el.querySelector('h4').textContent = title;
  el.querySelector('.num').textContent = num;
  el.querySelector('.desc').textContent = desc;
  return el;
}

async function renderReview() {
  const s = await api('/stats');
  const st = await api('/status');
  const grid = document.getElementById('reviewGrid');
  clearEl(grid);
  grid.appendChild(makeStatCard('总字数', s.total_chars.toLocaleString(), '全稿字符数（不含空白）'));
  grid.appendChild(makeStatCard('章节 / 场景', `${s.chapter_count} / ${s.scene_count}`, '章节数 · Plan 场景数'));
  grid.appendChild(makeStatCard('Codex / 概述', `${s.codex_count} / ${s.summary_count}`, '设定条目 · 已生成概述章数'));
  grid.appendChild(makeStatCard('API 费用', `$${(s.total_cost ?? st.total_cost).toFixed(4)}`, '累计费用 · 详见 cost_log.txt'));

  const wide = makeStatCard('各章字数', '', '', true);
  const list = document.createElement('div');
  list.className = 'stat-list';
  if (s.chapters.length) {
    for (const c of s.chapters) {
      const row = document.createElement('div');
      row.textContent = `第${c.num}章 — ${c.chars.toLocaleString()} 字`;
      list.appendChild(row);
    }
  } else {
    const row = document.createElement('div');
    row.textContent = '暂无章节';
    list.appendChild(row);
  }
  wide.querySelector('.num').appendChild(list);
  grid.appendChild(wide);
}

// ── Status / settings ─────────────────────────
async function loadStatus() {
  const s = await api('/status');
  updateApiKeyBanner(s);
  document.getElementById('projectSub').textContent = `第${s.chapter_num || '—'}章 · ${s.provider_name}`;
  document.getElementById('ctxTurns').value = s.context_turns;
  document.getElementById('ctxMode').value = s.context_mode;
  document.getElementById('providerSel').value = s.provider;
  document.getElementById('providerSelDrawer').value = s.provider;
  setState({ writingProvider: s.provider }, 'none');
  const freeSel = document.getElementById('freeProviderSel');
  if (freeSel) freeSel.value = s.free_chat_provider || 'deepseek';
  document.getElementById('footerStat').textContent =
    `概述 ${s.summary_count} 章 · 设定 ${s.codex_count} 条 · 自由聊 ${s.free_chat_len || 0} 条 · $${s.total_cost.toFixed(4)}`;
  updateFreeProviderHint(s.free_chat_provider || 'deepseek');

  const cachePill = document.getElementById('cachePill');
  const lc = s.last_call;
  if (lc?.ok && lc.usage) {
    const cr = lc.usage.cache_read || 0;
    cachePill.textContent = cr > 0 ? `cache 命中 ${cr}` : 'cache 写入';
    cachePill.classList.remove('hidden');
  }

  const info = document.getElementById('settingsInfo');
  clearEl(info);
  info.innerHTML =
    `主力：<b>${s.provider_name}</b><br>` +
    `概述 → ${s.summary_provider} · 检查 → ${s.check_provider} · 续章 → ${s.outline_provider}<br>` +
    `上下文：${s.context_mode} / ${s.context_turns} 轮`;

  document.getElementById('contextHint').textContent =
    `${s.context_mode} 模式 · 勾选 Codex 自动注入上下文`;
}

async function saveContext() {
  const turns = parseInt(document.getElementById('ctxTurns').value, 10);
  const mode = document.getElementById('ctxMode').value;
  await api('/config/context', { method: 'PUT', body: JSON.stringify({ turns, mode }) });
  await loadStatus();
  toast(`上下文：${mode}`);
}

function syncProvider(v) {
  document.getElementById('providerSel').value = v;
  document.getElementById('providerSelDrawer').value = v;
  switchProvider();
}

async function switchProvider() {
  const sel = document.getElementById('providerSel');
  const provider = sel.value;
  if (provider === state.writingProvider) return;
  const { messages } = await api('/chat/history');
  if (messages.length > 0) {
    if (!confirm('切换模型后，当前对话历史仍会发给新模型，是否继续？')) {
      sel.value = state.writingProvider;
      document.getElementById('providerSelDrawer').value = state.writingProvider;
      return;
    }
  }
  await api('/config/provider', { method: 'PUT', body: JSON.stringify({ provider }) });
  setState({ writingProvider: provider }, 'none');
  await loadStatus();
  toast(`已切换到 ${configLabel(provider)}`);
}

// ── Init ───────────────────────────────────────
async function init() {
  await loadStatus();
  const { chapters } = await api('/chapters');
  setState(
    { chapters, currentChapter: chapters.length ? chapters[chapters.length - 1].num : null },
    'none',
  );
  setMode('write');
}

document.getElementById('mainEditor')?.addEventListener('input', scheduleAutosave);
document.getElementById('sidebarSearch').addEventListener('input', () => scheduleRender({ sidebar: true }));

window.addEventListener('beforeunload', (e) => {
  if (_autosaveTimer && state.editTarget) {
    e.preventDefault();
    e.returnValue = '';
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden' && _autosaveTimer) flushAutosave();
});

init();
