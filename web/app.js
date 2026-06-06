/* 小说写作助手 — 对标 Novelcrafter 结构，适配本地单项目 */

const state = {
  mode: 'write',
  sidebar: 'codex',
  currentChapter: null,
  currentSceneId: null,
  editTarget: null,
  chapters: [],
  writingProvider: 'kie',
};

const API_TIMEOUT_MS = 120000;
const STREAM_FIRST_BYTE_MS = 90000;
const STREAM_CHUNK_IDLE_MS = 180000;
let _isSending = false;

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
      if (!timedOut && userSignal?.aborted) {
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

function showTypingIndicator(containerId = 'chatMessages') {
  const msgs = document.getElementById(containerId);
  if (!msgs || document.getElementById('typingIndicator')) return;
  msgs.insertAdjacentHTML('beforeend',
    '<div id="typingIndicator" class="msg assistant"><div class="label">AI</div><span class="typing-dots">生成中…</span></div>');
  msgs.scrollTop = msgs.scrollHeight;
}

function removeTypingIndicator() {
  document.getElementById('typingIndicator')?.remove();
}

const GLOBAL_LABELS = {
  world: '世界观 world.md',
  characters: '人物总表 characters.md',
  char_current: '当前状态',
  summaries: '章节概述',
  plot_threads: '伏笔线索',
};

const SIDEBAR_CONFIG = {
  plan:  [{ id: 'scenes', label: '场景' }],
  write: [{ id: 'codex', label: '设定库' }, { id: 'chats', label: '写书记录' }, { id: 'global', label: '全局文件' }],
  chat:  [{ id: 'chats', label: '写书记录' }, { id: 'codex', label: '设定库' }],
  free:  [{ id: 'freechats', label: '聊天记录' }],
};

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function jsEsc(s) {
  return String(s ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function toast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
  clearTimeout(el._t);
  el._t = setTimeout(() => el.style.display = 'none', 2800);
}

function updateApiKeyBanner(s) {
  const el = document.getElementById('apiKeyBanner');
  if (!el) return;
  el.classList.toggle('hidden', !!s.api_key_ok);
}

function countChars(text) {
  return (text || '').replace(/\s/g, '').length;
}

function updateWordCount() {
  const ed = document.getElementById('mainEditor');
  const pill = document.getElementById('wordCountPill');
  if (!pill) return;
  if (state.mode === 'write' && ed && !ed.classList.contains('hidden')) {
    const n = countChars(ed.value);
    pill.textContent = `${n.toLocaleString()} 字`;
    pill.classList.remove('hidden');
  } else if (state.mode !== 'write') {
    pill.classList.add('hidden');
  }
}

// ── Mode ───────────────────────────────────────
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.mode-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.mode === mode));

  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  document.getElementById('view' + mode.charAt(0).toUpperCase() + mode.slice(1)).classList.remove('hidden');

  const tabs = SIDEBAR_CONFIG[mode] || SIDEBAR_CONFIG.write;
  if (!tabs.find(t => t.id === state.sidebar)) state.sidebar = tabs[0].id;
  renderSidebarTabs(tabs);
  document.getElementById('sidebar').classList.toggle('hidden', mode === 'review');
  if (mode === 'free') state.sidebar = 'freechats';

  if (mode === 'plan') renderPlanBoard();
  if (mode === 'write') renderWriteView();
  if (mode === 'chat') { loadChat(); updateChatHints(); }
  if (mode === 'free') loadFreeChat();
  if (mode === 'review') renderReview();

  refreshSidebar();
  updateSidebarAddBtn();
}

function renderSidebarTabs(tabs) {
  document.getElementById('sidebarTabs').innerHTML = tabs.map(t =>
    `<div class="sidebar-tab ${state.sidebar===t.id?'active':''}" onclick="setSidebar('${t.id}')">${t.label}</div>`
  ).join('');
}

function setSidebar(tab) {
  state.sidebar = tab;
  const tabs = SIDEBAR_CONFIG[state.mode] || [];
  renderSidebarTabs(tabs);
  refreshSidebar();
  updateSidebarAddBtn();
}

function updateSidebarAddBtn() {
  const btn = document.getElementById('sidebarAddBtn');
  const labels = { scenes: '场景', codex: '条目', chats: '', global: '', plan: '场景' };
  const key = state.sidebar;
  if (key === 'chats' || key === 'global') { btn.style.display = 'none'; return; }
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

// ── Status ───────────────────────────────────
async function loadStatus() {
  const s = await api('/status');
  updateApiKeyBanner(s);
  document.getElementById('projectSub').textContent =
    `第${s.chapter_num || '—'}章 · ${s.provider_name}`;
  document.getElementById('ctxTurns').value = s.context_turns;
  document.getElementById('ctxMode').value = s.context_mode;
  document.getElementById('providerSel').value = s.provider;
  document.getElementById('providerSelDrawer').value = s.provider;
  state.writingProvider = s.provider;
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

  document.getElementById('settingsInfo').innerHTML =
    `主力：<b>${esc(s.provider_name)}</b><br>` +
    `概述 → ${s.summary_provider} · 检查 → ${s.check_provider}<br>` +
    `上下文：${s.context_mode} / ${s.context_turns} 轮`;

  document.getElementById('contextHint').textContent =
    `${s.context_mode} 模式 · 勾选 Codex 自动注入上下文`;
}

// ── Sidebar content ────────────────────────────
async function refreshSidebar() {
  const body = document.getElementById('sidebarBody');
  const q = (document.getElementById('sidebarSearch').value || '').toLowerCase();

  if (state.sidebar === 'scenes') {
    await renderScenesSidebar(body, q);
  } else if (state.sidebar === 'codex') {
    await renderCodexSidebar(body, q);
  } else if (state.sidebar === 'chats') {
    await renderChatsSidebar(body);
  } else if (state.sidebar === 'freechats') {
    await renderFreeChatsSidebar(body);
  } else if (state.sidebar === 'global') {
    body.innerHTML = Object.entries(GLOBAL_LABELS).map(([k, label]) =>
      `<div class="list-item" onclick="openGlobal('${k}')">${esc(label)}</div>`
    ).join('');
  }
}

async function renderScenesSidebar(body, q) {
  const [{ chapters }, { chapters: planChapters }] = await Promise.all([
    api('/chapters'),
    api('/plan/full'),
  ]);
  const planByNum = Object.fromEntries(planChapters.map(p => [p.num, p]));
  let html = '';
  for (const ch of chapters) {
    const plan = planByNum[ch.num] || { scenes: [] };
    html += `<div class="chapter-label">第${ch.num}章</div>`;
    html += (plan.scenes || []).filter(s =>
      !q || s.title.toLowerCase().includes(q) || (s.beat||'').toLowerCase().includes(q)
    ).map(s => `
      <div class="list-item ${state.currentSceneId===s.id?'active':''}"
           onclick="selectScene('${jsEsc(s.id)}', ${ch.num})">
        <div class="title">${s.done?'✓ ':''}${esc(s.title)}</div>
        <div class="meta">${esc((s.beat||'').slice(0,60) || '无 beat')}</div>
      </div>`).join('');
  }
  body.innerHTML = html || '<div class="empty-inline">暂无场景<br><button class="btn btn-sm" style="margin-top:8px" onclick="newChapter()">新建章节</button></div>';
}

async function renderCodexSidebar(body, q) {
  const { entries, active } = await api('/codex-entries');
  body.innerHTML = entries.filter(e => !q || e.name.toLowerCase().includes(q)).map(e => `
    <label class="codex-check">
      <input type="checkbox" ${active.includes(e.id)?'checked':''}
        onchange="toggleCodex('${jsEsc(e.id)}', this.checked)" />
      <div style="flex:1" onclick="openCodexEntry('${jsEsc(e.id)}')">
        <div class="title">${esc(e.name)}</div>
        <div class="meta">${esc(e.preview||'')}</div>
      </div>
    </label>`).join('') ||
    '<div class="empty-inline">Codex 存放人物、地点、规则<br>写作时勾选即注入 AI 上下文</div>';
}

function configLabel(p) {
  return p === 'kie' ? 'Claude' : 'DeepSeek';
}

function updateFreeProviderHint(provider) {
  const hint = document.getElementById('freeProviderHint');
  if (hint) hint.textContent = `${configLabel(provider)} · 纯对话，无系统提示词`;
}

async function renderChatsSidebar(body) {
  const { messages } = await api('/chat/history');
  if (!messages.length) {
    body.innerHTML = '<div class="empty-inline">写书对话为空<br>在「写书对话」模式发送指令</div>';
    return;
  }
  body.innerHTML = messages.map((m, i) => {
    const preview = (m.content || '').slice(0, 80);
    const role = m.role === 'user' ? '你' : 'AI';
    return `<div class="list-item" onclick="setMode('chat')">
      <div class="title">${role} #${i+1}</div>
      <div class="meta">${esc(preview)}</div>
    </div>`;
  }).join('');
}

async function renderFreeChatsSidebar(body) {
  const { messages } = await api('/free-chat/history');
  if (!messages.length) {
    body.innerHTML = '<div class="empty-inline">自由聊为空</div>';
    return;
  }
  body.innerHTML = messages.map((m, i) => {
    const preview = (m.content || '').slice(0, 80);
    const role = m.role === 'user' ? '你' : 'AI';
    return `<div class="list-item" onclick="setMode('free')">
      <div class="title">${role} #${i+1}</div>
      <div class="meta">${esc(preview)}</div>
    </div>`;
  }).join('');
}

// ── Plan board ─────────────────────────────────
let _planSortable = null;

async function renderPlanBoard() {
  const [{ chapters }, { chapters: planChapters }] = await Promise.all([
    api('/chapters'),
    api('/plan/full'),
  ]);
  state.chapters = chapters;
  const planByNum = Object.fromEntries(planChapters.map(p => [p.num, p]));
  const sel = document.getElementById('planChapterSel');
  sel.innerHTML = chapters.map(c => {
    const title = planByNum[c.num]?.title;
    const label = title && title !== `第${c.num}章` ? `第${c.num}章 · ${title}` : `第${c.num}章`;
    return `<option value="${c.num}">${esc(label)}</option>`;
  }).join('');

  const board = document.getElementById('planBoard');
  const beatPanel = document.getElementById('planBeatPanel');

  if (!chapters.length) {
    board.innerHTML = `<div class="nc-empty" style="grid-column:1/-1">
      <div class="nc-empty-box">
        <p>还没有场景。先创建章节，再添加 Scene Beat 规划每一个场景。</p>
        <button class="btn btn-primary btn-lg" onclick="newChapter()">+ 创建第一章</button>
      </div></div>`;
    beatPanel.classList.add('hidden');
    return;
  }

  const num = state.currentChapter || chapters[chapters.length - 1].num;
  state.currentChapter = num;
  sel.value = String(num);
  const plan = planByNum[num] || (await api(`/plan/${num}`));
  const scenes = plan.scenes || [];

  if (!scenes.length) {
    board.innerHTML = `<div class="nc-empty" style="grid-column:1/-1">
      <div class="nc-empty-box">
        <p>第${num}章还没有场景。写一个 Scene Beat，再交给 Chat 生成正文。</p>
        <button class="btn btn-primary btn-lg" onclick="addScene(${num})">+ 创建第一个场景</button>
      </div></div>`;
    beatPanel.classList.add('hidden');
    return;
  }

  board.innerHTML = `<div id="planSceneList" class="plan-scene-list">${
    scenes.map(s => `
    <div class="scene-card ${state.currentSceneId===s.id?'active':''}" data-id="${esc(s.id)}"
         onclick="selectScene('${jsEsc(s.id)}', ${num})">
      <h4>
        <input type="checkbox" ${s.done?'checked':''}
          onclick="event.stopPropagation()"
          onchange="toggleSceneDone('${esc(s.id)}', this.checked)"
          title="标记完成" />
        ${esc(s.title)}
      </h4>
      <p>${esc(s.beat || '点击添加 Scene Beat…')}</p>
      <div class="tag">第${num}章 · 场景 · 可拖拽排序</div>
    </div>`).join('')
  }</div><div class="scene-card no-sort" style="display:flex;align-items:center;justify-content:center;min-height:140px" onclick="addScene(${num})">
    <span style="color:var(--text-3)">+ 添加场景</span></div>`;

  initPlanSortable(num);
  beatPanel.classList.toggle('hidden', !state.currentSceneId);
}

function initPlanSortable(chapterNum) {
  const list = document.getElementById('planSceneList');
  if (!list || typeof Sortable === 'undefined') return;
  if (_planSortable) {
    _planSortable.destroy();
    _planSortable = null;
  }
  _planSortable = Sortable.create(list, {
    animation: 150,
    draggable: '.scene-card',
    ghostClass: 'dragging',
    onEnd: async () => {
      const ids = [...list.querySelectorAll('.scene-card')].map(el => el.dataset.id);
      await api(`/plan/${chapterNum}/reorder`, {
        method: 'PUT',
        body: JSON.stringify({ scene_ids: ids }),
      });
      toast('场景顺序已更新');
      refreshSidebar();
    },
  });
}

async function toggleSceneDone(sceneId, done) {
  await api(`/plan/scenes/${sceneId}`, { method: 'PUT', body: JSON.stringify({ done }) });
  if (state.mode === 'plan') renderPlanBoard();
  refreshSidebar();
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
  await renderPlanBoard();
  if (state.mode === 'write') await renderWriteView();
  toast('章节标题已更新');
}

async function selectScene(sceneId, chapterNum) {
  state.currentChapter = chapterNum;
  if (!sceneId) {
    state.currentSceneId = null;
    document.getElementById('planBeatPanel')?.classList.add('hidden');
    if (state.mode === 'plan') renderPlanBoard();
    refreshSidebar();
    updateChatHints();
    return;
  }
  state.currentSceneId = sceneId;
  await api(`/plan/active/${sceneId}`, { method: 'PUT' });
  const plan = await api(`/plan/${chapterNum}`);
  const scene = plan.scenes?.find(s => s.id === sceneId);
  if (scene) {
    document.getElementById('beatEditor').value = scene.beat || '';
    document.getElementById('planSceneTitle').textContent = scene.title;
    document.getElementById('planBeatPanel').classList.remove('hidden');
  } else {
    state.currentSceneId = null;
    document.getElementById('planBeatPanel')?.classList.add('hidden');
  }
  if (state.mode === 'plan') renderPlanBoard();
  refreshSidebar();
  updateChatHints();
}

async function addScene(chapterNum) {
  if (!chapterNum) { toast('请先创建章节'); return; }
  const title = prompt('场景标题', '新场景')?.trim();
  if (!title) return;
  const r = await api('/plan/scenes', { method: 'POST', body: JSON.stringify({ chapter_num: chapterNum, title }) });
  await selectScene(r.scene.id, chapterNum);
  if (state.mode === 'plan') renderPlanBoard();
  refreshSidebar();
  toast('场景已创建');
}

async function saveBeat() {
  if (!state.currentSceneId) return;
  const beat = document.getElementById('beatEditor').value;
  await api(`/plan/scenes/${state.currentSceneId}`, { method: 'PUT', body: JSON.stringify({ beat }) });
  if (state.mode === 'plan') renderPlanBoard();
  refreshSidebar();
  toast('Beat 已保存');
}

function onPlanChapterChange() {
  state.currentChapter = parseInt(document.getElementById('planChapterSel').value, 10);
  state.currentSceneId = null;
  renderPlanBoard();
}

// ── Write ──────────────────────────────────────
async function renderWriteView() {
  const [{ chapters }, { chapters: planChapters }] = await Promise.all([
    api('/chapters'),
    api('/plan/full'),
  ]);
  state.chapters = chapters;
  const planByNum = Object.fromEntries(planChapters.map(p => [p.num, p]));
  const sel = document.getElementById('writeChapterSel');
  const empty = document.getElementById('writeEmpty');
  const editor = document.getElementById('mainEditor');

  if (!chapters.length) {
    sel.innerHTML = '';
    empty.classList.remove('hidden');
    editor.classList.add('hidden');
    return;
  }

  empty.classList.add('hidden');
  editor.classList.remove('hidden');
  sel.innerHTML = chapters.map(c => {
    const title = planByNum[c.num]?.title;
    const label = title && title !== `第${c.num}章` ? `第${c.num}章 · ${title}` : `第${c.num}章`;
    return `<option value="${c.num}">${esc(label)}</option>`;
  }).join('');

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
  state.currentChapter = num;
  state.editTarget = { type: 'chapter', num };
  document.getElementById('mainTitle').textContent = `第${num}章 正文`;
  document.getElementById('mainEditor').value = ch.content;
  document.getElementById('writeChapterSel').value = num;
  updateWordCount();
}

function onWriteChapterChange() {
  openChapter(parseInt(document.getElementById('writeChapterSel').value, 10));
}

let _autosaveTimer = null;

function scheduleAutosave() {
  updateWordCount();
  if (!state.editTarget) return;
  clearTimeout(_autosaveTimer);
  _autosaveTimer = setTimeout(() => saveEditor({ silent: true }), 2000);
}

document.getElementById('mainEditor')?.addEventListener('input', scheduleAutosave);

async function saveEditor({ silent = false } = {}) {
  const t = state.editTarget;
  const content = document.getElementById('mainEditor').value;
  if (!t) return toast('请先选择章节或设定');
  const titleEl = document.getElementById('mainTitle');
  try {
    if (t.type === 'chapter') {
      await api(`/chapters/${t.num}`, { method: 'PUT', body: JSON.stringify({ content }) });
      if (silent) {
        const pill = document.getElementById('wordCountPill');
        if (pill) {
          pill.classList.add('saved-flash');
          setTimeout(() => pill.classList.remove('saved-flash'), 1200);
        }
      } else {
        toast(`第${t.num}章已保存`);
      }
      if (titleEl) titleEl.textContent = `第${t.num}章 正文`;
    } else if (t.type === 'codex-entry') {
      await api(`/codex-entries/${t.id}`, { method: 'PUT', body: JSON.stringify({ content }) });
      toast(silent ? 'Codex 已自动保存' : 'Codex 已保存');
    } else if (t.type === 'global') {
      await api(`/codex/${t.name}`, { method: 'PUT', body: JSON.stringify({ content }) });
      toast(silent ? '设定已自动保存' : '设定已保存');
    }
  } catch (e) {
    if (t.type === 'chapter' && titleEl) {
      titleEl.textContent = `第${t.num}章 ⚠️ 保存失败`;
    }
    if (!silent) toast(e.message || '保存失败');
  }
}

async function newChapter() {
  if (!confirm('将创建新的空章节，是否继续？')) return;
  const r = await api('/chapters/new', { method: 'POST' });
  state.currentChapter = r.num;
  toast(`第${r.num}章已创建`);
  if (state.mode === 'plan') { setMode('plan'); renderPlanBoard(); }
  else { setMode('write'); }
  await loadStatus();
}

async function openCodexEntry(id) {
  if (state.editTarget?.type !== 'codex-entry' || state.editTarget?.id !== id) {
    await flushAutosave();
  }
  const entry = await api(`/codex-entries/${id}`);
  state.editTarget = { type: 'codex-entry', id };
  setMode('write');
  document.getElementById('mainTitle').textContent = `Codex · ${entry.name}`;
  document.getElementById('mainEditor').value = entry.content;
  document.getElementById('writeEmpty').classList.add('hidden');
  document.getElementById('mainEditor').classList.remove('hidden');
}

async function openGlobal(name) {
  if (state.editTarget?.type !== 'global' || state.editTarget?.name !== name) {
    await flushAutosave();
  }
  const data = await api(`/codex/${name}`);
  state.editTarget = { type: 'global', name };
  setMode('write');
  document.getElementById('mainTitle').textContent = GLOBAL_LABELS[name];
  document.getElementById('mainEditor').value = data.content;
  document.getElementById('writeEmpty').classList.add('hidden');
  document.getElementById('mainEditor').classList.remove('hidden');
}

async function createCodexEntry() {
  const name = prompt('Codex 名称（人物/地点/物品）');
  if (!name) return;
  const r = await api('/codex-entries', { method: 'POST', body: JSON.stringify({ name }) });
  if (!r.ok) return alert(r.error || '创建失败');
  refreshSidebar();
  openCodexEntry(r.id);
}

async function toggleCodex(id, checked) {
  const { active } = await api('/codex-entries');
  let ids = [...active];
  if (checked && !ids.includes(id)) ids.push(id);
  else ids = ids.filter(x => x !== id);
  await api('/codex-entries/active', { method: 'PUT', body: JSON.stringify({ active: ids }) });
  toast(checked ? `已注入上下文：${id}` : `已移除：${id}`);
}

// ── Chat ───────────────────────────────────────
function updateChatHints() {
  const hint = document.getElementById('chatSceneHint');
  if (state.currentSceneId) {
    hint.textContent = `当前场景已选中 · 第${state.currentChapter}章`;
  } else {
    hint.textContent = '建议先在 Plan 选中场景';
  }
}

function renderChat(messages) {
  const log = document.getElementById('chatMessages');
  if (!messages.length) {
    log.innerHTML = `<div class="nc-empty"><div class="nc-empty-box" style="border:none">
      <p>这是新对话。输入指令开始 — 提到的 Codex 条目会自动加入上下文。</p>
      <button class="btn" onclick="setMode('plan')">先去 Plan 写 Beat</button>
    </div></div>`;
    return;
  }
  log.innerHTML = messages.map(m => {
    const label = m.role === 'user' ? '你的指令' : 'AI 回复';
    let text = m.content;
    if (text.length > 4000) text = text.slice(0, 4000) + '\n…';
    return `<div class="msg ${m.role}"><div class="label">${label}</div>${esc(text)}</div>`;
  }).join('');
  log.scrollTop = log.scrollHeight;
}

async function loadChat() {
  const { messages } = await api('/chat/history');
  renderChat(messages);
  refreshSidebar();
}

function appendStreamBubble(containerId) {
  const log = document.getElementById(containerId);
  if (!log) return null;
  const empty = log.querySelector('.nc-empty');
  if (empty) empty.remove();
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
    if (!resp.body) {
      throw new Error('AI 连接异常，未收到流式响应');
    }

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
        try {
          evt = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
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
    if (!doneMeta && !streamStarted) {
      throw new Error('AI 未返回内容，请检查 API Key 或网络');
    }
    return doneMeta;
  } catch (e) {
    if (e.name === 'AbortError' && timedOut) {
      const msg = streamStarted
        ? '生成超时（长时间无新内容），请重试'
        : '连接超时，请检查网络或 API Key';
      throw new Error(msg);
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
    const beatEl = document.getElementById('beatEditor');
    scene_beat = beatEl?.value || '';
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
    await loadChat();
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
  await loadChat();
}

// ── 自由聊 ─────────────────────────────────────
function renderFreeChat(messages) {
  const log = document.getElementById('freeChatMessages');
  if (!messages.length) {
    log.innerHTML = `<div class="nc-empty"><div class="nc-empty-box" style="border:none">
      <p>普通聊天窗口，没有额外提示词。<br>和写书分开，不会写入章节。</p>
    </div></div>`;
    return;
  }
  log.innerHTML = messages.map(m => {
    const label = m.role === 'user' ? '你' : 'AI';
    let text = m.content;
    if (text.length > 5000) text = text.slice(0, 5000) + '\n…';
    return `<div class="msg ${m.role}"><div class="label">${label}</div>${esc(text)}</div>`;
  }).join('');
  log.scrollTop = log.scrollHeight;
}

async function loadFreeChat() {
  const { messages, provider } = await api('/free-chat/history');
  renderFreeChat(messages);
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
      const r = await api('/free-chat', {
        method: 'POST',
        body: JSON.stringify({ content, provider }),
      });
      if (!r.ok) throw new Error(r.error);
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
    if (!r.ok) return alert(r.error);
    toast('概述已追加到 summaries.md');
    alert(r.reply);
  }, { btnId: 'runSummaryBtn', loadingText: '生成中…' });
}

async function runCheck() {
  await runWithLoading(async () => {
    const r = await api('/check', { method: 'POST' });
    if (!r.ok) return alert(r.error);
    alert(r.reply);
  }, { btnId: 'runCheckBtn', loadingText: '检查中…' });
}

// ── Review ─────────────────────────────────────
async function renderReview() {
  const s = await api('/stats');
  const st = await api('/status');
  document.getElementById('reviewGrid').innerHTML = `
    <div class="stat-card">
      <h4>总字数</h4>
      <div class="num">${s.total_chars.toLocaleString()}</div>
      <div class="desc">全稿字符数（不含空白）</div>
    </div>
    <div class="stat-card">
      <h4>章节 / 场景</h4>
      <div class="num">${s.chapter_count} / ${s.scene_count}</div>
      <div class="desc">章节数 · Plan 场景数</div>
    </div>
    <div class="stat-card">
      <h4>Codex / 概述</h4>
      <div class="num">${s.codex_count} / ${s.summary_count}</div>
      <div class="desc">设定条目 · 已生成概述章数</div>
    </div>
    <div class="stat-card">
      <h4>API 费用</h4>
      <div class="num">$${(s.total_cost ?? st.total_cost).toFixed(4)}</div>
      <div class="desc">累计费用 · 详见 cost_log.txt</div>
    </div>
    <div class="stat-card" style="grid-column:1/-1">
      <h4>各章字数</h4>
      <div class="stat-list">
        ${s.chapters.length ? s.chapters.map(c =>
          `<div>第${c.num}章 — ${c.chars.toLocaleString()} 字</div>`
        ).join('') : '<div>暂无章节</div>'}
      </div>
    </div>`;
}

// ── Settings ───────────────────────────────────
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
  state.writingProvider = provider;
  await loadStatus();
  toast(`已切换到 ${configLabel(provider)}`);
}

// ── Init ───────────────────────────────────────
async function init() {
  await loadStatus();
  const { chapters } = await api('/chapters');
  state.chapters = chapters;
  if (chapters.length) state.currentChapter = chapters[chapters.length-1].num;
  setMode('write');
}

document.getElementById('sidebarSearch').addEventListener('input', refreshSidebar);

window.addEventListener('beforeunload', (e) => {
  if (_autosaveTimer && state.editTarget) {
    e.preventDefault();
    e.returnValue = '';
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden' && _autosaveTimer) {
    flushAutosave();
  }
});

init();
