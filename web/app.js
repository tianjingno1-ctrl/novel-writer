/* 小说写作助手 — 原生 JS + setState/render + template */

// ── State ───────────────────────────────────────
const state = {
  mode: 'write',
  sidebar: 'toc',
  currentChapter: null,
  writeChapterNum: null,
  currentSceneId: null,
  editTarget: null,
  chapters: [],
  writingProvider: 'deepseek',
  chatFocusTurn: null,
  activePromptId: null, // 最近点选的指令库条目
};

const dataCache = {
  chapters: [],
  planByNum: {},
  codex: { entries: [], active: [] },
  chat: { messages: [], appended: [], turns: [], prompts: [] },
  quality: { entries: [], loadedAt: 0 },
  freeChat: { messages: [] },
};

const API_TIMEOUT_MS = 120000;
/** 本章定稿：档案 + 质检 + 爽点，多次 LLM 串行，与后端 httpx 超时对齐 */
const FINALIZE_API_TIMEOUT_MS = 1800000;
/** 一键全查：多次 LLM 串行 */
const QUALITY_FULL_TIMEOUT_MS = FINALIZE_API_TIMEOUT_MS;
/** 自由聊：超长输出 + 大上下文，与后端 httpx 超时对齐（30 分钟） */
const FREE_CHAT_API_TIMEOUT_MS = 1800000;
const STREAM_FIRST_BYTE_MS = 90000;
const STREAM_CHUNK_IDLE_MS = 180000;
const RENDER_DEBOUNCE_MS = 16;

const FINALIZE_ON_SAVE_KEY = 'novel_prompt_finalize_on_save';

function shouldPromptFinalizeOnSave() {
  try {
    return localStorage.getItem(FINALIZE_ON_SAVE_KEY) === '1';
  } catch {
    return false;
  }
}

function parseRecordTimestamp(ts) {
  if (!ts) return null;
  const normalized = String(ts).trim().replace(' ', 'T');
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatRecordTime(ts) {
  const d = parseRecordTimestamp(ts);
  if (!d) return ts || '';
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function formatRelativeTime(ts) {
  const d = parseRecordTimestamp(ts);
  if (!d) return '';
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function timeBadgeHtml(ts, variant = 'muted') {
  if (!ts) return '';
  const abs = formatRecordTime(ts);
  const rel = formatRelativeTime(ts);
  const relPart = rel ? ` · ${rel}` : '';
  return `<time class="record-time record-time--${variant}" datetime="${escapeHtml(String(ts))}">${escapeHtml(abs)}${escapeHtml(relPart)}</time>`;
}

function splitChapterDisplayTitle(text) {
  const raw = (text || '').trim();
  if (!raw) return { title: null, body: '' };
  const m = raw.match(/^#\s*第\s*(\d+|[一二三四五六七八九十百千]+)\s*章(?:\s*[·•\-—]\s*(.+))?/);
  if (m) {
    const sub = (m[2] || '').trim();
    const body = raw.slice(m[0].length).replace(/^\s*\n+/, '');
    return { title: sub || null, body: body || raw };
  }
  const parsed = extractChapterTitleFromReply(raw);
  if (parsed.title) return { title: parsed.title, body: parsed.body || raw };
  return { title: null, body: raw };
}

function _logMaintainUiState() {}

function _dbgApiLog() {}

function _dbgUiLog() {}

let _isChatSending = false;
let _isQualityBusy = false;
let _chatStreamAbort = null;
let _chatStreamReader = null;
let _chatStreamUserCancelled = false;
let _activeSendingSession = null;
let _codexFileList = null;
let _qualityResultText = '';
let _planSortable = null;
let _autosaveTimer = null;
let _renderTimer = null;
let _renderOpts = { chrome: false, main: false, sidebar: false };
let _editorSnapshot = null;

const GLOBAL_LABELS = {
  world: '世界观 world.md',
  style: '文风锚点 style.md',
  characters: '人物总表 characters.md',
  char_static: '人物锚点 char_static.md',
  char_dynamic: '人物动态 char_dynamic.md',
  summaries_archive: '概述归档 summaries_archive.md',
  summaries_recent: '近期概述 summaries_recent.md',
  plot_threads_locked: '细节钉子 plot_threads_locked.md',
  plot_threads_active: '伏笔线索 plot_threads_active.md',
  char_current: '（已拆分）char_current.md',
  summaries: '（兼容）summaries.md',
  plot_threads: '（已拆分）plot_threads.md',
};

const GLOBAL_DEPRECATED = new Set(['char_current', 'summaries', 'plot_threads']);

function globalFileLabel(name) {
  return GLOBAL_LABELS[name] || `${name}.md`;
}

async function ensureCodexFileList() {
  if (_codexFileList) return _codexFileList;
  const { files } = await api('/codex');
  _codexFileList = files || [];
  return _codexFileList;
}

function formatApiError(data, fallback = '请求失败') {
  const d = data?.detail ?? data?.error;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map((x) => x.msg || x.message || JSON.stringify(x)).join('；');
  }
  if (d && typeof d === 'object') return d.message || JSON.stringify(d);
  return fallback;
}

function getWriteTargetConflict() {
  const writeNum = getWriteChapterNum();
  if (!writeNum || !state.currentSceneId) return null;
  const found = getSceneFromCache(state.currentSceneId);
  const sceneCh = found?.chapterNum;
  if (sceneCh && sceneCh !== writeNum) {
    return { writeNum, sceneCh };
  }
  return null;
}

const SIDEBAR_CONFIG = {
  plan: [{ id: 'scenes', label: '场景' }],
  write: [
    { id: 'toc', label: '目录' },
    { id: 'codex', label: '设定库' },
    { id: 'chats', label: '写书记录' },
    { id: 'quality', label: '质量记录' },
    { id: 'global', label: '全局文件' },
  ],
  chat: [
    { id: 'chats', label: '写书记录' },
    { id: 'quality', label: '质量记录' },
    { id: 'codex', label: '设定库' },
    { id: 'toc', label: '目录' },
  ],
  free: [{ id: 'freechats', label: '讨论话题' }],
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
  document.getElementById('sidebar')?.classList.toggle('hidden', mode === 'review' || mode === 'overview' || mode === 'quality' || mode === 'deconstruct');

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
    case 'overview':
      await renderOverview();
      break;
    case 'deconstruct':
      await renderDeconstructView();
      break;
    case 'plan':
      await renderPlanBoardFull();
      break;
    case 'write':
      await renderWriteView();
      break;
    case 'chat':
      await fillWriteChapterTargetSel();
      await loadChat(false);
      await loadChatPrompts();
      renderPromptLibrary();
      updateChatBeatPreview(getSceneFromCache(state.currentSceneId)?.scene);
      updateChatHints();
      break;
    case 'free':
      await loadFreeChat();
      break;
    case 'quality':
      await renderQualityView();
      break;
    case 'review':
      await renderReview();
      break;
  }
  await renderGuideHints(state.mode);
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

function mergeChapterList(fileChapters, planChapters) {
  const nums = new Set([
    ...fileChapters.map(c => c.num),
    ...planChapters.map(p => p.num),
  ]);
  return [...nums].sort((a, b) => a - b).map(num => {
    const file = fileChapters.find(c => c.num === num);
    return file || {
      num,
      file: `ch${String(num).padStart(3, '0')}.md`,
      planned_only: true,
    };
  });
}

function fillSelect(sel, chapters, planByNum) {
  clearEl(sel);
  for (const c of chapters) {
    const opt = document.createElement('option');
    opt.value = String(c.num);
    const title = planByNum[c.num]?.title;
    const label =
      title && title !== `第${c.num}章` ? `第${c.num}章 · ${title}` : `第${c.num}章`;
    opt.textContent = c.planned_only ? `${label}（规划中）` : label;
    sel.appendChild(opt);
  }
}

// ── Data cache ──────────────────────────────────
async function ensurePlanData(force = false) {
  if (force || !dataCache.chapters.length) {
    const [{ chapters: fileChapters }, { chapters: planChapters }] = await Promise.all([
      api('/chapters'),
      api('/plan/full'),
    ]);
    const chapters = mergeChapterList(fileChapters, planChapters);
    dataCache.chapters = chapters;
    dataCache.planByNum = Object.fromEntries(planChapters.map(p => [p.num, p]));
    state.chapters = chapters;
  }
  return dataCache;
}

function invalidateCache(keys = ['all']) {
  const all = keys.includes('all');
  if (all || keys.includes('plan') || keys.includes('chapters')) {
    dataCache.chapters = [];
    dataCache.planByNum = {};
  }
  if (all || keys.includes('codex')) {
    dataCache.codex = { entries: [], active: [] };
  }
}

function _chaptersWithBody() {
  const withBody = dataCache.chapters.filter((c) => !c.planned_only);
  return withBody.length ? withBody : dataCache.chapters;
}

function getWriteChapterNum() {
  if (state.writeChapterNum) return state.writeChapterNum;
  if (state.editTarget?.type === 'chapter') return state.editTarget.num;
  const selVal = parseInt(document.getElementById('writeChapterSel')?.value || '', 10);
  if (selVal > 0) return selVal;
  const list = _chaptersWithBody();
  return list.length ? list[list.length - 1].num : null;
}

async function getLatestChapterNum() {
  await ensurePlanData();
  const list = _chaptersWithBody();
  return list.length ? list[list.length - 1].num : 1;
}

async function setWriteChapterTarget(num) {
  const n = parseInt(num, 10);
  if (!n) return;
  const sel = document.getElementById('writeChapterTargetSel');
  const prev = state.writeChapterNum;
  try {
    const r = await api('/chat/write-chapter', {
      method: 'PUT',
      body: JSON.stringify({ chapter_num: n }),
    });
    setState({ writeChapterNum: r.write_chapter_num || n }, 'none');
    updateChatHints();
    toast(`写作目标已设为第 ${r.write_chapter_num || n} 章`);
  } catch (e) {
    toast(e.message || '设置写作目标失败');
    if (sel) {
      if (prev) sel.value = String(prev);
      else await fillWriteChapterTargetSel();
    }
    updateChatHints();
  }
}

async function restoreActiveSceneFromStatus(activeSceneId) {
  if (!activeSceneId) return;
  await ensurePlanData();
  for (const ch of dataCache.chapters) {
    const plan = dataCache.planByNum[ch.num];
    const scene = plan?.scenes?.find((s) => s.id === activeSceneId);
    if (scene) {
      setState({ currentSceneId: activeSceneId, currentChapter: ch.num }, 'none');
      loadSceneBeatIntoEditors(scene);
      updateChatBeatPreview(scene);
      highlightActiveScene(activeSceneId);
      return;
    }
  }
}

function invalidatePlanCache() {
  invalidateCache(['plan']);
}

function invalidateCodexCache() {
  _codexFileList = null;
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
function resetChatSendingUi() {
  _isChatSending = false;
  _chatStreamAbort = null;
  _chatStreamReader = null;
  _chatStreamUserCancelled = false;
  _activeSendingSession = null;
  const btn = document.getElementById('sendChatBtn');
  if (btn) {
    btn.disabled = false;
    if (btn.textContent === '生成中…') btn.textContent = '发送';
  }
  document.getElementById('stopChatBtn')?.classList.add('hidden');
}

function beginSending(btnId, loadingText = '处理中…') {
  if (_isChatSending) {
    // #region agent log
    _dbgUiLog('app.js:beginSending', 'blocked: already sending', {
      btnDisabled: document.getElementById('sendChatBtn')?.disabled,
      hasAbort: !!_chatStreamAbort,
      hasSession: !!_activeSendingSession,
    }, 'H7');
    // #endregion
    toast('请等待当前写书生成完成');
    return null;
  }
  _chatStreamUserCancelled = false;
  _isChatSending = true;
  const btn = btnId ? document.getElementById(btnId) : null;
  const defaultText = btn?.textContent || '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = loadingText;
  }
  document.getElementById('stopChatBtn')?.classList.remove('hidden');
  _activeSendingSession = { btn, defaultText };
  // #region agent log
  _dbgUiLog('app.js:beginSending', 'stop btn shown', {
    hasAbort: !!_chatStreamAbort,
    isChatSending: _isChatSending,
  }, 'H1');
  // #endregion
  return _activeSendingSession;
}

function endSending(session) {
  _isChatSending = false;
  _chatStreamAbort = null;
  _chatStreamReader = null;
  _activeSendingSession = null;
  document.getElementById('stopChatBtn')?.classList.add('hidden');
  const s = session || null;
  if (!s) return;
  const { btn, defaultText } = s;
  if (btn) {
    btn.disabled = false;
    btn.textContent = defaultText || '发送';
  }
}

function isChatStreamInProgress() {
  return !!(
    _isChatSending
    || _chatStreamAbort
    || _chatStreamReader
    || document.getElementById('streamBubble')
    || document.querySelector('#chatMessages [data-optimistic="1"]')
  );
}

function cancelChatStream() {
  const hadAbort = !!_chatStreamAbort;
  const hadReader = !!_chatStreamReader;
  const wasSending = _isChatSending;
  const session = _activeSendingSession;
  const inProgress = isChatStreamInProgress();
  // #region agent log
  _dbgUiLog('app.js:cancelChatStream', 'stop clicked', {
    hadAbort,
    hadReader,
    wasSending,
    inProgress,
    hasSession: !!session,
    streamBubble: !!document.getElementById('streamBubble'),
    optimistic: !!document.querySelector('#chatMessages [data-optimistic="1"]'),
  }, inProgress ? 'H2' : 'H1');
  // #endregion
  if (inProgress) _chatStreamUserCancelled = true;
  if (_chatStreamAbort) _chatStreamAbort.abort();
  if (_chatStreamReader) _chatStreamReader.cancel().catch(() => {});
  if (inProgress) {
    document.getElementById('streamBubble')?.remove();
    removeTypingIndicator();
    endSending(session);
    toast('已停止生成');
    return;
  }
  toast('当前没有进行中的生成');
}

async function api(path, opts = {}, timeoutMs = API_TIMEOUT_MS) {
  const controller = new AbortController();
  let timedOut = false;
  const apiStart = Date.now();
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
  const headers = { 'Content-Type': 'application/json', ...(fetchOpts.headers || {}) };
  const token = sessionStorage.getItem('novel_web_token');
  if (token) headers['X-Novel-Token'] = token;
  try {
    const r = await fetch('/api' + path, {
      ...fetchOpts,
      headers,
      signal: controller.signal,
    });
    const data = await r.json().catch(() => ({}));
    // #region agent log
    if (!r.ok || path.includes('finalize')) {
      _dbgApiLog('app.js:api', r.ok ? 'api ok' : 'api http error', {
        path,
        method: fetchOpts.method || 'GET',
        status: r.status,
        ok: r.ok,
        detail: typeof data.detail === 'string' ? data.detail.slice(0, 200) : data.detail,
        error: data.error,
        ms: Date.now() - apiStart,
      }, r.ok ? 'H1' : 'H1');
    }
    // #endregion
    if (r.status === 401) {
      const entered = prompt('Web API 需要访问令牌（.env 中的 NOVEL_WEB_TOKEN）');
      if (entered) {
        sessionStorage.setItem('novel_web_token', entered.trim());
        return api(path, opts, timeoutMs);
      }
      throw new Error(formatApiError(data, '未授权'));
    }
    if (!r.ok) {
      const msg = formatApiError(data, r.statusText);
      if (r.status === 403 && msg.includes('非本地')) {
        throw new Error(`${msg}\n\n请用 http://127.0.0.1:8765 打开，或在 .env 设置 NOVEL_WEB_TOKEN 后输入令牌`);
      }
      throw new Error(msg);
    }
    return data;
  } catch (e) {
    // #region agent log
    if (!e.cancelled) {
      _dbgApiLog('app.js:api', 'api fetch error', {
        path,
        method: fetchOpts.method || 'GET',
        error: String(e.message || e).slice(0, 300),
        ms: Date.now() - apiStart,
      }, 'H1');
    }
    // #endregion
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

async function runWithLoading(fn, { btnId, btnIds, loadingText = '处理中…' } = {}) {
  if (_isChatSending) {
    toast('写书对话生成中，请等待完成后再操作');
    return null;
  }
  if (_isQualityBusy) {
    toast('请等待当前质量检查完成');
    return null;
  }
  _isQualityBusy = true;
  const ids = btnIds || (btnId ? [btnId] : []);
  const buttons = ids.map((id) => document.getElementById(id)).filter(Boolean);
  const defaultTexts = buttons.map((b) => b.textContent || '');
  for (const btn of buttons) {
    btn.disabled = true;
    btn.textContent = loadingText;
  }
  try {
    return await fn();
  } finally {
    _isQualityBusy = false;
    buttons.forEach((btn, i) => {
      btn.disabled = false;
      btn.textContent = defaultTexts[i];
    });
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

const PROVIDER_LABELS = {
  kie: 'Claude Sonnet 4.6',
  'kie-opus': 'Claude Opus 4.6',
  'kie-opus-47': 'Claude Opus 4.7',
  'kie-opus-48': 'Claude Opus 4.8',
  deepseek: 'DeepSeek V4 Pro',
};

function configLabel(p) {
  return PROVIDER_LABELS[p] || p;
}

function updateFreeProviderHint(provider) {
  const hint = document.getElementById('freeProviderHint');
  if (!hint) return;
  const base = `${configLabel(provider)} · 纯对话，无系统提示词`;
  hint.textContent = provider === 'kie' || provider.startsWith('kie-')
    ? `${base} · 自由聊推荐 DeepSeek（kie 偶发 500）`
    : base;
}

function updateApiKeyBanner(s) {
  const el = document.getElementById('apiKeyBanner');
  if (!el) return;
  el.classList.toggle('hidden', !!s.api_key_ok);
}

const SIDEBAR_COLLAPSED_KEY = 'novel_writer_sidebar_collapsed';

function toggleSidebar(force) {
  const shell = document.getElementById('appShell');
  if (!shell) return;
  const collapsed = typeof force === 'boolean'
    ? force
    : !shell.classList.contains('sidebar-collapsed');
  shell.classList.toggle('sidebar-collapsed', collapsed);
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch (_) { /* ignore */ }
}

function initSidebarCollapsed() {
  try {
    if (localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1') toggleSidebar(true);
  } catch (_) { /* ignore */ }
}

function syncChatResultOverlay() {
  const overlay = document.getElementById('chatResultOverlay');
  if (!overlay) return;
  const visible = ['qualityResultPanel', 'outlineResultPanel', 'chatComparePanel'].some((id) => {
    const el = document.getElementById(id);
    return el && !el.classList.contains('hidden');
  });
  overlay.classList.toggle('hidden', !visible);
}

function closeChatResultBackdrop(event) {
  if (event.target.id !== 'chatResultOverlay') return;
  closeQualityPanel();
  closeOutlinePanel();
  closeChatCompare();
}

function syncChatMetaFold() {
  const fold = document.getElementById('chatMetaFold');
  if (!fold) return;
  const conflict = !document.getElementById('chatTargetConflict')?.classList.contains('hidden');
  const beat = !document.getElementById('chatBeatPreview')?.classList.contains('hidden');
  fold.open = conflict || beat;
}

async function getChapterPlanTitle(num) {
  if (!num) return '';
  await ensurePlanData();
  const ch = dataCache.planByNum[num];
  return (ch?.title || '').trim();
}

function updateChatHints() {
  const hint = document.getElementById('chatSceneHint');
  const writeNum = getWriteChapterNum();
  const scenePart = state.currentSceneId
    ? `场景已选 · 第${state.currentChapter}章`
    : '建议先在 Plan 选中场景';
  if (hint) {
    hint.textContent = writeNum
      ? `${scenePart} · 写作目标：第 ${writeNum} 章`
      : scenePart;
  }

  const conflict = getWriteTargetConflict();
  const conflictEl = document.getElementById('chatTargetConflict');
  if (conflictEl) {
    if (conflict) {
      conflictEl.textContent =
        `⚠️ 当前场景在第 ${conflict.sceneCh} 章，写作目标为第 ${conflict.writeNum} 章。发送后将写入第 ${conflict.writeNum} 章（以写作目标为准）。`;
      conflictEl.classList.remove('hidden');
    } else {
      conflictEl.classList.add('hidden');
    }
  }

  const bar = document.getElementById('chatWriteTargetBar');
  if (bar) {
  ensurePlanData().then(() => {
    const planTitle = writeNum ? (dataCache.planByNum[writeNum]?.title || '') : '';
    const titlePart = planTitle ? ` · ${planTitle}` : '';
    bar.classList.toggle('chat-write-target-bar--warn', !!conflict);
    if (!writeNum) {
      bar.innerHTML = '<span class="chat-write-target-bar__label">将写入</span><span class="chat-write-target-bar__value">请先选择目标章</span>';
    } else if (conflict) {
      bar.innerHTML =
        `<span class="chat-write-target-bar__label">将写入</span>` +
        `<span class="chat-write-target-bar__value chat-write-target-bar__value--warn">第 ${writeNum} 章${escapeHtml(titlePart)}</span>` +
        `<span class="chat-write-target-bar__note">（场景在第 ${conflict.sceneCh} 章）</span>`;
    } else {
      bar.innerHTML =
        `<span class="chat-write-target-bar__label">将写入</span>` +
        `<span class="chat-write-target-bar__value">第 ${writeNum} 章${escapeHtml(titlePart)}</span>`;
    }
  });
  }
  syncChatMetaFold();
}

function loadSceneBeatIntoEditors(scene) {
  if (!scene) return;
  const beatEl = document.getElementById('beatEditor');
  if (beatEl) beatEl.value = scene.beat || '';
  const titleEl = document.getElementById('planSceneTitle');
  if (titleEl) titleEl.textContent = scene.title || '场景';
  const paceSel = document.getElementById('beatPaceSel');
  if (paceSel) paceSel.value = scene.pace || '中';
  const ea = scene.emotion_anchor || {};
  const targetEl = document.getElementById('beatEmotionTarget');
  const howEl = document.getElementById('beatEmotionHow');
  if (targetEl) targetEl.value = ea.target || '';
  if (howEl) howEl.value = ea.how || '';
}

function updateChatBeatPreview(scene) {
  const wrap = document.getElementById('chatBeatPreview');
  if (!wrap) return;
  if (!state.currentSceneId) {
    wrap.classList.add('hidden');
    return;
  }
  const found = getSceneFromCache(state.currentSceneId);
  const cached = scene || found?.scene;
  const title = (cached?.title || '').trim();
  const beatEl = document.getElementById('beatEditor');
  const beat = (beatEl?.value ?? cached?.beat ?? '').trim();
  if (!beat) {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  const titleEl = document.getElementById('chatBeatPreviewTitle');
  const bodyEl = document.getElementById('chatBeatPreviewBody');
  if (titleEl) titleEl.textContent = title ? `· ${title}` : '';
  if (bodyEl) bodyEl.textContent = beat;
  syncChatMetaFold();
}

function isBeatEditorDirty() {
  if (!state.currentSceneId) return false;
  const found = getSceneFromCache(state.currentSceneId);
  const scene = found?.scene;
  if (!scene) return false;
  const beat = document.getElementById('beatEditor')?.value ?? '';
  const pace = document.getElementById('beatPaceSel')?.value || '中';
  const target = document.getElementById('beatEmotionTarget')?.value.trim() || '';
  const how = document.getElementById('beatEmotionHow')?.value.trim() || '';
  const ea = scene.emotion_anchor || {};
  return (
    beat !== (scene.beat || '')
    || pace !== (scene.pace || '中')
    || target !== (ea.target || '')
    || how !== (ea.how || '')
  );
}

function closeOtherResultPanels(except = '') {
  if (except !== 'quality') closeQualityPanel();
  if (except !== 'outline') closeOutlinePanel();
  if (except !== 'compare') closeChatCompare();
}

const QUALITY_RESULT_META = {
  continuity: {
    match: (t) => t.includes('连续性检查'),
    guide: '发现问题时对照修改：<b>数字/专名/外貌</b> → <code>plot_threads_locked.md</code>（细节钉子）；<b>伏笔</b> → <code>plot_threads_active.md</code>；<b>人设</b> → <code>char_static.md</code> / <code>char_dynamic.md</code>；<b>正文措辞</b> → 写作模式本章。',
    actions: ['plot_threads_locked', 'plot_threads_active', 'char_static', 'char_dynamic'],
  },
  detail: {
    match: (t) => t.includes('细节提取'),
    guide: '提取的是<b>细节钉子</b>，已自动追加到 <code>plot_threads_locked.md</code>（可在侧栏「质量记录」回看）。',
    actions: ['plot_threads_locked'],
  },
  character: {
    match: (t) => t.includes('人物检查'),
    guide: '人设问题改 <code>char_static.md</code>（性格锚点）或 <code>char_dynamic.md</code>（当前状态）；正文问题回写作模式改本章。',
    actions: ['char_static', 'char_dynamic'],
  },
  observe: {
    match: (t) => t.includes('角色观察'),
    guide: '有变更的提案已<b>自动写入</b> char_static / char_dynamic。侧栏「质量记录」可回看完整报告。',
    actions: ['char_static', 'char_dynamic'],
  },
  repetition: {
    match: (t) => t.includes('套话') || t.includes('重复检查'),
    guide: '套话问题请直接在<b>写作模式</b>编辑对应章节正文，或调整 <code>style.md</code> 禁用词。',
    actions: ['style'],
  },
  reader: {
    match: (t) => t.includes('读者审阅') || t.includes('读者视角'),
    guide: '阅读体验问题请改<b>章节正文</b>或 Plan Beat；审阅不会自动写档案。',
    actions: [],
  },
  editor: {
    match: (t) => t.includes('编辑审阅') || t.includes('编辑视角'),
    guide: '编辑建议请对照 <code>world.md</code> 节拍与 Plan；改稿后建议重新「一键全查」对比。',
    actions: ['world'],
  },
  quality_full: {
    match: (t) => t.includes('一键全查') || t.includes('质量审阅'),
    guide: '本报告为只读诊断。改完请点「本章定稿」同步概述/观察/钉子，或到质量页重新全查对比。',
    actions: [],
  },
  batch_world_review: {
    match: (t) => t.includes('世界审阅') || t.includes('世界批次审阅'),
    guide: '按<b>读者连读</b>诊断本世界。改稿后重新「审阅本世界」；确认无误再「定稿本世界」。',
    actions: [],
  },
  batch_world_finalize: {
    match: (t) => t.includes('世界定稿') || t.includes('世界批次定稿'),
    guide: '已逐章写入概述/观察/钉子。若报告有 ⚠️ 截断提示，请检查质量记录全文或提高 .env 中的 BATCH token 上限。',
    actions: ['summaries_recent', 'plot_threads_active'],
  },
  world_remediate: {
    match: (t) => t.includes('世界闭环'),
    guide: '正文与档案已自动写入。满意可点「全部接受」；不满意可「撤销某章」从快照恢复（不调 API）。',
    actions: [],
  },
  world_batch_generate: {
    match: (t) => t.includes('世界批量生成') || t.includes('世界生成'),
    guide: '已按 plan Beat 写入各章。建议通读后跑「女频审阅+改稿」或「世界闭环」，再「仅同步档案」。',
    actions: ['world'],
  },
  deconstruct: {
    match: (t) => t.includes('参考拆文') || t.includes('拆解报告'),
    guide: '对照报告调整 Plan Beat 或 world 节拍；可回到规划模式修改下章结构。',
    actions: ['world'],
  },
  female_fiction_review: {
    match: (t) => t.includes('女频审阅') || t.includes('女频直改稿'),
    guide: '直改稿：先预览全文，满意后点「采纳并同步档案」写回章节并更新全局文件。',
    actions: ['summaries_recent', 'char_dynamic', 'plot_threads_locked', 'plot_threads_active'],
  },
  female_fiction_accept: {
    match: (t) => t.includes('女频采纳') || t.includes('女频改稿采纳'),
    guide: '章节与档案已写入。可在全局文件中核对概述/观察/钉子。',
    actions: ['summaries_recent', 'char_dynamic', 'plot_threads_locked', 'plot_threads_active'],
  },
  pacing: {
    match: (t) => t.includes('爽点检查'),
    guide: '节奏/爽点问题对照 <code>world.md</code> 节拍表与 Plan Beat，在规划或写书对话中调整下章走向。',
    actions: ['world'],
  },
};

function resolveQualityMeta(title, hint = '') {
  for (const meta of Object.values(QUALITY_RESULT_META)) {
    if (meta.match(title)) return { ...meta, hint };
  }
  return {
    guide: hint || '请根据检查结果，到对应全局文件或本章正文修改。',
    actions: [],
  };
}

function renderQualityResultActions(fileKeys, customButtons) {
  const host = document.getElementById('qualityResultActions');
  if (!host) return;
  clearEl(host);
  const files = fileKeys || [];
  const extras = customButtons || [];
  if (!files.length && !extras.length) {
    host.classList.add('hidden');
    return;
  }
  host.classList.remove('hidden');
  for (const key of files) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm';
    btn.textContent = `打开 ${globalFileLabel(key).split(' ')[0]}`;
    btn.addEventListener('click', () => openGlobalFromQuality(key));
    host.appendChild(btn);
  }
  for (const spec of extras) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = spec.className || 'btn btn-sm';
    btn.textContent = spec.label || '操作';
    btn.addEventListener('click', () => {
      if (typeof spec.onClick === 'function') spec.onClick();
    });
    host.appendChild(btn);
  }
}

async function openGlobalFromQuality(fileKey) {
  closeQualityPanel();
  setState({ mode: 'write', sidebar: 'global' }, 'full');
  await openGlobal(fileKey);
  toast(`已打开 ${globalFileLabel(fileKey)}，改完请点顶部「保存」`);
}

function showQualityResult(title, body, hint = '', options = {}) {
  closeOtherResultPanels('quality');
  _qualityResultText = body || '';
  const panel = document.getElementById('qualityResultPanel');
  if (!panel) return;
  const meta = resolveQualityMeta(title, hint);
  document.getElementById('qualityResultTitle').textContent = title;
  const timeEl = document.getElementById('qualityResultTime');
  if (timeEl) {
    if (options.createdAt) {
      timeEl.innerHTML = timeBadgeHtml(
        options.createdAt,
        options.persisted ? 'ok' : 'muted',
      );
    } else {
      timeEl.textContent = '';
    }
  }
  const guideEl = document.getElementById('qualityResultGuide');
  if (guideEl) {
    let guideHtml = options.guide || meta.guide;
    const warns = options.warnings || [];
    if (options.outputTruncated || options.inputTruncated) {
      warns.unshift('部分 API 回复或输入可能被截断，请对照正文通读；可在 .env 调高 NOVEL_BATCH_REVIEW_* 上限');
    }
    if (warns.length) {
      guideHtml += `<div class="quality-result-trunc-warn">${warns.map((w) => escapeHtml(w)).join('<br>')}</div>`;
    }
    if (options.reportChars) {
      guideHtml += `<div class="muted" style="margin-top:6px;font-size:11px">报告约 ${options.reportChars.toLocaleString()} 字 · 可点「复制报告」或侧栏质量记录回看</div>`;
    }
    guideEl.innerHTML = guideHtml;
  }
  const bodyEl = document.getElementById('qualityResultBody');
  if (bodyEl) bodyEl.textContent = body || '（无内容）';
  const scrollEl = document.getElementById('qualityResultScroll');
  if (scrollEl) scrollEl.scrollTop = 0;
  renderQualityResultActions(options.actions || meta.actions, options.customButtons);
  panel.classList.remove('hidden');
  syncChatResultOverlay();
}

function closeQualityPanel() {
  document.getElementById('qualityResultPanel')?.classList.add('hidden');
  syncChatResultOverlay();
}

function copyQualityResult() {
  if (!_qualityResultText) return toast('无内容可复制');
  navigator.clipboard.writeText(_qualityResultText).then(
    () => toast('已复制到剪贴板'),
    () => toast('复制失败，请手动选择文本'),
  );
}

async function goToChatFromPlan() {
  if (state.currentSceneId) {
    await saveBeat();
  }
  const found = state.currentSceneId ? getSceneFromCache(state.currentSceneId) : null;
  const sceneCh = found?.chapterNum || state.currentChapter;
  await setMode('chat');
  if (sceneCh > 0) {
    await setWriteChapterTarget(sceneCh);
  }
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
async function setMode(mode) {
  const prev = state.mode;
  if (prev === 'plan' && mode === 'chat' && state.currentSceneId && isBeatEditorDirty()) {
    await saveBeat({ silent: true });
  }
  const patch = { mode };
  if (mode === 'chat' && prev !== 'chat') patch.sidebar = 'chats';
  setState(patch, 'full');
  if (mode === 'chat') {
    updateChatBeatPreview();
    updateChatHints();
    updateChatReadingModeBtn();
    updateChatReadingModeBanner();
    requestAnimationFrame(() => _logMaintainUiState(`setMode:${mode}`));
  }
  if (mode === 'write') {
    requestAnimationFrame(() => _logMaintainUiState(`setMode:${mode}`));
  }
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
  const labels = { scenes: '场景', codex: '条目', freechats: '话题', chats: '', global: '', toc: '', plan: '场景' };
  const key = state.sidebar;
  if (key === 'chats' || key === 'global' || key === 'toc') {
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
  else if (state.sidebar === 'freechats') createFreeChatThread();
}

function syncFinalizeOnSavePrefUi() {
  const cb = document.getElementById('promptFinalizeOnSave');
  if (cb) cb.checked = shouldPromptFinalizeOnSave();
}

function saveFinalizeOnSavePref() {
  const cb = document.getElementById('promptFinalizeOnSave');
  if (!cb) return;
  try {
    localStorage.setItem(FINALIZE_ON_SAVE_KEY, cb.checked ? '1' : '0');
  } catch { /* ignore */ }
  toast(cb.checked ? '已开启：保存后询问定稿' : '已关闭：保存后不再询问定稿');
}

function toggleSettings() {
  const drawer = document.getElementById('settingsDrawer');
  const opening = drawer.classList.contains('hidden');
  drawer.classList.toggle('hidden');
  document.getElementById('overlay').classList.toggle('hidden');
  if (opening) {
    syncFinalizeOnSavePrefUi();
    loadHistoryPanel();
  }
}

async function loadHistoryPanel() {
  const host = document.getElementById('historyPanel');
  if (!host) return;
  host.textContent = '加载中…';
  try {
    const fileKey = document.getElementById('historyFileKey')?.value || '';
    const q = fileKey ? `?file_key=${encodeURIComponent(fileKey)}&limit=30` : '?limit=30';
    const data = await api(`/history${q}`);
    const entries = data.entries || [];
    if (!entries.length) {
      host.innerHTML = '<p class="muted">暂无变更记录</p>';
      return;
    }
    host.innerHTML = entries.map((e) => {
      const isRevert = String(e.source || '').includes('revert');
      const timeVariant = isRevert ? 'err' : 'ok';
      return (
        `<div class="history-entry">` +
        `<div class="history-entry__head">` +
        `<span class="history-entry__file">${escapeHtml(e.file_key || '')}</span>` +
        timeBadgeHtml(e.ts, timeVariant) +
        `</div>` +
        `<div class="history-entry__meta">${escapeHtml(e.source || '')} · 第${e.chapter_num || '?'}章</div>` +
        `<div class="history-entry__body">${escapeHtml(e.after_preview || '')}</div>` +
        `<button type="button" class="history-entry__btn" data-history-id="${escapeHtml(e.id)}" data-file-key="${escapeHtml(e.file_key || '')}" data-chapter-num="${e.chapter_num || 0}" onclick="revertHistoryEntry(this.dataset.historyId, this.dataset.fileKey, this.dataset.chapterNum)">撤销此次</button>` +
        `</div>`
      );
    }).join('');
  } catch (e) {
    host.textContent = e.message || '加载失败';
  }
}

async function revertHistoryEntry(entryId, fileKey = '', chapterNum = 0) {
  if (!entryId || !confirm('撤销此次档案变更？文件将恢复为修改前内容。')) return;
  try {
    const ch = parseInt(chapterNum, 10) || undefined;
    await api('/history/revert', {
      method: 'POST',
      body: JSON.stringify({ entry_id: entryId, chapter_num: ch }),
    });
    toast('已撤销');
    invalidateCache(['codex', 'plan']);
    await loadHistoryPanel();
    fetchGuideStatus(true).then(() => renderGuideHints(state.mode));
    if (state.editTarget?.type === 'global' && fileKey && state.editTarget.name === fileKey) {
      await openGlobal(fileKey);
    }
    if (fileKey === 'plan') {
      invalidatePlanCache();
      scheduleRender({ main: state.mode === 'plan', sidebar: state.sidebar === 'scenes' });
    }
  } catch (e) {
    toast(e.message || '撤销失败');
  }
}

async function refreshHistoryBaseline() {
  if (!confirm('刷新第 0 章基准快照？\n\n将用当前所有追踪文件覆盖 baseline（慎用）。')) return;
  try {
    await api('/history/baseline', { method: 'POST' });
    toast('基准快照已刷新');
    await loadHistoryPanel();
  } catch (e) {
    toast(e.message || '刷新失败');
  }
}

// ── Sidebar: full + partial ─────────────────────
async function refreshSidebarFull() {
  const body = document.getElementById('sidebarBody');
  const q = (document.getElementById('sidebarSearch').value || '').toLowerCase();
  if (state.sidebar === 'toc') await renderTocSidebar(body, q);
  else if (state.sidebar === 'scenes') await renderScenesSidebar(body, q);
  else if (state.sidebar === 'codex') await renderCodexSidebar(body, q);
  else if (state.sidebar === 'chats') await renderChatsSidebar(body);
  else if (state.sidebar === 'quality') await renderQualitySidebar(body);
  else if (state.sidebar === 'freechats') await renderFreeChatsSidebar(body);
  else if (state.sidebar === 'global') await renderGlobalSidebar(body);
}

function applySidebarPartial({ type, sceneId, patch }) {
  if (type === 'scene') updateSceneSidebarItem(sceneId, patch);
}

function makeSceneSidebarItem(scene, chapterNum) {
  const el = cloneTplEl('tpl-scene-sidebar-item');
  el.dataset.sceneId = scene.id;
  el.classList.toggle('active', state.currentSceneId === scene.id);
  const title = el.querySelector('.title');
  const meta = el.querySelector('.meta');
  const textWrap = document.createElement('div');
  textWrap.className = 'scene-sidebar-text';
  title.parentNode.insertBefore(textWrap, title);
  textWrap.appendChild(title);
  textWrap.appendChild(meta);
  title.textContent = `${scene.done ? '✓ ' : ''}${scene.title}`;
  meta.textContent = (scene.beat || '').slice(0, 60) || '无 beat';
  const delBtn = document.createElement('button');
  delBtn.type = 'button';
  delBtn.className = 'scene-sidebar-del btn btn-sm btn-ghost';
  delBtn.textContent = '×';
  delBtn.title = '删除场景';
  delBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    deleteScene(scene.id, chapterNum);
  });
  el.appendChild(delBtn);
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
  if (chapters.length) {
    const addRow = document.createElement('div');
    addRow.className = 'sidebar-new-chapter';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm';
    btn.style.marginTop = '10px';
    btn.textContent = '+ 新建章节';
    btn.addEventListener('click', newChapter);
    addRow.appendChild(btn);
    body.appendChild(addRow);
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

function pairChatTurns(messages) {
  const turns = [];
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role !== 'user') continue;
    const turn = { userIdx: i, user: messages[i].content || '', aiIdx: null, ai: '' };
    if (i + 1 < messages.length && messages[i + 1].role === 'assistant') {
      turn.aiIdx = i + 1;
      turn.ai = messages[i + 1].content || '';
    }
    turns.push(turn);
  }
  return turns;
}

const TOC_COLLAPSE_KEY = 'novel_toc_collapsed';

function loadTocCollapsed() {
  try {
    const raw = JSON.parse(localStorage.getItem(TOC_COLLAPSE_KEY) || '{}');
    return { worlds: raw.worlds || {}, chapters: raw.chapters || {}, chatWorlds: raw.chatWorlds || {}, chatChapters: raw.chatChapters || {} };
  } catch {
    return { worlds: {}, chapters: {}, chatWorlds: {}, chatChapters: {} };
  }
}

function saveTocCollapsed(data) {
  localStorage.setItem(TOC_COLLAPSE_KEY, JSON.stringify(data));
}

function isTocCollapsed(bucket, key, { forceOpen = false } = {}) {
  if (forceOpen || qForceExpand) return false;
  const data = loadTocCollapsed();
  if (data[bucket][key] === undefined) {
    return bucket === 'chapters' || bucket === 'chatChapters';
  }
  return !!data[bucket][key];
}

let qForceExpand = false;

function toggleTocCollapsed(bucket, key) {
  const data = loadTocCollapsed();
  data[bucket][key] = !isTocCollapsed(bucket, key);
  saveTocCollapsed(data);
  scheduleRender({ sidebar: true });
}

function parseChapterWorld(chapterTitle, defaultWorld = '本书') {
  const t = (chapterTitle || '').trim();
  const m = t.match(/^(世界[一二三四五六七八九十百千万\d]+)[·・\s]+(.+)$/);
  if (m) return { world: m[1], shortTitle: m[2].trim() };
  const stripped = t.replace(/^第\d+章[·・\s]*/, '').trim();
  return { world: defaultWorld || '本书', shortTitle: stripped || t || '未命名' };
}

function codexSubtitleForWorld(worldKey, entries = []) {
  const needle = (worldKey || '').replace(/世界/, '');
  const hit = entries.find(e => e.name && (e.name.includes(worldKey) || (needle && e.name.includes(needle))));
  if (!hit) return '';
  const name = hit.name.replace(/_/g, '·');
  const parts = name.split('·').slice(1);
  return parts.join('·') || '';
}

function buildWorldChapterTree(chapters, planByNum, defaultWorld) {
  const worlds = new Map();
  for (const ch of chapters) {
    const plan = planByNum[ch.num] || {};
    const fullTitle = plan.title || `第${ch.num}章`;
    const { world, shortTitle } = parseChapterWorld(fullTitle, defaultWorld);
    if (!worlds.has(world)) worlds.set(world, []);
    worlds.get(world).push({ ...ch, plan, fullTitle, shortTitle });
  }
  return [...worlds.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh'));
}

function extractTurnChapterNum(userText) {
  const m = (userText || '').match(/【当前章节：第(\d+)章】/);
  return m ? parseInt(m[1], 10) : null;
}

function extractChapterTitleFromReply(text) {
  const raw = text || '';
  const m = raw.match(/^【章节标题】\s*(.+?)(?:\n\n|\n)/s);
  if (!m) return { title: '', body: raw };
  const title = m[1].trim().split('\n')[0].trim();
  const body = raw.slice(m[0].length).trim();
  return { title, body };
}

function extractInstructionText(userText) {
  let text = userText || '';
  const idx = text.indexOf('【写作指令】');
  if (idx >= 0) text = text.slice(idx + '【写作指令】'.length);
  text = text.replace(/^[\s\n]+/, '');
  const beatBlock = /【场景指令 Scene Beat】\s*\n[\s\S]*?(?:\n\n|$)/;
  const beatMatch = text.match(/【场景指令 Scene Beat】\s*\n([^\n]+)/);
  const beatLine = beatMatch ? beatMatch[1].trim() : '';
  text = text.replace(beatBlock, '').trim();
  const firstLine = text.split('\n').map(l => l.trim()).find(Boolean) || '';
  return { instruction: firstLine, beatLine };
}

function extractUserMessageParts(userText) {
  const raw = (userText || '').trim();
  const m = raw.match(/^【当前章节：第(\d+)章】\s*\n+([\s\S]*?)\n+【写作指令】\s*\n([\s\S]*)$/);
  if (m) {
    return {
      chapterNum: parseInt(m[1], 10),
      chapterBody: m[2].trim(),
      instruction: m[3].trim(),
      hasChapter: true,
    };
  }
  return { chapterNum: null, chapterBody: '', instruction: raw, hasChapter: false };
}

function formatInstructionDisplay(userText) {
  const parts = extractUserMessageParts(userText);
  let text = parts.instruction;
  let beatText = '';
  const beatMatch = text.match(/【场景指令 Scene Beat】\s*\n([\s\S]*?)(?:\n\n|$)/);
  if (beatMatch) {
    beatText = beatMatch[1].trim();
    text = text.replace(/【场景指令 Scene Beat】\s*\n[\s\S]*?(?:\n\n|$)/, '').trim();
  }
  const { beatLine } = extractInstructionText(text);
  return { ...parts, instruction: text, beatLine, beatText };
}

const CHAT_READING_MODE_KEY = 'novel_writer_chat_reading_mode';

function getChatScrollEl() {
  return document.querySelector('#viewChat .chat-scroll');
}

function getFreeChatScrollEl() {
  return document.querySelector('#viewFree .chat-scroll');
}

function scrollChatToBottom(behavior = 'auto') {
  const sc = getChatScrollEl();
  if (!sc) return;
  requestAnimationFrame(() => {
    sc.scrollTo({ top: sc.scrollHeight, behavior });
  });
}

function scrollFreeChatToBottom(behavior = 'auto') {
  const sc = getFreeChatScrollEl();
  if (!sc) return;
  requestAnimationFrame(() => {
    const top = sc.scrollHeight;
    sc.scrollTo({ top, behavior });
    // #region agent log
    _dbgApiLog('app.js:scrollFreeChatToBottom', 'free chat scroll', {
      scrollTop: sc.scrollTop,
      scrollHeight: sc.scrollHeight,
      clientHeight: sc.clientHeight,
      behavior,
    }, 'H2');
    // #endregion
  });
}

function scrollChatToEl(el, block = 'end') {
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block });
}

function isChatReadingMode() {
  return document.getElementById('viewChat')?.classList.contains('chat-reading-mode');
}

function updateChatReadingModeBanner() {
  const banner = document.getElementById('chatReadingModeBanner');
  if (!banner) return;
  const on = isChatReadingMode();
  banner.classList.toggle('hidden', !on);
}

function toggleChatReadingMode(force) {
  const view = document.getElementById('viewChat');
  if (!view) return;
  const on = typeof force === 'boolean' ? force : !view.classList.contains('chat-reading-mode');
  view.classList.toggle('chat-reading-mode', on);
  try {
    localStorage.setItem(CHAT_READING_MODE_KEY, on ? '1' : '0');
  } catch (_) { /* ignore */ }
  updateChatReadingModeBtn();
  updateChatReadingModeBanner();
  if (on) {
    toast('阅读模式：章后维护按钮已隐藏，点顶栏「退出阅读模式」恢复');
  }
  _logMaintainUiState(`readingMode:${on}`);
  if (!on) document.getElementById('chatInstruction')?.focus();
}

function initChatReadingMode() {
  try {
    if (localStorage.getItem(CHAT_READING_MODE_KEY) === '1') toggleChatReadingMode(true);
  } catch (_) { /* ignore */ }
  updateChatReadingModeBanner();
}

function updateChatReadingModeBtn() {
  const btn = document.getElementById('chatReadingModeBtn');
  if (!btn) return;
  const on = isChatReadingMode();
  btn.textContent = on ? '显示输入' : '阅读模式';
  btn.classList.toggle('active', on);
}

function buildChatTurnCard(turn, turnIndex, { appended = [], highlight = false, pending = false } = {}) {
  const card = cloneTplEl('tpl-chat-turn');
  card.dataset.turnNum = String(turnIndex);
  if (highlight) card.classList.add('highlight');

  const labelInfo = deriveChatTurnLabel(turn, turnIndex);
  card.querySelector('.msg-turn__title').textContent = `第 ${turnIndex + 1} 轮 · ${labelInfo.title}`;

  card.querySelector('.msg-turn__copy-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    copyChatTurn(turn);
  });
  card.querySelector('.msg-turn__compare-btn')?.addEventListener('click', (e) => {
    e.stopPropagation();
    openChatTurnCompare(turnIndex);
  });
  card.addEventListener('click', (e) => {
    if (e.target.closest('details') || e.target.closest('button')) return;
    openChatTurnCompare(turnIndex);
  });

  const display = formatInstructionDisplay(turn.user);
  const instrEl = card.querySelector('.msg-turn__instruction');
  const chunks = [];
  if (display.beatText) chunks.push(`【Scene Beat】\n${display.beatText}`);
  else if (display.beatLine) chunks.push(`【Beat】${display.beatLine}`);
  if (display.instruction) chunks.push(display.instruction);
  instrEl.textContent = chunks.join('\n\n') || '（空指令）';

  const chapterFold = card.querySelector('.msg-chapter-fold');
  if (display.hasChapter && display.chapterBody) {
    chapterFold.classList.remove('hidden');
    chapterFold.querySelector('.msg-chapter-fold__summary').textContent =
      `附带第 ${display.chapterNum} 章正文（${display.chapterBody.length.toLocaleString()} 字，点击展开）`;
    chapterFold.querySelector('.msg-chapter-fold__body').textContent = display.chapterBody;
  }

  const aiBlock = card.querySelector('.msg-turn__ai');
  const pendingEl = card.querySelector('.msg-turn__pending');
  const aiLabel = aiBlock.querySelector('.msg-turn__ai-label');
  if (turn.ai || turn.aiIdx != null) {
    let aiText = turn.ai || '';
    if (aiText) {
      const parsed = extractChapterTitleFromReply(aiText);
      if (parsed.title) aiLabel.textContent = `AI 回复 · ${parsed.title}`;
      aiText = parsed.body || aiText;
    } else {
      aiLabel.textContent = 'AI 回复';
    }
    if (turn.aiIdx != null && appended.includes(turn.aiIdx)) {
      aiLabel.textContent += ' · ✓ 已写入章节';
    }
    aiBlock.querySelector('.msg-body').textContent = aiText || '（无内容）';
    aiBlock.classList.remove('hidden');
    pendingEl.classList.add('hidden');
  } else if (pending) {
    pendingEl.classList.remove('hidden');
    aiBlock.classList.add('hidden');
  } else {
    pendingEl.classList.add('hidden');
    aiBlock.classList.add('hidden');
  }

  return card;
}

function appendOptimisticTurn(instruction, scene_beat = '') {
  const parts = [];
  if (scene_beat.trim()) parts.push(`【场景指令 Scene Beat】\n${scene_beat.trim()}`);
  if (instruction.trim()) parts.push(instruction.trim());
  const log = document.getElementById('chatMessages');
  if (!log) return;
  log.querySelector('.nc-empty')?.remove();
  const idx = pairChatTurns(dataCache.chat.messages || []).length;
  const card = buildChatTurnCard({ user: parts.join('\n\n'), ai: '' }, idx, { pending: true });
  card.dataset.optimistic = '1';
  log.appendChild(card);
  scrollChatToBottom('smooth');
}

function beginStreamOnLastTurn() {
  removeTypingIndicator();
  const log = document.getElementById('chatMessages');
  if (!log) return null;
  const card = log.querySelector('[data-optimistic="1"]') || log.querySelector('.msg-turn:last-child');
  if (!card) return appendStreamBubble('chatMessages');

  card.querySelector('.msg-turn__pending')?.classList.add('hidden');
  const ai = card.querySelector('.msg-turn__ai');
  ai?.classList.remove('hidden');
  const label = ai?.querySelector('.msg-turn__ai-label');
  if (label) label.textContent = 'AI 回复';
  const body = ai?.querySelector('.msg-body');
  if (body) {
    body.id = 'streamBubble';
    body.textContent = '';
    scrollChatToBottom('auto');
    return body;
  }
  return appendStreamBubble('chatMessages');
}

function deriveChatTurnLabel(turn, turnIndex) {
  const chapterNum = extractTurnChapterNum(turn.user);
  const { instruction, beatLine } = extractInstructionText(turn.user);
  let title = instruction;
  if (!title || title.length > 36) {
    title = instruction ? instruction.slice(0, 34) + '…' : `写作指令 ${turnIndex + 1}`;
  }
  const metaParts = [];
  if (chapterNum) metaParts.push(`第 ${chapterNum} 章`);
  if (beatLine) metaParts.push(beatLine.slice(0, 28) + (beatLine.length > 28 ? '…' : ''));
  if (turn.aiIdx != null) metaParts.push('已有 AI 回复');
  return {
    title,
    meta: metaParts.join(' · ') || '写书对话',
    chapterNum: chapterNum ?? 0,
  };
}

function makeFoldRow({ level, label, collapsed, active, bucket, foldKey, onActivate }) {
  const row = document.createElement('div');
  row.className = `toc-fold-head toc-level-${level}${active ? ' active' : ''}`;
  const chevron = document.createElement('button');
  chevron.type = 'button';
  chevron.className = 'toc-chevron';
  chevron.setAttribute('aria-label', collapsed ? '展开' : '折叠');
  chevron.textContent = collapsed ? '▶' : '▼';
  chevron.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleTocCollapsed(bucket, foldKey);
  });
  const labelEl = document.createElement('span');
  labelEl.className = 'toc-fold-label';
  labelEl.textContent = label;
  if (onActivate) {
    labelEl.addEventListener('click', (e) => {
      e.stopPropagation();
      onActivate();
    });
  }
  row.appendChild(chevron);
  row.appendChild(labelEl);
  return row;
}

async function renderTocSidebar(body, q = '') {
  qForceExpand = !!q;
  await ensurePlanData();
  const { chapters, planByNum } = dataCache;
  let defaultWorld = '本书';
  let codexEntries = [];
  const statsByNum = {};
  try {
    const [st, proj, codex] = await Promise.all([
      api('/stats'),
      api('/project'),
      api('/codex-entries'),
    ]);
    defaultWorld = proj.world_label || defaultWorld;
    codexEntries = codex.entries || [];
    for (const c of st.chapters || []) statsByNum[c.num] = c.chars;
  } catch {
    /* ignore */
  }

  clearEl(body);
  if (!chapters.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.innerHTML = '尚无章节<br><button type="button" class="btn btn-sm btn-primary" style="margin-top:8px">+ 创建第一章</button>';
    empty.querySelector('button')?.addEventListener('click', newChapter);
    body.appendChild(empty);
    qForceExpand = false;
    return;
  }

  const editingChapter =
    state.mode === 'write' &&
    (!state.editTarget || state.editTarget.type === 'chapter');
  const worldTree = buildWorldChapterTree(chapters, planByNum, defaultWorld);

  for (const [worldKey, worldChapters] of worldTree) {
    const sub = codexSubtitleForWorld(worldKey, codexEntries);
    const worldLabel = sub ? `${worldKey} · ${sub}` : worldKey;
    const worldFoldKey = worldKey;
    const worldCollapsed = isTocCollapsed('worlds', worldFoldKey, {
      forceOpen: worldChapters.some(c => c.num === state.currentChapter),
    });

    const worldMatches = !q || worldLabel.toLowerCase().includes(q.toLowerCase());
    const chapterMatches = worldChapters.some(ch => {
      const blob = `${ch.shortTitle} ${ch.fullTitle}`.toLowerCase();
      return blob.includes(q.toLowerCase()) || (ch.plan.scenes || []).some(s =>
        `${s.title} ${s.beat || ''}`.toLowerCase().includes(q.toLowerCase()));
    });
    if (q && !worldMatches && !chapterMatches) continue;

    body.appendChild(makeFoldRow({
      level: 0,
      label: worldLabel,
      collapsed: worldCollapsed,
      active: worldChapters.some(c => c.num === state.currentChapter),
      bucket: 'worlds',
      foldKey: worldFoldKey,
    }));

    if (worldCollapsed) continue;

    for (const ch of worldChapters) {
      const chars = statsByNum[ch.num] || 0;
      const planned = ch.planned_only;
      const scenes = ch.plan.scenes || [];
      const chapterFoldKey = `${worldKey}:${ch.num}`;
      const chapterLabel = planned
        ? `第 ${ch.num} 章 · ${ch.shortTitle}（规划中）`
        : `第 ${ch.num} 章 · ${ch.shortTitle}（${chars.toLocaleString()} 字）`;

      const sceneHits = scenes.filter(s => {
        if (!q) return true;
        const blob = `${s.title} ${s.beat || ''}`.toLowerCase();
        return blob.includes(q.toLowerCase());
      });
      if (q && !chapterLabel.toLowerCase().includes(q.toLowerCase()) && !sceneHits.length) continue;

      const chapterCollapsed = isTocCollapsed('chapters', chapterFoldKey, {
        forceOpen: ch.num === state.currentChapter,
      });

      body.appendChild(makeFoldRow({
        level: 1,
        label: chapterLabel,
        collapsed: chapterCollapsed,
        active: editingChapter && state.currentChapter === ch.num,
        bucket: 'chapters',
        foldKey: chapterFoldKey,
        onActivate: () => openChapterFromToc(ch.num, planned),
      }));

      if (chapterCollapsed) continue;

      const list = scenes.filter(s => !q || sceneHits.includes(s));
      for (const scene of list) {
        const el = cloneTplEl('tpl-scene-sidebar-item');
        el.classList.add('toc-scene-item');
        el.dataset.sceneId = scene.id;
        if (state.mode === 'plan' && state.currentSceneId === scene.id) el.classList.add('active');
        el.querySelector('.title').textContent = `${scene.done ? '✓ ' : ''}${scene.title}`;
        el.querySelector('.meta').textContent = '';
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          openSceneFromToc(ch.num, scene.id);
        });
        body.appendChild(el);
      }
      if (!list.length && !planned) {
        const hint = document.createElement('div');
        hint.className = 'toc-empty-hint';
        hint.textContent = '（无场景，去规划添加）';
        body.appendChild(hint);
      }
    }
  }
  if (chapters.length && !q) {
    const addRow = document.createElement('div');
    addRow.className = 'sidebar-new-chapter';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-primary';
    btn.style.marginTop = '10px';
    btn.textContent = '+ 新建章节';
    btn.addEventListener('click', newChapter);
    addRow.appendChild(btn);
    body.appendChild(addRow);
  }
  qForceExpand = false;
}

async function openChapterFromToc(num, planned) {
  if (planned) {
    setState({ mode: 'plan', currentChapter: num, sidebar: 'toc' }, 'full');
    toast(`第 ${num} 章尚在规划，已打开场景看板`);
    return;
  }
  if (state.mode !== 'write') setState({ mode: 'write', sidebar: 'toc' }, 'chrome');
  await openChapter(num);
  if (state.sidebar === 'toc') scheduleRender({ sidebar: true });
}

async function openSceneFromToc(chapterNum, sceneId) {
  if (state.mode === 'chat') {
    await selectScene(sceneId, chapterNum);
    updateChatHints();
    scheduleRender({ sidebar: true });
    return;
  }
  setState({ mode: 'plan', currentChapter: chapterNum, sidebar: 'toc' }, 'chrome');
  await selectScene(sceneId, chapterNum);
  scheduleRender({ main: true, sidebar: true });
}

function invalidateQualityCache() {
  dataCache.quality = { entries: [], loadedAt: 0 };
}

async function ensureQualityLog(force = false) {
  const age = Date.now() - (dataCache.quality.loadedAt || 0);
  if (!force && dataCache.quality.entries.length && age < 15000) {
    return dataCache.quality.entries;
  }
  const { entries } = await api('/quality/log?limit=80');
  dataCache.quality = { entries: entries || [], loadedAt: Date.now() };
  return dataCache.quality.entries;
}

async function openQualityLogEntry(entryId) {
  const row = await api(`/quality/log/${encodeURIComponent(entryId)}`);
  const ch = row.chapter_num ? `第 ${row.chapter_num} 章` : '';
  const title = `${row.label || '质量记录'}${ch ? ` · ${ch}` : ''}`;
  const hint = row.persisted_detail || row.summary || '';
  if (state.mode !== 'chat' && state.mode !== 'quality') await setMode('chat');
  const extra = row.extra || {};
  const pending = extra.pending_accept && !row.persisted;
  showQualityResult(title, row.body || '', hint, {
    createdAt: row.created_at,
    persisted: row.persisted,
    guide: pending
      ? '通读改稿全文后，点「采纳并同步档案」写回章节并更新全局文件。'
      : undefined,
    customButtons: pending ? femaleFictionAcceptButtons(entryId) : [],
  });
  if (state.mode !== 'quality') {
    setState({ sidebar: 'quality' }, 'sidebar');
  }
}

function femaleFictionAcceptButtons(logId) {
  if (!logId) return [];
  return [
    {
      label: '✅ 采纳并同步档案',
      className: 'btn btn-sm btn-primary',
      onClick: () => acceptFemaleFictionRewrite(logId),
    },
  ];
}

async function acceptFemaleFictionRewrite(logId) {
  if (!logId) return toast('无待采纳记录');
  if (!confirm('采纳改稿：写回章节文件，并同步概述/观察/钉子/伏笔到全局档案？')) return;
  await runWithLoading(async () => {
    const r = await api(
      '/review/female-fiction/accept',
      {
        method: 'POST',
        body: JSON.stringify({ log_id: logId, sync_archive: true }),
      },
      QUALITY_FULL_TIMEOUT_MS,
    );
    invalidateCache(['chapters', 'plan', 'quality']);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    const hint = r.archive_synced
      ? `✅ 第 ${r.chapter_num} 章已写回${r.chapter_title ? `（${r.chapter_title}）` : ''}，全局档案已同步。`
      : `⚠️ 章节已写回，但档案同步未完成${r.archive_errors?.length ? '：' + r.archive_errors.join('；') : ''}`;
    showQualityResult(
      `女频采纳 · 第 ${r.chapter_num} 章`,
      _qualityResultText || '（改稿正文见上一条预览）',
      hint,
      { persisted: true, customButtons: [] },
    );
    toast(r.archive_synced ? '已采纳并同步档案' : '章节已写回，档案请检查');
  }, { loadingText: '采纳并同步中…' });
}

async function renderQualitySidebar(body) {
  clearEl(body);
  let entries = [];
  try {
    entries = await ensureQualityLog();
  } catch {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.textContent = '无法加载质量记录';
    body.appendChild(empty);
    return;
  }
  if (!entries.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.innerHTML =
      '尚无记录<br><span style="font-size:11px;color:var(--text-3)">角色观察 / 提取细节 / 各类检查会自动保存到此</span>';
    body.appendChild(empty);
    return;
  }
  for (const e of entries) {
    const el = cloneTplEl('tpl-sidebar-list-item');
    el.dataset.qualityId = e.id;
    el.querySelector('.title').textContent = `${e.label || e.kind}`;
    const ch = e.chapter_num ? `第${e.chapter_num}章` : '';
    const preview = (e.preview || e.summary || '').trim();
    const badge = e.persisted
      ? '<span class="record-badge record-badge--ok">已写入</span>'
      : (e.kind === 'female_fiction_revise'
        ? '<span class="record-badge record-badge--warn">待采纳</span>'
        : '');
    el.querySelector('.meta').innerHTML =
      `${timeBadgeHtml(e.created_at, e.persisted ? 'ok' : 'muted')}` +
      (ch ? ` <span class="record-meta">${escapeHtml(ch)}</span>` : '') +
      badge +
      (preview ? `<div class="record-preview">${escapeHtml(preview)}</div>` : '');
    el.addEventListener('click', () => openQualityLogEntry(e.id));
    body.appendChild(el);
  }
}

async function renderChatsSidebar(body) {
  let { messages, appended_indices: appended = [] } = await api('/chat/history');
  if (!messages.length) {
    const st = await api('/status');
    if (st.session_on_disk) {
      const r = await api('/chat/restore', { method: 'POST' });
      if (r.ok) {
        toast(`已恢复写书对话（${r.message_count} 条，${r.saved_at || ''}）`);
        const again = await api('/chat/history');
        messages = again.messages;
        appended = again.appended_indices || [];
      }
    }
  }
  const turns = pairChatTurns(messages);
  dataCache.chat = { messages, appended, turns };
  clearEl(body);
  if (!turns.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    const st = await api('/status');
    if (st.session_on_disk) {
      empty.innerHTML = '写书对话未加载<br>点击下方恢复';
      const btn = document.createElement('button');
      btn.className = 'btn btn-sm btn-primary';
      btn.style.marginTop = '8px';
      btn.textContent = '恢复写书记录';
      btn.addEventListener('click', async () => {
        await restoreChatSession();
        scheduleRender({ sidebar: true });
        if (state.mode === 'chat') await loadChat(true);
      });
      empty.appendChild(btn);
    } else {
      empty.innerHTML = '写书对话为空<br>在「写书对话」模式发送指令';
    }
    body.appendChild(empty);
    return;
  }
  await ensurePlanData();
  let defaultWorld = '本书';
  try {
    const proj = await api('/project');
    defaultWorld = proj.world_label || defaultWorld;
  } catch {
    /* ignore */
  }
  const { planByNum } = dataCache;

  const byWorld = new Map();
  turns.forEach((turn, t) => {
    const label = deriveChatTurnLabel(turn, t);
    const chNum = label.chapterNum;
    const plan = planByNum[chNum] || {};
    const { world, shortTitle } = parseChapterWorld(plan.title || `第${chNum}章`, defaultWorld);
    if (!byWorld.has(world)) byWorld.set(world, new Map());
    const byCh = byWorld.get(world);
    if (!byCh.has(chNum)) byCh.set(chNum, { shortTitle, items: [] });
    byCh.get(chNum).items.push({ turn, t, label, saved: turn.aiIdx != null && appended.includes(turn.aiIdx) });
  });

  for (const [worldKey, byCh] of [...byWorld.entries()].sort((a, b) => a[0].localeCompare(b[0], 'zh'))) {
    const wFold = `chat:${worldKey}`;
    const wCollapsed = isTocCollapsed('chatWorlds', wFold);
    body.appendChild(makeFoldRow({
      level: 0,
      label: worldKey,
      collapsed: wCollapsed,
      active: false,
      bucket: 'chatWorlds',
      foldKey: wFold,
    }));
    if (wCollapsed) continue;

    for (const [chNum, group] of [...byCh.entries()].sort((a, b) => a[0] - b[0])) {
      const cFold = `chat:${worldKey}:${chNum}`;
      const writeNum = getWriteChapterNum();
      const cCollapsed = isTocCollapsed('chatChapters', cFold, {
        forceOpen: chNum > 0 && (chNum === writeNum || chNum === state.currentChapter),
      });
      const chLabel = chNum > 0 ? `第 ${chNum} 章` : '未标注章节';
      body.appendChild(makeFoldRow({
        level: 1,
        label: `${chLabel} · ${group.shortTitle}`,
        collapsed: cCollapsed,
        active: false,
        bucket: 'chatChapters',
        foldKey: cFold,
      }));
      if (cCollapsed) continue;

      for (const { turn, t, label, saved } of group.items) {
        const el = cloneTplEl('tpl-sidebar-list-item');
        el.classList.add('toc-chat-turn');
        el.dataset.chatTurn = String(t);
        el.classList.toggle('active', state.chatFocusTurn === t);
        el.querySelector('.title').textContent = `${label.title}${saved ? ' · ✓已写入' : ''}`;
        el.querySelector('.meta').textContent = label.meta;
        el.addEventListener('click', () => openChatTurnCompare(t));
        body.appendChild(el);
      }
    }
  }
}

async function renderFreeChatsSidebar(body) {
  const data = await api('/free-chat/history');
  const threads = data.threads || [];
  clearEl(body);
  if (!threads.length) {
    const empty = cloneTplEl('tpl-empty-inline');
    empty.textContent = '点 + 新建讨论话题';
    body.appendChild(empty);
    return;
  }
  for (const t of threads) {
    const el = cloneTplEl('tpl-sidebar-list-item');
    el.dataset.threadId = t.id;
    el.classList.toggle('active', !!t.active);
    el.querySelector('.title').textContent = t.title || '未命名话题';
    const meta = [
      t.message_count ? `${t.message_count} 条` : '空',
      t.preview || '',
    ].filter(Boolean).join(' · ');
    el.querySelector('.meta').textContent = meta;
    el.addEventListener('click', () => switchFreeChatThread(t.id));
    body.appendChild(el);
  }
}

async function renderGlobalSidebar(body) {
  clearEl(body);
  let files = [];
  try {
    files = await ensureCodexFileList();
  } catch {
    files = Object.keys(GLOBAL_LABELS);
  }
  for (const k of files) {
    const el = cloneTplEl('tpl-global-item');
    el.dataset.globalKey = k;
    el.textContent = globalFileLabel(k);
    if (GLOBAL_DEPRECATED.has(k)) el.classList.add('global-item-deprecated');
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
  const delBtn = el.querySelector('.scene-card-del');
  if (delBtn) {
    delBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteScene(scene.id, chapterNum);
    });
  }
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
  const oldTitle = plan.title || `第${num}章`;
  if (title === oldTitle) return;
  if (!confirm(`将第${num}章标题由「${oldTitle}」改为「${title}」？`)) return;
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
    loadSceneBeatIntoEditors(scene);
    updateChatBeatPreview(scene);
  } else {
    updateChatBeatPreview(null);
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

async function saveBeat({ silent = false } = {}) {
  if (!state.currentSceneId) return;
  const beat = document.getElementById('beatEditor').value;
  const pace = document.getElementById('beatPaceSel')?.value || '中';
  const target = document.getElementById('beatEmotionTarget')?.value.trim() || '';
  const how = document.getElementById('beatEmotionHow')?.value.trim() || '';
  const emotion_anchor = { target, how };
  await api(`/plan/scenes/${state.currentSceneId}`, {
    method: 'PUT',
    body: JSON.stringify({ beat, pace, emotion_anchor }),
  });
  const found = getSceneFromCache(state.currentSceneId);
  if (found?.scene) {
    Object.assign(found.scene, { beat, pace, emotion_anchor });
    updateChatBeatPreview(found.scene);
  }
  scheduleRender({
    planPartial: { sceneId: state.currentSceneId, patch: { beat, pace, emotion_anchor } },
    sidebarPartial: state.sidebar === 'scenes'
      ? { type: 'scene', sceneId: state.currentSceneId, patch: { beat, pace, emotion_anchor } }
      : null,
  });
  if (!silent) toast('Beat 已保存');
}

async function deleteScene(sceneId, chapterNum) {
  const found = getSceneFromCache(sceneId);
  const title = found?.scene?.title || sceneId;
  if (!confirm(`删除场景「${title}」？\n\nBeat 将一并移除，章节正文不受影响。`)) return;
  await api(`/plan/scenes/${sceneId}`, { method: 'DELETE' });
  if (state.currentSceneId === sceneId) {
    setState({ currentSceneId: null }, 'none');
    updateChatBeatPreview(null);
  }
  invalidatePlanCache();
  await ensurePlanData(true);
  scheduleRender({ main: state.mode === 'plan', sidebar: state.sidebar === 'scenes' });
  toast('场景已删除');
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
function codexEntryPath(id) {
  return `/codex-entries/${encodeURIComponent(id)}`;
}

function updateWriteToolbar() {
  const sel = document.getElementById('writeChapterSel');
  const deleteBtn = document.getElementById('deleteCodexBtn');
  const newBtn = document.getElementById('newChapterBtn');
  const writeQualityRow = document.getElementById('writeQualityRow');
  const t = state.editTarget;
  const editingChapter = !t || t.type === 'chapter';
  if (sel) sel.style.display = editingChapter ? '' : 'none';
  if (newBtn) newBtn.classList.toggle('hidden', !editingChapter);
  if (deleteBtn) deleteBtn.classList.toggle('hidden', t?.type !== 'codex-entry');
  if (writeQualityRow) writeQualityRow.classList.toggle('hidden', !editingChapter);
}

async function renderWriteView() {
  await ensurePlanData();
  const { chapters, planByNum } = dataCache;
  const sel = document.getElementById('writeChapterSel');
  const empty = document.getElementById('writeEmpty');
  const editor = document.getElementById('mainEditor');
  const t = state.editTarget;

  // 编辑全局设定或 Codex 条目时不依赖章节，保留当前编辑器内容
  if (t?.type === 'global' || t?.type === 'codex-entry') {
    empty.classList.add('hidden');
    editor.classList.remove('hidden');
    updateWriteToolbar();
    return;
  }

  updateWriteToolbar();

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

function isEditorDirty() {
  const ed = document.getElementById('mainEditor');
  if (!ed || !state.editTarget) return false;
  return _editorSnapshot !== null && ed.value !== _editorSnapshot;
}

async function flushAutosave() {
  clearTimeout(_autosaveTimer);
  _autosaveTimer = null;
  if (!state.editTarget) return;
  if (state.editTarget.type === 'global') {
    if (!isEditorDirty()) return;
    if (confirm('全局设定有未保存的修改，是否保存？\n\n确定 = 保存并切换\n取消 = 不保存，丢弃修改')) {
      await saveEditor({ silent: true, confirmed: true });
    }
    return;
  }
  await saveEditor({ silent: true });
}

async function openChapter(num, { force = false } = {}) {
  const switching = state.editTarget?.type !== 'chapter' || state.editTarget?.num !== num;
  if (switching && state.editTarget) await flushAutosave();
  if (!switching && !force) {
    document.getElementById('writeChapterSel').value = num;
    updateWriteToolbar();
    updateWordCount();
    return;
  }
  const meta = dataCache.chapters.find(c => c.num === num);
  if (meta?.planned_only) {
    toast(`第 ${num} 章尚在规划，请先在「概览」或「规划」查看；写入续章灵感可自动建章`);
    setState({ mode: 'plan', currentChapter: num }, 'full');
    return;
  }
  const ch = await api(`/chapters/${num}`);
  setState(
    { currentChapter: num, editTarget: { type: 'chapter', num } },
    'none',
  );
  document.getElementById('mainTitle').textContent = `第${num}章 正文`;
  document.getElementById('mainEditor').value = ch.content;
  _editorSnapshot = ch.content;
  document.getElementById('writeChapterSel').value = num;
  updateWriteToolbar();
  updateWordCount();
  if (state.sidebar === 'toc') scheduleRender({ sidebar: true });
}

function onWriteChapterChange() {
  openChapter(parseInt(document.getElementById('writeChapterSel').value, 10));
}

function scheduleAutosave() {
  updateWordCount();
  if (!state.editTarget) return;
  // 全局设定须手动保存并确认，避免误删段落被静默写入
  if (state.editTarget.type === 'global') return;
  clearTimeout(_autosaveTimer);
  _autosaveTimer = setTimeout(() => saveEditor({ silent: true }), 2000);
}

const GLOBAL_SAVE_HINTS = {
  world: '世界观与大纲节拍变更会影响后续所有章节的 AI 理解。',
  style: '文风锚点写第一章前必须定稿；变更后缓存会刷新。',
  characters: '建议只在末尾追加；删改旧段落会破坏「只增不改」与缓存命中。',
  char_static: '性格锚点与禁止写法；极少改动，命中缓存②。',
  char_dynamic: '当前状态与表层软肋；每章定稿后更新（④ 层，不缓存）。',
  summaries_archive: '旧章概述归档；只增不改，命中缓存③。近期条可从此剪切迁入。',
  summaries_recent: '「生成概述」自动追加；章数多时将旧条迁入 archive。',
  plot_threads_locked: '已钉死的细节；只增不改，命中缓存③。',
  plot_threads_active: '未回收/已回收伏笔；每章维护（④ 层）。',
  summaries: '兼容视图；新概述写入 summaries_recent.md。',
  char_current: '已拆分，请编辑 char_static + char_dynamic。',
  plot_threads: '已拆分，请编辑 plot_threads_locked + plot_threads_active。',
};

async function saveEditor({ silent = false, confirmed = false } = {}) {
  const t = state.editTarget;
  const content = document.getElementById('mainEditor').value;
  if (!t) return toast('请先选择章节或设定');
  const titleEl = document.getElementById('mainTitle');
  try {
    if (t.type === 'chapter') {
      const explicitSave = !silent;
      const r = await api(`/chapters/${t.num}`, { method: 'PUT', body: JSON.stringify({ content }) });
      _editorSnapshot = content;
      const chTitle = r.chapter_title ? ` · ${r.chapter_title}` : '';
      if (titleEl) titleEl.textContent = `第${t.num}章${chTitle}`;
      if (silent) {
        document.getElementById('wordCountPill')?.classList.add('saved-flash');
        setTimeout(() => document.getElementById('wordCountPill')?.classList.remove('saved-flash'), 1200);
      } else if (content.trim()) {
        toast(`第${t.num}章已保存${chTitle}`);
      }
      if (explicitSave && content.trim() && shouldPromptFinalizeOnSave()) {
        delete guideState.modalDismissed[t.num];
        const runNow = confirm(
          `第 ${t.num} 章已保存。\n\n是否立即「本章定稿」？\n（档案写入 + 质检，约 2–3 次 API）`,
        );
        if (runNow) {
          await runPostChapterFinalize(t.num, { skipConfirm: true });
        } else {
          showPostChapterModal(t.num);
        }
        fetchGuideStatus(true).then(() =>
          renderGuideHints(state.mode === 'chat' ? 'chat' : state.mode),
        );
      }
    } else if (t.type === 'codex-entry') {
      await api(codexEntryPath(t.id), { method: 'PUT', body: JSON.stringify({ content }) });
      _editorSnapshot = content;
      toast(silent ? 'Codex 已自动保存' : 'Codex 已保存');
      invalidateCodexCache();
    } else if (t.type === 'global') {
      if (silent && !confirmed) return;
      if (!confirmed) {
        const label = globalFileLabel(t.name);
        const hint = GLOBAL_SAVE_HINTS[t.name] || '';
        const msg = `保存「${label}」？\n\n${hint}\n\n（备份在 data/backups/）`;
        if (!confirm(msg)) {
          return;
        }
      }
      const payload = { content };
      if (guideState.postChapterChapterNum > 0) {
        payload.chapter_num = guideState.postChapterChapterNum;
      }
      const r = await api(`/codex/${t.name}`, { method: 'PUT', body: JSON.stringify(payload) });
      if (r.changed === false) {
        toast('内容未变化，未写入。请填写字段后再点保存');
        return;
      }
      _editorSnapshot = content;
      toast('设定已保存');
      if (t.name === 'char_dynamic' || t.name === 'plot_threads_active') {
        await fetchGuideStatus(true);
        renderGuideHints(state.mode === 'chat' ? 'chat' : state.mode);
        const cn = guideState.postChapterChapterNum;
        if (cn > 0) {
          const todos = guideState.status?.post_chapter_todos || {};
          const maintKeys = ['char_dynamic_never', 'plot_threads_never', 'char_dynamic', 'plot_threads'];
          if (!maintKeys.some((k) => todos[k])) {
            guideState.postChapterChapterNum = 0;
            document.getElementById('postChapterModal')?.remove();
          } else if (document.getElementById('postChapterModal')) {
            await showPostChapterModal(cn, true);
          }
        }
      }
    }
  } catch (e) {
    if (t.type === 'chapter' && titleEl) titleEl.textContent = `第${t.num}章 ⚠️ 保存失败`;
    if (!silent) toast(e.message || '保存失败');
  }
}

async function newChapter() {
  await ensurePlanData();
  const withBody = dataCache.chapters.filter((c) => !c.planned_only);
  const nextNum = withBody.length ? withBody[withBody.length - 1].num + 1 : 1;
  const label = nextNum === 1 ? '第一章' : `第 ${nextNum} 章`;
  if (!confirm(`将创建${label}（空章），是否继续？`)) return;
  const r = await api('/chapters/new', { method: 'POST' });
  invalidatePlanCache();
  setState({ currentChapter: r.num }, 'none');
  await setWriteChapterTarget(r.num);
  await fillWriteChapterTargetSel();
  toast(`第${r.num}章已创建，写作目标已同步`);
  setMode(state.mode === 'plan' ? 'plan' : 'write');
  await loadStatus();
}

async function openCodexEntry(id) {
  if (state.editTarget?.type !== 'codex-entry' || state.editTarget?.id !== id) await flushAutosave();
  const entry = await api(codexEntryPath(id));
  setState({ editTarget: { type: 'codex-entry', id } }, 'none');
  setMode('write');
  document.getElementById('mainTitle').textContent = `Codex · ${entry.name}`;
  document.getElementById('mainEditor').value = entry.content;
  _editorSnapshot = entry.content;
  document.getElementById('writeEmpty').classList.add('hidden');
  document.getElementById('mainEditor').classList.remove('hidden');
  updateWriteToolbar();
}

async function deleteCodexEntry() {
  const t = state.editTarget;
  if (t?.type !== 'codex-entry') return;
  const entry = dataCache.codex.entries.find(e => e.id === t.id);
  const label = entry?.name || t.id;
  if (isEditorDirty()) {
    if (!confirm(`条目「${label}」有未保存修改。\n\n确定 = 先保存再删除\n取消 = 中止删除`)) return;
    await saveEditor({ silent: true });
  }
  if (!confirm(`删除 Codex 条目「${label}」？\n\n原文件会备份到 data/backups/，并从勾选列表移除。`)) return;
  await api(codexEntryPath(t.id), { method: 'DELETE' });
  setState({ editTarget: null }, 'none');
  invalidateCodexCache();
  scheduleRender({ main: true, sidebar: state.sidebar === 'codex' });
  toast('条目已删除');
}

async function openGlobal(name) {
  if (state.editTarget?.type !== 'global' || state.editTarget?.name !== name) await flushAutosave();
  const data = await api(`/codex/${name}`);
  setState({ editTarget: { type: 'global', name } }, 'none');
  setMode('write');
  document.getElementById('mainTitle').textContent = globalFileLabel(name);
  document.getElementById('mainEditor').value = data.content;
  _editorSnapshot = data.content;
  document.getElementById('writeEmpty').classList.add('hidden');
  document.getElementById('mainEditor').classList.remove('hidden');
  updateWriteToolbar();
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
  if (containerId === 'chatMessages') scrollChatToBottom('smooth');
  else scrollFreeChatToBottom('smooth');
}

function removeTypingIndicator() {
  document.getElementById('typingIndicator')?.remove();
}

function renderChatMessages(messages, { highlight = [], scrollTo = null, scrollToTurn = null } = {}) {
  const log = document.getElementById('chatMessages');
  const appended = dataCache.chat.appended || [];
  clearEl(log);
  if (!messages.length) {
    const empty = cloneTplEl('tpl-chat-empty');
    empty.querySelector('p').textContent =
      '这是新对话。输入指令开始 — 每轮会显示「你的指令」与「AI 回复」，点击任一轮可打开对照面板。';
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = '先去 Plan 写 Beat';
    btn.addEventListener('click', () => setMode('plan'));
    empty.querySelector('.nc-empty-box').appendChild(btn);
    log.appendChild(empty);
    return;
  }

  const turns = pairChatTurns(messages);
  const highlightTurns = new Set();
  if (scrollToTurn != null) highlightTurns.add(scrollToTurn);
  turns.forEach((t, ti) => {
    if (highlight.includes(t.userIdx) || (t.aiIdx != null && highlight.includes(t.aiIdx))) {
      highlightTurns.add(ti);
    }
  });

  for (let ti = 0; ti < turns.length; ti++) {
    log.appendChild(buildChatTurnCard(turns[ti], ti, {
      appended,
      highlight: highlightTurns.has(ti),
    }));
  }

  if (scrollToTurn != null) {
    scrollChatToEl(log.querySelector(`[data-turn-num="${scrollToTurn}"]`), 'start');
    return;
  }
  if (scrollTo != null) {
    const ti = turns.findIndex(t => t.userIdx === scrollTo || t.aiIdx === scrollTo);
    if (ti >= 0) {
      scrollChatToEl(log.querySelector(`[data-turn-num="${ti}"]`), 'start');
      return;
    }
  }
  scrollChatToBottom('smooth');
}

function showChatCompare(turn, turnNum) {
  closeOtherResultPanels('compare');
  const panel = document.getElementById('chatComparePanel');
  if (!panel) return;
  const chNum = extractTurnChapterNum(turn.user) || getWriteChapterNum() || dataCache.chapters[dataCache.chapters.length - 1]?.num;
  document.getElementById('chatCompareTitle').textContent = `第 ${turnNum + 1} 轮对照`;
  const guideEl = document.getElementById('chatCompareGuide');
  if (guideEl) {
    guideEl.innerHTML = chNum
      ? `定稿流程：下方<b>「用此轮 AI 回复替换本章」</b> → 写入 <code>data/chapters/ch${String(chNum).padStart(3, '0')}.md</code>；或点「去写作模式核对」手动改。`
      : '定稿：用下方按钮将 AI 回复写入章节文件，或去写作模式核对。';
  }
  document.getElementById('chatCompareUser').textContent = turn.user || '（空）';
  document.getElementById('chatCompareAi').textContent = turn.ai || '（无回复）';
  const savedEl = document.getElementById('chatCompareSaved');
  const saved = turn.aiIdx != null && (dataCache.chat.appended || []).includes(turn.aiIdx);
  savedEl.classList.toggle('hidden', !saved);
  const btnAi = document.getElementById('btnApplyAiTurn');
  const btnDraft = document.getElementById('btnApplyDraftTurn');
  if (btnAi) btnAi.disabled = turn.aiIdx == null;
  if (btnDraft) {
    const hasDraft = /^【当前章节：第\d+章】/.test((turn.user || '').trim());
    btnDraft.disabled = !hasDraft;
    btnDraft.title = hasDraft ? '' : '仅首轮附带全文章节时可用';
  }
  panel.dataset.turnNum = String(turnNum);
  panel.classList.remove('hidden');
  syncChatResultOverlay();
}

async function applyChatTurnAsChapter(source) {
  const turnNum = parseInt(document.getElementById('chatComparePanel')?.dataset.turnNum ?? '', 10);
  const turn = dataCache.chat.turns?.[turnNum];
  if (!turn) return toast('请先选择一轮对照');
  const msgIndex = source === 'user_draft' ? turn.userIdx : turn.aiIdx;
  if (msgIndex == null) return toast(source === 'user_draft' ? '该轮没有可替换的章节草稿' : '该轮没有 AI 回复');

  await ensurePlanData();
  const fromTurn = extractTurnChapterNum(turn.user);
  const num = fromTurn || getWriteChapterNum() || dataCache.chapters[dataCache.chapters.length - 1]?.num;
  if (!num) return toast('请先在规划模式创建章节');

  const label = source === 'user_draft' ? '指令中的章节正文' : 'AI 回复';
  const preview = (source === 'user_draft' ? turn.user : turn.ai || '').slice(0, 80);
  const msg =
    `用第 ${turnNum + 1} 轮的${label}替换第 ${num} 章全文？\n\n` +
    `当前章节文件会被整章覆盖（旧稿备份在 data/backups/）。\n\n` +
    `预览：${preview}…`;
  if (!confirm(msg)) return;

  const btnId = source === 'assistant' ? 'btnApplyAiTurn' : 'btnApplyDraftTurn';
  await runWithLoading(async () => {
    const r = await api(`/chapters/${num}/apply-turn`, {
      method: 'POST',
      body: JSON.stringify({ msg_index: msgIndex, source }),
    });
    invalidateCache(['chapters', 'plan']);
    await loadChat(false);
    showChatCompare(dataCache.chat.turns[turnNum], turnNum);
    scheduleRender({ sidebar: state.sidebar === 'chats' });
    if (state.editTarget?.type === 'chapter' && state.editTarget.num === num) {
      await openChapter(num, { force: true });
    }
    toast(`第 ${num} 章已替换为第 ${turnNum + 1} 轮${label}（${r.chars} 字）`);
  }, { btnId, loadingText: '替换中…' });
}

function closeChatCompare() {
  document.getElementById('chatComparePanel')?.classList.add('hidden');
  syncChatResultOverlay();
  state.chatFocusTurn = null;
  if (state.sidebar === 'chats') scheduleRender({ sidebar: true });
  if (dataCache.chat.messages?.length) {
    renderChatMessages(dataCache.chat.messages);
  }
}

async function openChatTurnCompare(turnNum) {
  if (!dataCache.chat.turns?.length) {
    const { messages, appended_indices: appended = [] } = await api('/chat/history');
    dataCache.chat = { messages, appended, turns: pairChatTurns(messages) };
  }
  const turn = dataCache.chat.turns[turnNum];
  if (!turn) return;
  state.chatFocusTurn = turnNum;
  if (state.mode !== 'chat') setState({ mode: 'chat', sidebar: 'chats' }, 'full');
  else if (state.sidebar !== 'chats') setState({ sidebar: 'chats' }, { chrome: true, sidebar: true });
  showChatCompare(turn, turnNum);
  const hi = [turn.userIdx, turn.aiIdx].filter(x => x != null);
  renderChatMessages(dataCache.chat.messages, { highlight: hi, scrollToTurn: turn });
  scheduleRender({ sidebar: state.sidebar === 'chats' });
}

async function openChapterFromChat() {
  await ensurePlanData();
  const num = getWriteChapterNum() || dataCache.chapters[dataCache.chapters.length - 1]?.num;
  if (!num) return toast('请先在规划模式创建章节');
  setState({ mode: 'write' }, 'chrome');
  await openChapter(num);
  toast(`已打开第 ${num} 章正文，请核对后保存`);
}

async function loadChat(refreshSidebarPanel = true) {
  const { messages, appended_indices: appended = [] } = await api('/chat/history');
  dataCache.chat = {
    messages,
    appended,
    turns: pairChatTurns(messages),
  };
  const turn = state.chatFocusTurn;
  if (turn != null && dataCache.chat.turns[turn]) {
    showChatCompare(dataCache.chat.turns[turn], turn);
    const t = dataCache.chat.turns[turn];
    renderChatMessages(messages, {
      highlight: [t.userIdx, t.aiIdx].filter(x => x != null),
      scrollToTurn: turn,
    });
  } else {
    renderChatMessages(messages);
  }
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
  if (containerId === 'chatMessages') scrollChatToBottom('auto');
  else scrollFreeChatToBottom('auto');
  return el.querySelector('.stream-body');
}

async function loadChatPrompts() {
  const data = await api('/chat/prompts');
  dataCache.chat.prompts = data.prompts || [];
  return dataCache.chat.prompts;
}

function promptLineText(p) {
  const raw = (p.content || p.title || '').trim().replace(/\s+/g, ' ');
  return raw.length > 100 ? `${raw.slice(0, 100)}…` : raw;
}

function renderPromptLibrary() {
  const host = document.getElementById('promptLines');
  if (!host) return;
  clearEl(host);
  const prompts = dataCache.chat.prompts || [];
  if (!prompts.length) {
    const empty = document.createElement('div');
    empty.className = 'prompt-lines-empty';
    empty.textContent = '还没有保存的指令，写好下方内容后点「存入」';
    host.appendChild(empty);
    return;
  }
  for (const p of prompts) {
    const row = document.createElement('div');
    row.className = 'prompt-line';
    if (p.id === state.activePromptId) row.classList.add('active');

    const textBtn = document.createElement('button');
    textBtn.type = 'button';
    textBtn.className = 'prompt-line-text';
    textBtn.textContent = promptLineText(p);
    textBtn.title = (p.content || p.title || '').trim();
    textBtn.addEventListener('click', () => selectChatPrompt(p.id));

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'prompt-line-del';
    delBtn.textContent = '×';
    delBtn.title = '删除';
    delBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteChatPrompt(p.id);
    });

    row.appendChild(textBtn);
    row.appendChild(delBtn);
    host.appendChild(row);
  }
}

function selectChatPrompt(id) {
  const p = (dataCache.chat.prompts || []).find(x => x.id === id);
  if (!p) return;
  state.activePromptId = id;
  const ta = document.getElementById('chatInstruction');
  if (ta) ta.value = p.content || '';
  renderPromptLibrary();
}

async function persistChatPrompts() {
  const r = await api('/chat/prompts', {
    method: 'PUT',
    body: JSON.stringify({ prompts: dataCache.chat.prompts }),
  });
  dataCache.chat.prompts = r.prompts || dataCache.chat.prompts;
  renderPromptLibrary();
}

async function saveChatPrompt() {
  const content = document.getElementById('chatInstruction')?.value.trim();
  if (!content) return toast('先在下方写好指令再存入');
  const exists = dataCache.chat.prompts.some(
    p => (p.content || '').trim() === content,
  );
  if (exists) return toast('这条指令已在库里');
  const line = content.split('\n', 1)[0].trim();
  const title = line.length > 80 ? `${line.slice(0, 80)}…` : line;
  const id = `p_${Date.now().toString(36)}`;
  dataCache.chat.prompts.unshift({ id, title, content });
  state.activePromptId = id;
  await persistChatPrompts();
  toast('已存入指令库');
}

async function deleteChatPrompt(id) {
  const p = dataCache.chat.prompts.find(x => x.id === id);
  if (!p) return;
  const preview = promptLineText(p);
  if (!confirm(`删除这条指令？\n\n${preview}`)) return;
  dataCache.chat.prompts = dataCache.chat.prompts.filter(x => x.id !== id);
  if (state.activePromptId === id) state.activePromptId = null;
  await persistChatPrompts();
}

async function sendChatStream(body) {
  const controller = new AbortController();
  _chatStreamAbort = controller;
  // #region agent log
  _dbgUiLog('app.js:sendChatStream', 'abort controller set', {
    chapter_num: body.chapter_num,
  }, 'H1');
  // #endregion
  let timedOut = false;
  let streamStarted = false;
  let doneMeta = null;
  const streamStartMs = Date.now();
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
    const streamHeaders = { 'Content-Type': 'application/json' };
    const token = sessionStorage.getItem('novel_web_token');
    if (token) streamHeaders['X-Novel-Token'] = token;
    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: streamHeaders,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    // #region agent log
    _dbgUiLog('app.js:sendChatStream', 'fetch response', {
      status: resp.status,
      ok: resp.ok,
      hasBody: !!resp.body,
      elapsedMs: Date.now() - streamStartMs,
      firstByteLimitMs: STREAM_FIRST_BYTE_MS,
    }, 'H1');
    // #endregion
    if (resp.status === 401) {
      const entered = prompt('Web API 需要访问令牌（.env 中的 NOVEL_WEB_TOKEN）');
      if (entered) {
        sessionStorage.setItem('novel_web_token', entered.trim());
        return sendChatStream(body);
      }
      throw new Error('未授权');
    }
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      const msg = formatApiError(data, resp.statusText);
      if (resp.status === 403 && msg.includes('非本地')) {
        throw new Error(`${msg}\n\n请用 http://127.0.0.1:8765 打开，或在 .env 设置 NOVEL_WEB_TOKEN 后输入令牌`);
      }
      throw new Error(msg);
    }
    if (!resp.body) throw new Error('AI 连接异常，未收到流式响应');

    removeTypingIndicator();
    const bubble = beginStreamOnLastTurn();
    const reader = resp.body.getReader();
    _chatStreamReader = reader;
    const decoder = new TextDecoder();
    let buffer = '';

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
          scrollChatToBottom('auto');
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
    // #region agent log
    _dbgUiLog('app.js:sendChatStream', 'stream error', {
      name: e.name,
      message: String(e.message || '').slice(0, 120),
      timedOut,
      streamStarted,
      signalAborted: !!_chatStreamAbort?.signal?.aborted,
      cancelled: !!e.cancelled,
    }, e.name === 'AbortError' ? 'H2' : 'H5');
    // #endregion
    if (e.name === 'AbortError') {
      if (!timedOut && (_chatStreamUserCancelled || _chatStreamAbort?.signal?.aborted)) {
        const err = new Error('生成已停止');
        err.cancelled = true;
        throw err;
      }
      if (timedOut) {
        throw new Error(streamStarted ? '生成超时（长时间无新内容），请重试' : '连接超时，请检查网络或 API Key');
      }
    }
    throw e;
  } finally {
    clearTimeout(timer);
    // #region agent log
    _dbgUiLog('app.js:sendChatStream', 'stream finally', {
      signalAborted: !!_chatStreamAbort?.signal?.aborted,
      streamStarted,
      hadDoneMeta: !!doneMeta,
    }, 'H6');
    // #endregion
    _chatStreamReader = null;
    document.getElementById('streamBubble')?.removeAttribute('id');
    document.getElementById('stopChatBtn')?.classList.add('hidden');
  }
}

let _lastCallForDebug = null;
let _contextDebugData = null;
let _cachePanelOpen = false;

function formatTokenBar(label, value, total, cssClass) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    `<div class="token-row">` +
    `<span>${label}</span>` +
    `<div class="token-bar ${cssClass}"><span style="width:${pct}%"></span></div>` +
    `<span>${value.toLocaleString()}</span>` +
    `</div>`
  );
}

function formatCacheAge(ts) {
  if (!ts) return '—';
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (sec < 60) return `${sec} 秒前`;
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  return `${Math.floor(sec / 3600)} 小时前`;
}

function formatTtlRemaining(sec) {
  if (sec == null) return '—';
  if (sec <= 0) return '已过期或未知';
  const m = Math.floor(sec / 60);
  return m >= 60 ? `约 ${Math.floor(m / 60)} 小时 ${m % 60} 分` : `约 ${m} 分钟`;
}

function renderCacheDetailPanel(lc) {
  const panel = document.getElementById('cacheDetailPanel');
  if (!panel || !lc?.ok || !lc.usage) return;
  const u = lc.usage;
  const total = (u.cache_read || 0) + (u.cache_write || 0) + (u.input || 0) + (u.output || 0);
  const cost = Number(lc.cost || 0);
  const costNo = Number(lc.cost_no_cache || 0);
  const saved = Number(lc.cost_saved ?? Math.max(0, costNo - cost));
  const pct = lc.cache_savings_pct ?? (costNo > 0 ? Math.round((saved / costNo) * 100) : 0);
  panel.innerHTML =
    `<h4>📊 本次请求 Token 明细</h4>` +
    formatTokenBar('cache_read', u.cache_read || 0, total, '') +
    formatTokenBar('cache_write', u.cache_write || 0, total, 'write') +
    formatTokenBar('input', u.input || 0, total, 'input') +
    formatTokenBar('output', u.output || 0, total, 'output') +
    `<div class="divider"></div>` +
    `<div class="cost-line">💰 本次费用：<b>$${cost.toFixed(4)}</b></div>` +
    (costNo > 0
      ? `<div class="cost-line">💰 若无缓存：<b>$${costNo.toFixed(4)}</b> · 省了 <b>${pct}%</b></div>`
      : '') +
    `<div class="divider"></div>` +
    `<div class="muted">模型：${lc.model || lc.provider || '—'}</div>` +
    `<div class="muted">上次 cache 写入：${formatCacheAge(lc.cache_write_at)}</div>` +
    `<div class="muted">TTL 剩余：${formatTtlRemaining(lc.cache_ttl_remaining)}</div>`;
}

function toggleCachePanel(force) {
  const panel = document.getElementById('cacheDetailPanel');
  if (!panel) return;
  if (force === false || (_cachePanelOpen && force !== true)) {
    panel.classList.add('hidden');
    _cachePanelOpen = false;
    return;
  }
  if (!_lastCallForDebug?.ok) {
    toast('尚无 API 调用记录');
    return;
  }
  renderCacheDetailPanel(_lastCallForDebug);
  panel.classList.remove('hidden');
  _cachePanelOpen = true;
}

function updateCachePill({ writing_cache_supported, last_call, provider } = {}) {
  const pill = document.getElementById('cachePill');
  if (!pill) return;
  const supported = writing_cache_supported ?? (
    provider ? provider.startsWith('kie') : null
  );
  if (supported === false) {
    pill.textContent = '无 Prompt Cache';
    pill.title = '当前主力为 DeepSeek 等模型，不支持 Prompt Cache；写书对话切到 kie Claude 后此处会显示命中/写入';
    pill.classList.remove('hidden', 'pill-cache-hit', 'pill-clickable');
    pill.classList.add('pill-cache-off');
    _lastCallForDebug = null;
    toggleCachePanel(false);
    return;
  }
  pill.classList.remove('pill-cache-off');
  pill.classList.add('pill-clickable');
  const lc = last_call;
  if (!lc?.ok || !lc.usage) {
    pill.classList.add('hidden');
    _lastCallForDebug = null;
    toggleCachePanel(false);
    return;
  }
  _lastCallForDebug = lc;
  const cr = lc.usage.cache_read || 0;
  const cw = lc.usage.cache_write || 0;
  pill.classList.remove('hidden');
  if (cr > 0) {
    pill.textContent = `cache 命中 ${cr.toLocaleString()} ▼`;
    pill.title = '点击查看 Token 明细';
    pill.classList.add('pill-cache-hit');
  } else if (cw > 0) {
    pill.textContent = `cache 写入 ${cw.toLocaleString()} ▼`;
    pill.title = '点击查看 Token 明细';
    pill.classList.remove('pill-cache-hit');
  } else {
    pill.textContent = 'cache — ▼';
    pill.title = '点击查看 Token 明细';
    pill.classList.remove('pill-cache-hit');
  }
  if (_cachePanelOpen) renderCacheDetailPanel(lc);
}

function applyStreamDoneMeta(doneMeta) {
  if (!doneMeta) return;
  if (doneMeta.chapter_num) {
    state.writeChapterNum = doneMeta.chapter_num;
    updateChatHints();
  }
  if (doneMeta.total_cost != null) {
    const footer = document.getElementById('footerStat');
    if (footer) {
      const text = footer.textContent || '';
      const prefix = text.split('· $')[0] || text;
      footer.textContent = `${prefix.trim()} · $${Number(doneMeta.total_cost).toFixed(4)}`;
    }
  }
  if (doneMeta.usage || doneMeta.writing_cache_supported != null) {
    updateCachePill({
      writing_cache_supported: doneMeta.writing_cache_supported,
      provider: doneMeta.provider,
      last_call: {
        ok: true,
        provider: doneMeta.provider,
        model: doneMeta.model,
        cost: doneMeta.cost,
        cost_no_cache: doneMeta.cost_no_cache,
        cost_saved: doneMeta.cost_saved,
        cache_savings_pct: doneMeta.cache_savings_pct,
        cache_write_at: doneMeta.cache_write_at,
        cache_ttl_remaining: doneMeta.cache_ttl_remaining,
        usage: doneMeta.usage,
      },
    });
  }
}

function renderContextLayer(layer, depth = 0) {
  const cached = layer.cached
    ? '<span class="badge cached">✅ 缓存</span>'
    : '<span class="badge uncached">❌ 不缓存</span>';
  const tok = layer.token_estimate != null ? `${layer.token_estimate.toLocaleString()} tokens` : '';
  const id = `ctx-layer-${layer.id}-${depth}-${Math.random().toString(36).slice(2, 7)}`;
  let childrenHtml = '';
  if (layer.children?.length) {
    childrenHtml = layer.children
      .map(
        (c) =>
          `<div class="ctx-child">` +
          `<div class="ctx-child-title">${c.label} · ${(c.token_estimate || 0).toLocaleString()} tokens</div>` +
          `<pre>${escapeHtml(c.content || '')}</pre>` +
          `</div>`,
      )
      .join('');
  }
  const body = layer.children?.length
    ? childrenHtml
    : `<pre>${escapeHtml(layer.content || '')}</pre>`;
  return (
    `<div class="ctx-layer">` +
    `<div class="ctx-layer-head" onclick="toggleCtxLayer('${id}')">` +
    `<span>${layer.label}</span>` +
    `<span class="muted">${tok}</span>` +
    cached +
    `<span class="muted">▶</span>` +
    `</div>` +
    `<div class="ctx-layer-body hidden" id="${id}">${body}</div>` +
    `</div>`
  );
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function toggleCtxLayer(id) {
  document.getElementById(id)?.classList.toggle('hidden');
}

function renderContextDrawer(data) {
  const body = document.getElementById('contextDrawerBody');
  if (!body) return;
  if (!data?.ok) {
    body.innerHTML = `<p class="muted">${escapeHtml(data?.error || '暂无数据')}</p>`;
    return;
  }
  const meta =
    `<p class="muted">${escapeHtml(data.tag || '请求')} · ${escapeHtml(data.provider || '')}/${escapeHtml(data.model || '')} · ${escapeHtml(data.context_mode || '')} · ${escapeHtml(data.ts || '')}</p>`;
  const layers = (data.layers || []).map((l) => renderContextLayer(l)).join('');
  const msgs = (data.messages || [])
    .map(
      (m) =>
        `<div class="ctx-msg">` +
        `<div class="role">${escapeHtml(m.role)} · ${(m.est_tokens || 0).toLocaleString()} tokens · ${(m.chars || 0).toLocaleString()} 字</div>` +
        `<div class="preview">${escapeHtml(m.preview || '')}${m.has_chapter ? ' …[含章节正文]' : ''}${m.has_beat ? ' …[含 Beat]' : ''}</div>` +
        `</div>`,
    )
    .join('');
  body.innerHTML =
    meta +
    layers +
    `<h4 style="margin:16px 0 8px;font-size:13px">💬 messages（对话历史 · 约 ${(data.messages_token_estimate || 0).toLocaleString()} tokens）</h4>` +
    (msgs || '<p class="muted">（无 messages）</p>');
}

async function openContextDrawer() {
  const drawer = document.getElementById('contextDrawer');
  const backdrop = document.getElementById('contextDrawerBackdrop');
  if (!drawer || !backdrop) return;
  drawer.classList.remove('hidden');
  backdrop.classList.remove('hidden');
  document.getElementById('contextDrawerBody').innerHTML = '<p class="muted">加载中…</p>';
  toggleCachePanel(false);
  try {
    const data = await api('/debug/last_context');
    _contextDebugData = data;
    renderContextDrawer(data);
  } catch (e) {
    renderContextDrawer({ ok: false, error: e.message });
  }
}

function closeContextDrawer() {
  document.getElementById('contextDrawer')?.classList.add('hidden');
  document.getElementById('contextDrawerBackdrop')?.classList.add('hidden');
}

async function copyContextDebug() {
  if (!_contextDebugData?.ok) {
    toast('无可复制内容');
    return;
  }
  const parts = [];
  for (const layer of _contextDebugData.layers || []) {
    parts.push(`=== ${layer.label} ===\n${layer.content || ''}`);
    for (const c of layer.children || []) {
      parts.push(`--- ${c.label} ---\n${c.content || ''}`);
    }
  }
  for (const m of _contextDebugData.messages || []) {
    parts.push(`[${m.role}] ${m.preview || ''}`);
  }
  try {
    await navigator.clipboard.writeText(parts.join('\n\n'));
    toast('已复制上下文摘要');
  } catch {
    toast('复制失败');
  }
}

async function sendChat() {
  const sendBtn = document.getElementById('sendChatBtn');
  // #region agent log
  _dbgUiLog('app.js:sendChat', 'sendChat called', {
    isChatSending: _isChatSending,
    btnDisabled: sendBtn?.disabled,
    btnText: sendBtn?.textContent,
    readingMode: isChatReadingMode(),
    instructionLen: (document.getElementById('chatInstruction')?.value || '').trim().length,
  }, 'H7');
  // #endregion
  const instruction = document.getElementById('chatInstruction').value.trim();
  if (!instruction) return toast('请输入指令');
  if (isChatReadingMode()) return toast('阅读模式下无法发送，请先退出阅读模式');
  const session = beginSending('sendChatBtn', '生成中…');
  if (!session) return;

  const errEl = document.getElementById('chatError');
  errEl.textContent = '';
  try {
    let scene_beat = '';
    if (state.currentSceneId) {
      scene_beat = document.getElementById('beatEditor')?.value || '';
    }
    const chapter_num = getWriteChapterNum();
    appendOptimisticTurn(instruction, scene_beat);
    const payload = {
      instruction,
      scene_beat,
      scene_id: state.currentSceneId || '',
    };
    if (chapter_num) payload.chapter_num = chapter_num;
    const doneMeta = await sendChatStream(payload);
    document.getElementById('stopChatBtn')?.classList.add('hidden');
    document.getElementById('chatInstruction').value = '';
    applyStreamDoneMeta(doneMeta);
    state.chatFocusTurn = null;
    closeChatCompare();
    await loadChat(true);
    await loadStatus();
    if (doneMeta?.chapter_num) {
      setState({ writeChapterNum: doneMeta.chapter_num }, 'none');
      updateChatHints();
    }
    if (doneMeta?.chapter_saved) {
      invalidateCache(['plan', 'chapters']);
      const mode = doneMeta.chapter_save_mode === 'append' ? '追加' : '覆盖';
      const title = doneMeta.chapter_title ? ` · ${doneMeta.chapter_title}` : '';
      toast(`已${mode}保存第${doneMeta.chapter_num}章${title}`);
      delete guideState.modalDismissed[doneMeta.chapter_num];
      const runNow = confirm(
        `第 ${doneMeta.chapter_num} 章已写入。\n\n是否立即「本章定稿」？\n（档案写入 + 质检，约 2–3 次 API）`,
      );
      if (runNow) {
        runPostChapterFinalize(doneMeta.chapter_num, { skipConfirm: true });
      } else {
        showPostChapterModal(doneMeta.chapter_num);
      }
      fetchGuideStatus(true).then(() => renderGuideHints('chat'));
    }
  } catch (e) {
    // #region agent log
    _dbgUiLog('app.js:sendChat', 'sendChat catch', {
      cancelled: !!e.cancelled,
      message: String(e.message || '').slice(0, 120),
    }, e.cancelled ? 'H5' : 'H3');
    // #endregion
    if (!e.cancelled) {
      const msg = e.message || 'AI 连接异常，请检查 API Key 或网络';
      errEl.textContent = msg;
      toast(msg);
    } else {
      toast('生成已停止');
    }
    document.getElementById('streamBubble')?.remove();
    removeTypingIndicator();
    await loadChat(false);
  } finally {
    // #region agent log
    _dbgUiLog('app.js:sendChat', 'sendChat finally endSending', {
      isChatSending: _isChatSending,
      hasAbort: !!_chatStreamAbort,
    }, 'H3');
    // #endregion
    endSending(session);
  }
}

async function restoreChatSession() {
  const r = await api('/chat/restore', { method: 'POST' });
  if (!r.ok) return toast(r.error || '恢复失败');
  toast(`已恢复写书对话（${r.message_count} 条）`);
  state.chatFocusTurn = null;
  await loadStatus();
  await loadChat(true);
  return r;
}

async function clearChat() {
  if (!confirm('清空写书对话？（章节文件保留；备份在 data/backups/）')) return;
  await api('/chat/clear', { method: 'POST' });
  state.chatFocusTurn = null;
  setState({ writeChapterNum: null }, 'none');
  closeChatCompare();
  await loadStatus();
  await loadChat(true);
  updateChatHints();
}

function formatChatTurnCopyText(turn) {
  const parts = [];
  if (turn.user) parts.push(`【你的指令】\n${turn.user}`);
  if (turn.ai) parts.push(`【AI 回复】\n${turn.ai}`);
  return parts.join('\n\n');
}

function copyChatTurn(turn) {
  copyTextToClipboard(formatChatTurnCopyText(turn), '本轮无内容可复制');
}

async function copyAllWriteChat() {
  const messages = dataCache.chat.messages;
  if (!messages?.length) {
    try {
      const { messages: loaded } = await api('/chat/history');
      if (!loaded?.length) return copyTextToClipboard('', '对话为空');
      const turns = pairChatTurns(loaded);
      const text = turns.map((t, i) => `--- 第 ${i + 1} 轮 ---\n${formatChatTurnCopyText(t)}`).join('\n\n');
      return copyTextToClipboard(text);
    } catch (e) {
      toast(e.message || '加载对话失败');
      return;
    }
  }
  const turns = pairChatTurns(messages);
  const text = turns.map((t, i) => `--- 第 ${i + 1} 轮 ---\n${formatChatTurnCopyText(t)}`).join('\n\n');
  copyTextToClipboard(text);
}

function formatFreeChatMessagesCopyText(messages) {
  return (messages || [])
    .map((m) => `${m.role === 'user' ? '你' : 'AI'}：\n${m.content || ''}`)
    .join('\n\n');
}

async function copyAllFreeChat() {
  const messages = dataCache.freeChat.messages;
  if (!messages?.length) {
    try {
      const data = await api('/free-chat/history');
      const loaded = data.messages || [];
      if (!loaded.length) return copyTextToClipboard('', '当前话题为空');
      return copyTextToClipboard(formatFreeChatMessagesCopyText(loaded));
    } catch (e) {
      toast(e.message || '加载失败');
      return;
    }
  }
  copyTextToClipboard(formatFreeChatMessagesCopyText(messages));
}

function copyFreeChatMessage(content) {
  copyTextToClipboard(content || '', '消息为空');
}

// ── 自由聊 ─────────────────────────────────────
function updateFreeChatToolbar(data) {
  const titleEl = document.getElementById('freeChatThreadTitle');
  const hintEl = document.getElementById('freeChatHint');
  const title = data?.active_thread_title || '讨论话题';
  if (titleEl) titleEl.textContent = title;
  if (hintEl) {
    const n = (data?.threads || []).length;
    hintEl.textContent = n > 1
      ? `${n} 个话题 · 侧栏切换 · 不写章节`
      : '普通聊天，无提示词限制，不写入章节';
  }
}

function renderFreeChatMessages(messages) {
  const log = document.getElementById('freeChatMessages');
  clearEl(log);
  if (!messages.length) {
    const empty = cloneTplEl('tpl-chat-empty');
    empty.querySelector('p').innerHTML = '普通聊天窗口，没有额外提示词。<br>和写书分开，不会写入章节。';
    log.appendChild(empty);
    return;
  }
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    const el = cloneTplEl('tpl-chat-msg');
    el.classList.add(m.role);
    el.dataset.msgIndex = String(i);
    el.querySelector('.label').textContent = m.role === 'user' ? '你' : 'AI';
    el.querySelector('.msg-body').textContent = m.content || '';
    const copyBtn = el.querySelector('.msg-copy-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        copyFreeChatMessage(m.content);
      });
    }
    const delBtn = el.querySelector('.msg-delete-btn');
    if (delBtn) {
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteFreeChatMessage(i, m.role);
      });
    }
    log.appendChild(el);
  }
  scrollFreeChatToBottom('auto');
}

async function loadFreeChat(refreshSidebarPanel = true) {
  const data = await api('/free-chat/history');
  dataCache.freeChat.messages = data.messages || [];
  renderFreeChatMessages(dataCache.freeChat.messages);
  updateFreeChatToolbar(data);
  const sel = document.getElementById('freeProviderSel');
  if (sel && data.provider) sel.value = data.provider;
  updateFreeProviderHint(data.provider || 'deepseek');
  if (refreshSidebarPanel && state.sidebar === 'freechats') {
    scheduleRender({ sidebar: true });
  }
}

async function createFreeChatThread() {
  const title = prompt('新话题名称（可留空，首条消息会自动命名）', '');
  if (title === null) return;
  await runWithLoading(async () => {
    await api('/free-chat/threads', {
      method: 'POST',
      body: JSON.stringify({ title: title.trim() }),
    });
    await loadFreeChat();
    await loadStatus();
    toast('已新建话题');
  });
}

async function switchFreeChatThread(threadId) {
  if (!threadId) return;
  await api('/free-chat/active-thread', {
    method: 'PUT',
    body: JSON.stringify({ thread_id: threadId }),
  });
  setMode('free');
  await loadFreeChat();
}

async function renameFreeChatThread() {
  const data = await api('/free-chat/history');
  const current = data.active_thread_title || '';
  const title = prompt('重命名当前话题', current);
  if (title === null || !title.trim()) return;
  await api(`/free-chat/threads/${encodeURIComponent(data.active_thread_id)}`, {
    method: 'PUT',
    body: JSON.stringify({ title: title.trim() }),
  });
  await loadFreeChat();
  toast('话题已重命名');
}

async function deleteFreeChatThread() {
  const data = await api('/free-chat/history');
  if ((data.threads || []).length <= 1) return toast('至少保留一个话题');
  if (!confirm(`删除话题「${data.active_thread_title || '当前'}」？\n\n对话记录将不可恢复。`)) return;
  await api(`/free-chat/threads/${encodeURIComponent(data.active_thread_id)}`, {
    method: 'DELETE',
  });
  await loadFreeChat();
  await loadStatus();
  toast('话题已删除');
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
      const res = await api('/free-chat', { method: 'POST', body: JSON.stringify({ content, provider }) }, FREE_CHAT_API_TIMEOUT_MS);
      input.value = '';
      await loadFreeChat();
      await loadStatus();
      if (res.output_truncated) {
        toast(`回复可能已达输出上限（${res.max_tokens || '?'} tokens），可在 .env 调整 NOVEL_FREE_CHAT_MAX_TOKENS`);
      }
    } catch (e) {
      const mins = Math.round(FREE_CHAT_API_TIMEOUT_MS / 60000);
      errEl.textContent = e.message === '请求超时，请检查网络或稍后重试'
        ? `自由聊等待超过 ${mins} 分钟（上下文大 + Claude 较慢）。可在 ⚙️ 减少「自由聊保留轮数」，或换 DeepSeek 再试。`
        : e.message;
    } finally {
      removeTypingIndicator();
    }
  }, { btnId: 'sendFreeChatBtn', loadingText: '生成中（超长回复，最长约 30 分钟）…' });
}

async function clearFreeChat() {
  if (!confirm('清空当前话题的全部消息？\n\n（其他话题不受影响）')) return;
  await api('/free-chat/clear', { method: 'POST' });
  await loadFreeChat();
}

async function deleteFreeChatMessage(index, role) {
  if (_isChatSending || _isQualityBusy) {
    toast('请等待当前请求完成后再删除');
    return;
  }
  const who = role === 'user' ? '你的消息' : 'AI 回复';
  if (!confirm(`删除这条${who}？\n\n删除后不可恢复，且会影响后续 API 上下文。`)) return;
  try {
    await api(`/free-chat/messages/${index}`, { method: 'DELETE' });
    await loadFreeChat();
    toast('已删除');
  } catch (e) {
    toast(e.message || '删除失败');
  }
}

function formatFinalizeResultBody(r) {
  const lines = [];
  const a = r.archive || {};
  lines.push('【已自动写入档案】');
  if (a.summary?.ok) {
    const arch = a.summary.archived_count
      ? `（${a.summary.archived_count} 条已归档 summaries_archive）`
      : '';
    lines.push(`概述 → summaries_recent${arch}\n${a.summary.full_text || a.summary.text || ''}`);
  }
  if (a.observe?.applied_count) {
    lines.push(`角色观察 → 已写入 ${a.observe.applied_count} 条`);
    for (const it of a.observe.items || []) {
      if (it.applied) lines.push(`  · ${it.target_file}: ${(it.proposed_text || '').slice(0, 120)}`);
    }
  }
  if (a.detail_locked?.ok && a.detail_locked.text) {
    lines.push(`细节钉子 → plot_threads_locked\n${a.detail_locked.text}`);
  }
  if (a.plot_new_threads?.appended_count) {
    lines.push(`新伏笔 → active 未回收 ×${a.plot_new_threads.appended_count}`);
    for (const it of a.plot_new_threads.items || []) lines.push(`  ${it}`);
  }
  const pp = r.plot_proposal || {};
  if (pp.advanced) lines.push(`\n【伏笔推进（参考）】\n${pp.advanced}`);
  if (pp.resolved) lines.push(`\n【疑似已回收（请手动确认）】\n${pp.resolved}`);
  const q = r.quality || {};
  lines.push('\n【质检报告】');
  for (const key of ['continuity', 'character_drift', 'repetition', 'pacing']) {
    const block = q[key];
    if (!block || block.skipped) continue;
    const label = { continuity: '连续性', character_drift: '人物', repetition: '套话', pacing: '爽点' }[key];
    lines.push(`\n## ${label}${block.issue_count ? `（${block.issue_count} 条）` : ''}\n${block.text || ''}`);
  }
  if ((r.manual_todos || []).length) {
    lines.push('\n【还需你处理】');
    for (const t of r.manual_todos) lines.push(`- ${t.label}`);
  }
  if (r.total_cost_usd != null) lines.push(`\n费用合计：$${Number(r.total_cost_usd).toFixed(4)}`);
  return lines.join('\n');
}

function formatFinalizeHint(r) {
  const parts = [];
  const a = r.archive || {};
  if (a.summary?.ok) parts.push('概述');
  if (a.observe?.applied_count) parts.push(`观察×${a.observe.applied_count}`);
  if (a.detail_locked?.ok && a.detail_locked.text) parts.push('钉子');
  if (a.plot_new_threads?.appended_count) parts.push(`伏笔×${a.plot_new_threads.appended_count}`);
  const q = r.quality || {};
  if (q.continuity?.text) parts.push('连续性');
  if (q.character_drift?.text) parts.push('人物');
  if (q.repetition?.text) parts.push('套话');
  if (q.pacing?.ok) parts.push('爽点');
  if (r.partial) return `⚠️ 部分完成：${parts.join('、') || '见详情'}。${(r.errors || []).join('；')}`;
  return parts.length
    ? `✅ 定稿完成：${parts.join('、')}。侧栏「质量记录」可回看。`
    : `⚠️ ${(r.errors || []).join('；') || '未完成任何步骤'}`;
}

async function runPostChapterFinalize(chapterNum = null, { skipConfirm = false, runOutline = false } = {}) {
  const num = chapterNum || getWriteChapterNum();
  if (!num) {
    toast('请先选择章节');
    return;
  }
  if (
    !skipConfirm
    && !confirm(
      `为第 ${num} 章运行「本章定稿」？\n\n将自动：写入档案（概述/观察/钉子/新伏笔）+ 质检（连续性/人物/套话/爽点）\n\n约 2–3 次 API。`,
    )
  ) {
    return;
  }
  const btnIds = [
    'runPostChapterFinalizeBtn',
    'runPostChapterMaintainBtn',
    'runPostChapterMaintainQuickBtn',
    'runPostChapterMaintainModalBtn',
    'runPostChapterMaintainWriteBtn',
  ];
  await runWithLoading(async () => {
    const finalizeStart = Date.now();
    // #region agent log
    _dbgUiLog('app.js:runPostChapterFinalize', 'finalize request start', {
      chapter_num: num,
      runOutline,
      timeoutMs: FINALIZE_API_TIMEOUT_MS,
    }, 'F1');
    // #endregion
    let r;
    try {
      r = await api('/post-chapter/finalize', {
        method: 'POST',
        body: JSON.stringify({
          chapter_num: num,
          run_pacing: true,
          run_outline: runOutline,
          repetition_scope: 'current',
          auto_apply_observe: true,
          auto_append_locked: true,
          auto_append_plot_new: true,
        }),
      }, FINALIZE_API_TIMEOUT_MS);
      // #region agent log
      _dbgUiLog('app.js:runPostChapterFinalize', 'finalize request ok', {
        ok: r.ok,
        partial: r.partial,
        chapter_num: r.chapter_num,
        calls: (r.calls || []).length,
        elapsedMs: Date.now() - finalizeStart,
        archiveSummaryOk: r.archive?.summary?.ok,
      }, 'F1');
      // #endregion
    } catch (err) {
      // #region agent log
      _dbgUiLog('app.js:runPostChapterFinalize', 'finalize request error', {
        error: String(err?.message || err).slice(0, 300),
        elapsedMs: Date.now() - finalizeStart,
        timeoutMs: FINALIZE_API_TIMEOUT_MS,
      }, 'F1');
      // #endregion
      throw err;
    }
    invalidateCache(['plan']);
    invalidateQualityCache();
    const body = formatFinalizeResultBody(r);
    const hint = formatFinalizeHint(r);
    showQualityResult(`本章定稿 · 第 ${r.chapter_num || num} 章`, body, hint);
    toast(r.partial ? '本章定稿部分完成' : '本章定稿完成');
    document.getElementById('postChapterModal')?.remove();
    fetchGuideStatus(true).then(() =>
      renderGuideHints(state.mode === 'chat' ? 'chat' : state.mode),
    );
    if (state.sidebar === 'quality') scheduleRender({ sidebar: true });
  }, { btnIds, loadingText: '本章定稿中…' });
}

/** @deprecated 请用 runPostChapterFinalize；保留别名兼容旧 onclick */
async function runPostChapterMaintain(chapterNum = null, opts = {}) {
  return runPostChapterFinalize(chapterNum, opts);
}

async function runSummary(chapterNum = null) {
  const num = chapterNum || getWriteChapterNum();
  const label = num ? `第 ${num} 章` : '写作目标章';
  if (!confirm(`为${label}生成概述并追加到 summaries_recent.md？\n\n（只追加不覆盖；可在设置→档案留痕撤销）`)) return;
  await runWithLoading(async () => {
    const body = num ? JSON.stringify({ chapter_num: num }) : '{}';
    const r = await api('/summary', { method: 'POST', body });
    toast('概述已写入 summaries_recent.md');
    invalidateCache(['plan']);
    invalidateQualityCache();
    fetchGuideStatus(true).then(() => renderGuideHints(state.mode === 'chat' ? 'chat' : state.mode));
    showQualityResult(
      `第 ${r.chapter_num || num || '?'} 章 · 概述`,
      r.reply,
      '已追加到 summaries_recent.md · 侧栏「质量记录」可回看',
    );
  }, { btnIds: ['runSummaryBtn', 'runSummaryQuickBtn', 'runSummaryWriteBtn'], loadingText: '生成中…' });
}

async function runCheck(chapterNum = null) {
  const num = chapterNum || getQualityChapterNum() || getWriteChapterNum();
  const scope = getQualityScope();
  const scopeLabel = { current: '当前章', recent3: '最近3章', all: '全书' }[scope] || scope;
  await runWithLoading(async () => {
    const r = await api('/check', {
      method: 'POST',
      body: JSON.stringify({ chapter_num: num || undefined, scope }),
    });
    invalidateQualityCache();
    await refreshQualityHistoryList();
    showQualityResult(
      `连续性检查 · ${scopeLabel} · 第 ${r.chapter_num || num || '?'} 章锚点`,
      r.reply,
    );
    toast('连续性检查完成');
  }, { btnIds: ['runCheckBtn', 'runCheckBtnDock', 'qualityBtnContinuity'], loadingText: '检查中…' });
}

async function runCharacterDrift(chapterNum = null) {
  const num = chapterNum || getQualityChapterNum() || getWriteChapterNum();
  await runWithLoading(async () => {
    const r = await api('/check/character-drift', {
      method: 'POST',
      body: JSON.stringify({ chapter_num: num || undefined }),
    });
    invalidateQualityCache();
    await refreshQualityHistoryList();
    showQualityResult(`人物检查 · 第 ${r.chapter_num || num || '?'} 章`, r.reply);
  }, { btnIds: ['runCharDriftBtn', 'runCharDriftBtnDock', 'qualityBtnCharacter'], loadingText: '检查中…' });
}

let _observeState = null;

function closeObserveModal() {
  document.getElementById('observeModal')?.classList.add('hidden');
  _observeState = null;
}

function closeObserveModalBackdrop(e) {
  if (e.target.id === 'observeModal') closeObserveModal();
}

function observeChangeableCount() {
  return (_observeState?.items || []).filter((it) => it.has_change).length;
}

function syncObserveModalFooter() {
  const sub = document.getElementById('observeModalSub');
  const acceptAll = document.getElementById('observeBtnAcceptAll');
  const apply = document.getElementById('observeBtnApply');
  const hasItems = (_observeState?.items || []).length > 0;
  const n = observeChangeableCount();
  if (!hasItems) {
    if (sub) sub.textContent = '未能解析为可接受提案，仅展示 AI 原文。请关闭后手动编辑全局文件。';
    acceptAll?.classList.add('hidden');
    apply?.classList.add('hidden');
    return;
  }
  if (n === 0) {
    if (sub) sub.textContent = '所有项均为「无变化」，无需写入。点「关闭」即可。';
    acceptAll?.classList.add('hidden');
    apply?.classList.add('hidden');
    return;
  }
  if (sub) {
    sub.textContent = `共 ${n} 条可接受提案：请先点「✅ 接受」或「全部接受」，再点「确认并写入」。`;
  }
  acceptAll?.classList.remove('hidden');
  apply?.classList.remove('hidden');
}

function renderObserveModal() {
  const bodyEl = document.getElementById('observeModalBody');
  const summaryEl = document.getElementById('observeModalSummary');
  if (!bodyEl || !_observeState) return;
  const titleEl = document.getElementById('observeModalTitle');
  if (titleEl) titleEl.textContent = `📋 角色观察 · 第${_observeState.chapter_num}章`;
  if (summaryEl) {
    if (_observeState.summary) {
      summaryEl.textContent = _observeState.summary;
      summaryEl.classList.remove('hidden');
    } else {
      summaryEl.classList.add('hidden');
    }
  }
  if (!_observeState.items.length) {
    bodyEl.innerHTML =
      `<p class="muted">未能解析结构化提案。请查看 AI 原文：</p>` +
      `<pre style="white-space:pre-wrap;font-size:12px">${escapeHtml(_observeState.raw || '')}</pre>`;
    syncObserveModalFooter();
    return;
  }
  bodyEl.innerHTML = _observeState.items
    .map((item) => {
      const noChange = !item.has_change;
      const cls = noChange ? 'observe-card no-change' : 'observe-card';
      const changes =
        item.changes?.length &&
        item.changes
          .map((c) => `<li>${escapeHtml(c.field || '')}：${escapeHtml(c.from || '—')} → ${escapeHtml(c.to || '—')}</li>`)
          .join('');
      const exposure = item.exposure_level
        ? `<div class="scene">暴露程度：${escapeHtml(item.exposure_level)}</div>`
        : '';
      const editBlock = item.showEdit
        ? `<textarea class="observe-edit" data-observe-id="${escapeHtml(item.id)}" oninput="onObserveEditInput('${escapeHtml(item.id)}', this.value)">${escapeHtml(item.edited_text || item.proposed_text || '')}</textarea>`
        : '';
      const acceptCls = item.accepted ? 'btn btn-sm active' : 'btn btn-sm';
      const rejectCls = item.accepted === false && !noChange ? 'btn btn-sm btn-ghost active' : 'btn btn-sm btn-ghost';
      const targetKey = item.target_file || (item.id === 'private_frequency' ? 'char_static' : 'char_dynamic');
      const targetBadge = `<span class="observe-target-badge">写入 → ${escapeHtml(globalFileLabel(targetKey))}</span>`;
      return (
        `<div class="${cls}">` +
        `<h4>${escapeHtml(item.title || item.id)}</h4>` +
        targetBadge +
        (noChange
          ? `<p class="muted">无变化</p>`
          : `<div class="scene">${escapeHtml(item.scene || '（场景未描述）')}</div>` +
            exposure +
            `<div class="suggestion">→ ${escapeHtml(item.suggestion || item.proposed_text || '')}</div>` +
            (changes ? `<ul style="margin:0 0 8px 16px;font-size:12px">${changes}</ul>` : '') +
            `<div class="observe-card-actions">` +
            `<button type="button" class="${acceptCls}" onclick="setObserveItem('${escapeHtml(item.id)}', true)">✅ 接受</button>` +
            `<button type="button" class="btn btn-sm btn-ghost" onclick="toggleObserveEdit('${escapeHtml(item.id)}')">✏️ 改一下</button>` +
            `<button type="button" class="${rejectCls}" onclick="setObserveItem('${escapeHtml(item.id)}', false)">❌ 拒绝</button>` +
            `</div>` +
            editBlock) +
        `</div>`
      );
    })
    .join('');
  syncObserveModalFooter();
}

function openObserveModal(data) {
  _observeState = {
    chapter_num: data.chapter_num,
    summary: data.summary || '',
    raw: data.reply || '',
    items: (data.items || []).map((it) => ({
      ...it,
      accepted: false,
      edited_text: it.proposed_text || '',
      showEdit: false,
    })),
  };
  renderObserveModal();
  document.getElementById('observeModal')?.classList.remove('hidden');
}

function setObserveItem(id, accepted) {
  const item = _observeState?.items?.find((i) => i.id === id);
  if (!item || !item.has_change) return;
  item.accepted = accepted;
  renderObserveModal();
}

function acceptAllObserveItems() {
  if (!_observeState?.items?.length) return;
  let n = 0;
  for (const it of _observeState.items) {
    if (it.has_change) {
      it.accepted = true;
      n++;
    }
  }
  if (!n) return toast('没有需要接受的变化项');
  renderObserveModal();
  toast(`已接受 ${n} 条有变化的提案`);
}

function toggleObserveEdit(id) {
  const item = _observeState?.items?.find((i) => i.id === id);
  if (!item || !item.has_change) return;
  item.showEdit = !item.showEdit;
  item.accepted = true;
  if (!item.edited_text) item.edited_text = item.proposed_text || item.suggestion || '';
  renderObserveModal();
}

function onObserveEditInput(id, value) {
  const item = _observeState?.items?.find((i) => i.id === id);
  if (item) item.edited_text = value;
}

async function runCharacterObserve(chapterNum = null) {
  await runWithLoading(async () => {
    const num = chapterNum || getWriteChapterNum();
    const payload = { auto_apply: true, ...(num ? { chapter_num: num } : {}) };
    const r = await api('/observe', { method: 'POST', body: JSON.stringify(payload) });
    invalidateQualityCache();
    const applied = r.auto_applied || [];
    let hint = '完整报告已保存到侧栏「质量记录」。';
    if (applied.length) {
      hint = `✅ 已自动写入 ${applied.length} 条到 char_static / char_dynamic。${hint}`;
      toast(`角色观察：已写入 ${applied.length} 条`);
      fetchGuideStatus(true).then(() =>
        renderGuideHints(state.mode === 'chat' ? 'chat' : state.mode),
      );
    } else if (r.apply_error) {
      toast(`角色观察：${r.apply_error}`);
      hint = `⚠️ ${r.apply_error}。${hint}`;
    } else if (r.parse_ok) {
      toast('角色观察完成，本章无新变更');
    } else {
      toast('未能解析 JSON 提案，已尝试摘要回退写入');
    }
    const display = r.summary ? `${r.summary}\n\n---\n\n${r.reply || ''}` : (r.reply || '');
    showQualityResult(`角色观察 · 第 ${r.chapter_num || num || '?'} 章`, display, hint);
    if (state.sidebar === 'quality') scheduleRender({ sidebar: true });
  }, { btnIds: ['runObserveBtn', 'runObserveQuickBtn', 'runObserveWriteBtn'], loadingText: '分析中…' });
}

async function applyObserveProposals() {
  if (!_observeState?.items?.length) {
    closeObserveModal();
    return;
  }
  const items = _observeState.items
    .filter((it) => it.has_change && it.accepted)
    .map((it) => ({
      id: it.id,
      target_file: it.target_file,
      accepted: true,
      proposed_text: it.proposed_text || '',
      edited_text: (it.edited_text || it.proposed_text || '').trim(),
    }));
  if (!items.length) {
    toast('请先「接受」至少一条有变化的提案');
    return;
  }
  if (!confirm(`确认写入 ${items.length} 条提案到 char_static / char_dynamic？`)) return;
  try {
    const r = await api('/observe/apply', {
      method: 'POST',
      body: JSON.stringify({ items, chapter_num: _observeState.chapter_num }),
    });
    toast(`已写入 ${(r.applied || []).length} 条`);
    closeObserveModal();
    fetchGuideStatus(true).then(() => renderGuideHints(state.mode === 'chat' ? 'chat' : state.mode));
  } catch (e) {
    toast(e.message || '写入失败');
  }
}

async function runDetailExtract() {
  const num = getWriteChapterNum();
  await runWithLoading(async () => {
    const r = await api('/extract/details', {
      method: 'POST',
      body: JSON.stringify({ auto_append: true, chapter_num: num || undefined }),
    });
    invalidateQualityCache();
    const hint = r.appended
      ? '✅ 已自动追加到 plot_threads_locked.md。侧栏「质量记录」可回看。'
      : (r.reply?.trim()
        ? '⚠️ 生成成功但未写入文件（内容与磁盘相同或为空）。报告已保存到质量记录。'
        : '未写入文件（章节正文可能为空）。报告已保存到质量记录。');
    showQualityResult(`细节提取 · 第 ${r.chapter_num || num || '?'} 章`, r.reply, hint);
    if (r.appended) toast('细节钉子已自动追加');
    else if (r.reply?.trim()) toast('细节提取完成，但未追加到文件（请查质量记录）');
    if (state.sidebar === 'quality') scheduleRender({ sidebar: true });
  }, { btnIds: ['runDetailExtractBtn', 'runDetailExtractQuickBtn', 'runDetailExtractWriteBtn'], loadingText: '提取中…' });
}

async function runRepetitionCheck(chapterNum = null) {
  const scope = getQualityScope();
  const num = chapterNum || getQualityChapterNum() || getWriteChapterNum();
  const scopeLabel = { current: '当前章', recent3: '最近3章', all: '全书' }[scope] || scope;
  await runWithLoading(async () => {
    const r = await api('/check/repetition', {
      method: 'POST',
      body: JSON.stringify({ scope, chapter_num: num || undefined }),
    });
    invalidateQualityCache();
    await refreshQualityHistoryList();
    showQualityResult(`套话检查 · ${scopeLabel}`, r.reply);
  }, { btnIds: ['runRepetitionBtn', 'runRepetitionBtnDock', 'qualityBtnStyle'], loadingText: '检查中…' });
}

async function runFemaleFictionReview() {
  const mode = document.getElementById('femaleReviewMode')?.value || 'chapter';
  const profile_id = document.getElementById('femaleReviewProfile')?.value || undefined;
  const revise = document.getElementById('femaleReviewRevise')?.checked || false;
  const rewriteOnly = _femaleReviewProfilesCache?.active?.rewrite_only
    || (profile_id && ['world-tomato', 'world-qimao'].includes(profile_id));
  const write_back = !rewriteOnly && revise
    && (document.getElementById('femaleReviewWriteBack')?.checked || false);
  const sync_archive = write_back
    && (document.getElementById('femaleReviewSyncArchive')?.checked || false);
  const num = getQualityChapterNum() || getWriteChapterNum();
  const modeLabel = { chapter: '章节', outline: '大纲', characters: '人物' }[mode] || mode;
  if (mode === 'chapter' && !num) return toast('请先选择锚点章');
  if (mode === 'chapter' && write_back) {
    if (!confirm(`将覆盖第 ${num} 章正文（会先备份）${sync_archive ? '，并同步全局档案' : ''}。继续？`)) return;
  }
  await runWithLoading(async () => {
    const r = await api('/review/female-fiction', {
      method: 'POST',
      body: JSON.stringify({
        mode,
        chapter_num: mode === 'chapter' ? num : undefined,
        profile_id,
        revise: rewriteOnly ? false : revise,
        write_back: mode === 'chapter' ? write_back : false,
        sync_archive: mode === 'chapter' ? sync_archive : false,
      }),
    }, QUALITY_FULL_TIMEOUT_MS);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    const ch = r.chapter_num ? ` · 第 ${r.chapter_num} 章` : '';
    const prof = r.profile_label ? ` · ${r.profile_label}` : '';
    const action = r.rewrite_only ? '女频直改稿' : (revise ? '审阅改稿' : '女频审阅');
    let hint = '';
    let customButtons = [];
    if (r.pending_accept && r.log_id) {
      hint = '请通读下方改稿全文。满意后点「采纳并同步档案」写回章节并更新全局文件。';
      customButtons = femaleFictionAcceptButtons(r.log_id);
    } else if (r.write_back) {
      hint = `✅ 已写回第 ${r.chapter_num} 章${r.chapter_title ? `（${r.chapter_title}）` : ''}。`;
      if (r.sync_archive) {
        hint += r.archive_synced
          ? ' 档案已同步。'
          : ` ⚠️ 档案同步未完全成功${r.archive_errors?.length ? '：' + r.archive_errors.join('；') : ''}`;
      }
    } else if (revise && !r.revised_text) {
      hint = '⚠️ 模型未输出改稿正文，请重试。';
    }
    showQualityResult(`${action} · ${modeLabel}${ch}${prof}`, r.reply, hint, { customButtons });
    if (r.write_back) {
      invalidateCache(['chapters', 'quality']);
      if (r.archive_synced) invalidateCache(['plan']);
      toast(r.archive_synced ? `第 ${r.chapter_num} 章已更新并同步档案` : `第 ${r.chapter_num} 章已更新`);
    }
  }, { btnId: 'femaleReviewBtn', loadingText: (rewriteOnly || revise) ? '改稿中…' : '女频审阅中…' });
}

function bindFemaleReviewReviseToggle() {
  const reviseEl = document.getElementById('femaleReviewRevise');
  const writeEl = document.getElementById('femaleReviewWriteBack');
  const archiveEl = document.getElementById('femaleReviewSyncArchive');
  const writeOpts = document.getElementById('femaleReviewWriteOpts');
  if (!reviseEl || !writeEl) return;
  const isRewriteOnly = () =>
    _femaleReviewProfilesCache?.active?.rewrite_only
    || ['world-tomato', 'world-qimao'].includes(
      document.getElementById('femaleReviewProfile')?.value || '',
    );
  const sync = () => {
    const ro = isRewriteOnly();
    reviseEl.disabled = ro;
    if (ro) reviseEl.checked = false;
    if (writeOpts) writeOpts.classList.toggle('hidden', ro);
    writeEl.disabled = !reviseEl.checked || ro;
    if (archiveEl) archiveEl.disabled = !writeEl.checked || writeEl.disabled;
  };
  reviseEl.addEventListener('change', sync);
  writeEl.addEventListener('change', sync);
  document.getElementById('femaleReviewProfile')?.addEventListener('change', sync);
  sync();
}

async function runReaderReview() {
  const scope = getQualityScope();
  const num = getQualityChapterNum() || getWriteChapterNum();
  const scopeLabel = { current: '当前章', recent3: '最近3章', all: '全书' }[scope] || scope;
  await runWithLoading(async () => {
    const r = await api('/quality/reader', {
      method: 'POST',
      body: JSON.stringify({ scope, chapter_num: num || undefined }),
    }, QUALITY_FULL_TIMEOUT_MS);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    showQualityResult(`读者审阅 · ${scopeLabel} · 第 ${r.chapter_num || num} 章锚点`, r.reply);
  }, { btnId: 'qualityBtnReader', loadingText: '审阅中…' });
}

async function runEditorReview() {
  const scope = getQualityScope();
  const num = getQualityChapterNum() || getWriteChapterNum();
  const scopeLabel = { current: '当前章', recent3: '最近3章', all: '全书' }[scope] || scope;
  await runWithLoading(async () => {
    const r = await api('/quality/editor', {
      method: 'POST',
      body: JSON.stringify({ scope, chapter_num: num || undefined }),
    }, QUALITY_FULL_TIMEOUT_MS);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    showQualityResult(`编辑审阅 · ${scopeLabel} · 第 ${r.chapter_num || num} 章锚点`, r.reply);
  }, { btnId: 'qualityBtnEditor', loadingText: '审阅中…' });
}

async function runQualityFullReview() {
  const scope = getQualityScope();
  const num = getQualityChapterNum() || getWriteChapterNum();
  if (!num) return toast('请先选择锚点章');
  const scopeLabel = { current: '当前章', recent3: '最近3章', all: '全书' }[scope] || scope;
  if (!confirm(`一键全查（只读）\n\n锚点：第 ${num} 章 · 范围：${scopeLabel}\n\n含套话/连续性/人物/爽点/读者/编辑，约 4–6 次 API，不会写档案。`)) {
    return;
  }
  await runWithLoading(async () => {
    const r = await api('/quality/full', {
      method: 'POST',
      body: JSON.stringify({
        chapter_num: num,
        scope,
        run_pacing: true,
        run_reader: true,
        run_editor: true,
      }),
    }, QUALITY_FULL_TIMEOUT_MS);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    const hint = r.errors?.length
      ? `部分步骤失败：${r.errors.join('；')}`
      : '只读报告已入库，改稿后请「本章定稿」或重新全查对比';
    showQualityResult(`一键全查 · ${scopeLabel} · 第 ${r.chapter_num || num} 章`, r.reply, hint);
    toast(r.errors?.length ? '一键全查部分完成' : '一键全查完成');
  }, { btnId: 'qualityBtnFull', loadingText: '全查中（较久）…' });
}

function getQualityScope() {
  const q = document.getElementById('qualityScopeSel')?.value;
  if (q) return q;
  return document.getElementById('repetitionScopeSel')?.value || 'current';
}

function getQualityChapterNum() {
  const sel = document.getElementById('qualityChapterSel');
  if (sel?.value) return parseInt(sel.value, 10);
  return getWriteChapterNum();
}

async function fillQualityChapterSel() {
  const sel = document.getElementById('qualityChapterSel');
  if (!sel) return;
  await ensurePlanData();
  const chapters = _chaptersWithBody();
  const prev = sel.value;
  sel.replaceChildren();
  for (const ch of chapters) {
    const opt = document.createElement('option');
    opt.value = String(ch.num);
    opt.textContent = `第 ${ch.num} 章`;
    sel.appendChild(opt);
  }
  const target = getWriteChapterNum() || chapters[chapters.length - 1]?.num;
  if (target) sel.value = String(target);
  else if (prev) sel.value = prev;
}

function onQualityChapterChange() {
  const num = getQualityChapterNum();
  if (num) setState({ writeChapterNum: num }, 'none');
}

let _deconstructLatestReply = '';

function updateDeconstructCharCount() {
  const ta = document.getElementById('deconstructInput');
  const el = document.getElementById('deconstructCharCount');
  if (!ta || !el) return;
  const n = (ta.value || '').replace(/\s/g, '').length;
  el.textContent = `${n.toLocaleString()} 字（不含空白）`;
}

async function refreshDeconstructHistory() {
  const list = document.getElementById('deconstructHistoryList');
  if (!list) return;
  const entries = await ensureQualityLog(true);
  const rows = entries.filter((e) => e.kind === 'deconstruct');
  clearEl(list);
  if (!rows.length) {
    list.textContent = '尚无记录，完成一次拆解后会出现在这里。';
    return;
  }
  for (const e of rows.slice(0, 15)) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'deconstruct-history-item';
    btn.innerHTML =
      `<span class="deconstruct-history-meta">${escapeHtml(formatRecordTime(e.created_at))}</span>` +
      `<span class="deconstruct-history-summary">${escapeHtml(e.summary || e.preview || '参考拆文')}</span>`;
    btn.addEventListener('click', () => openDeconstructEntry(e.id));
    list.appendChild(btn);
  }
}

async function openDeconstructEntry(id) {
  const row = await api(`/quality/log/${encodeURIComponent(id)}`);
  _deconstructLatestReply = row.body || '';
  const panel = document.getElementById('deconstructResult');
  const body = document.getElementById('deconstructResultBody');
  if (panel && body) {
    body.textContent = _deconstructLatestReply;
    panel.classList.remove('hidden');
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

async function renderDeconstructView() {
  updateDeconstructCharCount();
  await refreshDeconstructHistory();
  const ta = document.getElementById('deconstructInput');
  if (ta && !ta.dataset.bound) {
    ta.dataset.bound = '1';
    ta.addEventListener('input', updateDeconstructCharCount);
  }
}

async function runDeconstruct() {
  const ta = document.getElementById('deconstructInput');
  const text = (ta?.value || '').trim();
  if (text.replace(/\s/g, '').length < 80) {
    toast('请至少粘贴 80 字参考文');
    return;
  }
  const sourceLabel = document.getElementById('deconstructLabel')?.value?.trim() || '';
  const includeBook = document.getElementById('deconstructUseBookCtx')?.checked !== false;
  await runWithLoading(async () => {
    const r = await api('/deconstruct', {
      method: 'POST',
      body: JSON.stringify({
        text,
        source_label: sourceLabel,
        include_book_context: includeBook,
      }),
    }, QUALITY_FULL_TIMEOUT_MS);
    _deconstructLatestReply = r.reply || '';
    const panel = document.getElementById('deconstructResult');
    const body = document.getElementById('deconstructResultBody');
    if (panel && body) {
      body.textContent = _deconstructLatestReply;
      panel.classList.remove('hidden');
    }
    invalidateQualityCache();
    await refreshDeconstructHistory();
    toast('拆解完成');
  }, { btnId: 'deconstructRunBtn', loadingText: '拆解中…' });
}

function copyDeconstructResult() {
  if (!_deconstructLatestReply) return toast('暂无报告');
  navigator.clipboard?.writeText(_deconstructLatestReply).then(
    () => toast('已复制到剪贴板'),
    () => toast('复制失败，请手动选择复制'),
  );
}

async function refreshQualityHistoryList() {
  const list = document.getElementById('qualityHistoryList');
  if (!list) return;
  const entries = await ensureQualityLog(true);
  clearEl(list);
  const reviewKinds = new Set([
    'finalize', 'continuity', 'character_drift', 'repetition', 'pacing',
    'reader_review', 'editor_review', 'quality_full',
    'batch_world_review', 'batch_world_finalize', 'world_remediate', 'world_batch_generate',
    'female_fiction_review', 'female_fiction_accept',
  ]);
  const filtered = entries.filter((e) => reviewKinds.has(e.kind));
  if (!filtered.length) {
    const empty = document.createElement('p');
    empty.className = 'quality-history__empty';
    empty.textContent = '尚无审阅记录。运行单项或「一键全查」后会出现在这里。';
    list.appendChild(empty);
    return;
  }
  for (const e of filtered.slice(0, 30)) {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'quality-history__item';
    const ch = e.chapter_num ? `第${e.chapter_num}章 · ` : '';
    const saved = e.persisted ? ' · ✓已写档案' : '';
    row.innerHTML =
      `<span class="quality-history__meta">${escapeHtml(e.created_at || '')} · ${escapeHtml(e.label || e.kind)}${saved}</span>` +
      `<span class="quality-history__summary">${escapeHtml(e.summary || e.preview || '')}</span>`;
    row.addEventListener('click', () => openQualityLogEntry(e.id));
    list.appendChild(row);
  }
}

async function renderQualityView() {
  await fillQualityChapterSel();
  await refreshQualityHistoryList();
  await refreshWorldBatchStatus();
  await refreshFemaleReviewProfiles();
  const status = await fetchGuideStatus(true);
  if (status) renderQualityGuideHints(status);
}

let _worldBatchCache = null;
let _lastRemediateJobId = null;

async function refreshWorldBatchStatus() {
  const panel = document.getElementById('worldBatchPanel');
  const textEl = document.getElementById('worldBatchStatusText');
  const hintEl = document.getElementById('worldBatchHint');
  const reviewBtn = document.getElementById('worldBatchReviewBtn');
  const finalizeBtn = document.getElementById('worldBatchFinalizeBtn');
  const generateBtn = document.getElementById('worldGenerateBtn');
  const remediateBtn = document.getElementById('worldRemediateBtn');
  if (!textEl) return;
  try {
    const active = await api('/library/active');
    if (active.book?.type === 'short') {
      if (panel) panel.classList.add('hidden');
      return;
    }
    if (panel) panel.classList.remove('hidden');
    const s = await api('/batch/world/status');
    _worldBatchCache = s;
    const label = s.label || '当前世界';
    const plan = `第${s.chapter_from}–${s.chapter_to}章`;
    const written = s.written_count
      ? `已有正文 ${s.written_count} 章（第${s.written_from}–${s.written_to}）`
      : '尚无正文';
    const beats = s.beats_count
      ? ` · plan 已覆盖 ${s.beats_count} 章 Beat`
      : ' · ⚠️ plan 无 Beat';
    const prog = s.world_in_progress ? ' · 进行中' : (s.complete ? ' · 已写满' : '');
    textEl.textContent = `${label} · ${plan} · ${written}${beats}${prog}`;
    if (hintEl) {
      const pending = (s.beats_count || 0) - (s.written_count || 0);
      hintEl.innerHTML =
        `<strong>批量生成</strong>：按 Beat 自动写 ${plan}（缺 ${Math.max(0, pending)} 章会补写，已有正文默认跳过）。`
        + ` <strong>世界闭环</strong>：需已有正文。`;
    }
    const noWritten = !s.written_count;
    const noBeats = !(s.beats_count > 0);
    if (generateBtn) generateBtn.disabled = noBeats;
    if (reviewBtn) reviewBtn.disabled = noWritten;
    if (finalizeBtn) finalizeBtn.disabled = noWritten;
    if (remediateBtn) remediateBtn.disabled = noWritten;
  } catch (e) {
    textEl.textContent = '无法加载世界批次信息';
    if (hintEl) hintEl.textContent = String(e.message || e);
  }
}

function remediateResultButtons(jobId) {
  if (!jobId) return [];
  return [
    {
      label: '✅ 全部接受',
      className: 'btn btn-sm btn-primary',
      onClick: () => acceptRemediateJob(jobId),
    },
    {
      label: '↩️ 撤销某章',
      className: 'btn btn-sm',
      onClick: () => revertRemediateChapter(jobId),
    },
  ];
}

async function acceptRemediateJob(jobId) {
  const id = jobId || _lastRemediateJobId;
  if (!id) return toast('无闭环任务');
  try {
    await api(`/batch/jobs/${encodeURIComponent(id)}/accept`, { method: 'POST' });
    toast('已确认接受全部改动');
  } catch (e) {
    toast(e.message || '确认失败');
  }
}

async function revertRemediateChapter(jobId) {
  const id = jobId || _lastRemediateJobId;
  if (!id) return toast('无闭环任务');
  const raw = prompt('撤销第几章？（输入章号，仅恢复正文快照，不调 API）');
  const num = parseInt(raw ?? '', 10);
  if (!num || num < 1) return;
  if (!confirm(`确定将第 ${num} 章正文恢复为闭环前版本？（档案不回滚）`)) return;
  await runWithLoading(async () => {
    const r = await api(`/batch/jobs/${encodeURIComponent(id)}/revert`, {
      method: 'POST',
      body: JSON.stringify({ chapter_num: num }),
    });
    invalidateCache(['plan', 'chapters']);
    toast(r.warning ? `第 ${num} 章已恢复（${r.warning}）` : `第 ${num} 章已恢复`);
  }, { loadingText: '恢复中…' });
}

async function runWorldBatchGenerate() {
  const s = _worldBatchCache;
  if (!s?.beats_count) return toast('请先在规划模式填写 Scene Beat（如「第1-2章」）');
  const label = s.label || '当前世界';
  const from = s.chapter_from;
  const to = s.chapter_to;
  const pending = Math.max(0, (s.beats_count || 0) - (s.written_count || 0));
  const overwrite = s.written_count > 0 && confirm(
    '范围内部分章节已有正文。\n\n'
    + '点「确定」= 覆盖已有章节重新生成\n'
    + '点「取消」= 只补写空白章（推荐）',
  );
  if (
    !confirm(
      `批量生成「${label}」？\n\n`
        + `范围：第 ${from}–${to} 章\n`
        + `plan Beat 覆盖：${s.beats_count} 章\n`
        + `${overwrite ? '将覆盖已有正文' : `约补写 ${pending} 章（已有正文跳过）`}\n\n`
        + `将逐章调用写作 API（约 ${s.beats_count} 次），耗时较长，请勿关闭页面。`,
    )
  ) {
    return;
  }
  await runWithLoading(async () => {
    const r = await api(
      '/batch/world/generate',
      {
        method: 'POST',
        body: JSON.stringify({
          chapter_from: from,
          chapter_to: to,
          overwrite,
          skip_existing: !overwrite,
        }),
      },
      FINALIZE_API_TIMEOUT_MS,
    );
    invalidateCache(['plan', 'chapters', 'quality']);
    invalidateQualityCache();
    const title = `世界批量生成 · ${label} · 第${from}–${to}章`;
    const hint = r.partial
      ? `部分完成：${r.ok_count}/${r.target_count} 章`
      : `成功 ${r.ok_count}/${r.target_count} 章`;
    showQualityResult(title, r.report || '', hint);
    toast(r.partial ? '批量生成部分完成' : '批量生成完成');
    await refreshQualityHistoryList();
    await refreshWorldBatchStatus();
  }, { btnId: 'worldGenerateBtn', loadingText: '批量生成中（较久）…' });
}

async function runWorldRemediate() {
  const s = _worldBatchCache;
  if (!s?.written_count) return toast('本世界尚无正文');
  const label = s.label || '当前世界';
  const from = s.written_from || s.chapter_from;
  const to = s.written_to || s.chapter_to;
  if (
    !confirm(
      `运行「世界闭环」？\n\n` +
        `${label} · 第 ${from}–${to} 章\n\n` +
        `AI 将自动：诊断 → 改稿 → 写回章节 → 同步档案\n` +
        `完成后展示变更报告。耗时与 API 次数较多，请耐心等待。`,
    )
  ) {
    return;
  }
  await runWithLoading(async () => {
    const r = await api(
      '/batch/world/remediate',
      { method: 'POST', body: JSON.stringify({}) },
      FINALIZE_API_TIMEOUT_MS,
    );
    _lastRemediateJobId = r.job_id || null;
    invalidateCache(['plan', 'chapters', 'quality']);
    invalidateQualityCache();
    const title = `世界闭环 · ${label} · 第${from}–${to}章`;
    const hint = r.partial
      ? `部分完成：${r.ok_count}/${r.target_count} 章`
      : `成功 ${r.ok_count}/${r.target_count} 章`;
    showQualityResult(title, r.report || '', hint, {
      reportChars: (r.report || '').length,
      warnings: r.warnings || [],
      customButtons: remediateResultButtons(r.job_id),
    });
    toast(r.partial ? '世界闭环部分完成' : '世界闭环完成');
    await refreshQualityHistoryList();
  }, { btnId: 'worldRemediateBtn', loadingText: '世界闭环中（较久）…' });
}

async function runWorldBatchReview() {
  const s = _worldBatchCache;
  if (!s?.written_count) return toast('本世界尚无正文');
  await runWithLoading(async () => {
    const preview = await api('/batch/world/review/preview');
    const label = preview.label || s.label || '当前世界';
    showQualityResult(
      `发送预览 · 世界审阅 · ${label}`,
      preview.preview || '（无预览）',
      '请核对下方每次 API 将发送的内容与 token 估算，确认后再发送。',
      {
        reportChars: (preview.preview || '').length,
        inputTruncated: preview.input_truncated,
        customButtons: [
          {
            label: '确认发送',
            className: 'btn btn-sm btn-primary',
            onClick: () => executeWorldBatchReview(preview),
          },
          {
            label: '取消',
            className: 'btn btn-sm btn-ghost',
            onClick: () => closeQualityPanel(),
          },
        ],
      },
    );
  }, { btnId: 'worldBatchReviewBtn', loadingText: '生成发送预览…' });
}

async function executeWorldBatchReview(preview) {
  closeQualityPanel();
  const label = preview?.label || '当前世界';
  await runWithLoading(async () => {
    const r = await api('/batch/world/review', {
      method: 'POST',
      body: JSON.stringify({}),
    }, QUALITY_FULL_TIMEOUT_MS);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    const title = `世界审阅 · ${label} · 第${r.written_from}–${r.written_to}章`;
    const hint = r.partial
      ? `部分步骤失败：${(r.errors || []).join('；')}`
      : '只读报告；改稿后重新审阅，满意再「定稿本世界」';
    showQualityResult(title, r.reply, hint, {
      warnings: r.warnings,
      outputTruncated: r.output_truncated,
      inputTruncated: r.input_truncated,
      reportChars: r.report_chars,
    });
    toast(r.partial ? '世界审阅部分完成' : '世界审阅完成');
  }, { btnId: 'worldBatchReviewBtn', loadingText: '世界审阅中（较久）…' });
}

async function runWorldBatchFinalize() {
  const s = _worldBatchCache;
  if (!s?.written_count) return toast('本世界尚无正文');
  const label = s.label || '当前世界';
  const msg =
    `定稿本世界（写档案）\n\n`
    + `${label} · 第${s.written_from}–${s.written_to}章共 ${s.written_count} 章\n\n`
    + `将逐章执行本章定稿（约 ${s.written_count * 2}–${s.written_count * 3} 次 API），`
    + '可能需要十数分钟。';
  if (!confirm(msg)) return;
  await runWithLoading(async () => {
    const r = await api('/batch/world/finalize', {
      method: 'POST',
      body: JSON.stringify({}),
    }, QUALITY_FULL_TIMEOUT_MS);
    invalidateQualityCache();
    await refreshQualityHistoryList();
    await refreshWorldBatchStatus();
    const title = `世界定稿 · ${label}`;
    const hint = r.partial
      ? `部分章节失败：${(r.errors || []).join('；')}`
      : `成功 ${r.ok_count}/${(r.finalized_chapters || []).length} 章`;
    showQualityResult(title, r.reply, hint, {
      warnings: r.errors,
      reportChars: (r.reply || '').length,
    });
    toast(r.partial ? '世界定稿部分完成' : '世界定稿完成');
  }, { btnId: 'worldBatchFinalizeBtn', loadingText: '世界定稿中（较久）…' });
}

function renderQualityGuideHints(status) {
  const container = document.getElementById('qualityGuideBar');
  if (!container) return;
  const todos = status.post_chapter_todos || {};
  const items = [];
  if (todos.summary) {
    items.push(`🔴 第 ${status.latest_chapter_num} 章尚未定稿（缺概述）→ 用下方「本章定稿」`);
  }
  if (todos.char_dynamic_never || todos.char_dynamic) {
    items.push('🟡 char_dynamic 需更新 → 定稿观察或手动编辑');
  }
  if (todos.plot_threads_never || todos.plot_threads) {
    items.push('🟡 plot_threads_active 需更新 → 定稿或手动编辑');
  }
  if (todos.archive) {
    items.push('🟡 summaries_recent 条目过多 → 剪切旧条到 archive');
  }
  container.innerHTML = items.length
    ? `<div class="guide-bar guide-bar--warn"><div class="guide-bar__title">章后维护提醒</div>${items.map((i) => `<div class="guide-bar__item">${i}</div>`).join('')}</div>`
    : `<div class="guide-bar guide-bar--ok">✅ 档案状态良好。快穿建议世界写满后用「审阅/定稿本世界」；单章定稿仅作补救。</div>`;
  setGuideHostVisible('qualityGuideBar', true);
}

async function runPacingCheck() {
  await runWithLoading(async () => {
    const r = await api('/check/pacing', { method: 'POST' });
    invalidateQualityCache();
    await refreshQualityHistoryList();
    showQualityResult('爽点检查', r.reply);
  }, { btnIds: ['runPacingBtn', 'runPacingBtnDock', 'qualityBtnPacing'], loadingText: '检查中…' });
}

let _outlineLatestReply = '';

async function showOutlinePanel(r) {
  closeOtherResultPanels('outline');
  _outlineLatestReply = r.reply || '';
  const panel = document.getElementById('outlineResultPanel');
  if (!panel) return;
  const latest = r.chapter_num || (await getLatestChapterNum());
  const target = latest + 1;
  document.getElementById('outlineResultTitle').textContent = '续章灵感';
  const hint = document.getElementById('outlineResultHint');
  if (hint) {
    const savedAt = r.saved_at ? ` · ${r.saved_at}` : '';
    hint.textContent =
      `已保存${savedAt} · 点按钮将第 1 条建议写入第 ${target} 章 Plan（最新第 ${latest} 章 +1）· ${r.saved_to || 'data/outline_latest.md'}`;
  }
  const body = document.getElementById('outlineResultBody');
  if (body) body.textContent = r.reply || '';
  const btn = document.getElementById('btnApplyOutlineNext');
  if (btn) {
    const n = (r.suggestions || []).length;
    btn.textContent = n ? `写入第 ${target} 章场景 Beat（约 ${Math.min(3, n)} 场）` : '写入下一章场景 Beat';
  }
  panel.classList.remove('hidden');
  syncChatResultOverlay();
}

function closeOutlinePanel() {
  document.getElementById('outlineResultPanel')?.classList.add('hidden');
  syncChatResultOverlay();
}

async function applyOutlineToPlan(offset = 1) {
  const latest = await getLatestChapterNum();
  const target = latest + 1;
  const msg =
    `把第 ${offset} 条续章建议写入第 ${target} 章 Plan？\n\n` +
    `（磁盘最新正文第 ${latest} 章 → 目标第 ${target} 章，与 AI 标题里的章号无关）\n\n` +
    '将自动：① 新建 ch' + String(target).padStart(3, '0') + '.md（若尚无）\n' +
    '② 用建议「定位」生成章节标题（规划里可改）\n' +
    '③ 拆成 2～3 个场景 Beat\n' +
    '（已有 Beat 需确认覆盖）';
  if (!confirm(msg)) return;

  const payload = { offset, replace: false };
  if (_outlineLatestReply) payload.reply = _outlineLatestReply;

  try {
    const r = await api('/outline/apply', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    invalidateCache(['plan', 'chapters']);
    const title = r.chapter_title ? `「${r.chapter_title}」` : '';
    const created = r.chapter_file_created ? '，已创建正文文件' : '';
    toast(`第 ${r.target_chapter || target} 章 ${title}：${r.scene_count} 个场景 Beat${created}`);
    closeOutlinePanel();
    setState({ mode: 'plan', currentChapter: r.target_chapter || target }, 'full');
  } catch (e) {
    const errMsg = e.message || '';
    if (errMsg.includes('已有') || errMsg.includes('覆盖')) {
      if (!confirm(`${errMsg}\n\n确定覆盖第 ${target} 章现有场景 Beat？`)) return;
      const r2 = await api('/outline/apply', {
        method: 'POST',
        body: JSON.stringify({ ...payload, replace: true }),
      });
      invalidateCache(['plan', 'chapters']);
      const t2 = r2.chapter_title ? `「${r2.chapter_title}」` : '';
      toast(`已覆盖第 ${r2.target_chapter || target} 章 ${t2}，${r2.scene_count} 个场景`);
      closeOutlinePanel();
      setState({ mode: 'plan', currentChapter: r2.target_chapter || target }, 'full');
      return;
    }
    toast(errMsg || '写入失败');
  }
}

async function openPlanFromOutline() {
  const latest = await getLatestChapterNum();
  closeOutlinePanel();
  setState({ mode: 'plan', currentChapter: latest + 1 }, 'full');
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
    await showOutlinePanel(r);
    toast('续章灵感已保存，可点「写入下一章场景 Beat」');
    await loadStatus();
  }, { btnId: 'runOutlineBtn', loadingText: '生成中…' });
}

async function loadOutlineLatestIfAny() {
  try {
    const r = await api('/outline/latest');
    if (r.body?.trim()) {
      _outlineLatestReply = r.body;
    }
  } catch {
    /* ignore */
  }
}

async function viewOutlineLatest() {
  const r = await api('/outline/latest');
  if (!r.body?.trim()) return toast('尚无保存的续章灵感，请先点「续章灵感」生成');
  const latest = await getLatestChapterNum();
  await showOutlinePanel({
    reply: r.body,
    chapter_num: latest,
    saved_at: r.saved_at,
    saved_to: 'data/outline_latest.md',
    suggestions: r.suggestions || [],
  });
}

async function undoChapterWrite() {
  if (!confirm('撤销上一次 AI 自动写入章节的正文？\n\n（对话记录保留；可从 data/backups/ 恢复更早版本）')) return;
  const openNum = state.editTarget?.type === 'chapter' ? state.editTarget.num : null;
  await runWithLoading(async () => {
    const r = await api('/chapters/undo-last', { method: 'POST' });
    toast(`已撤销写入（${r.file}）`);
    invalidateCache(['plan', 'chapters']);
    await loadStatus();
    if (!state.writeChapterNum && openNum) {
      setState({ writeChapterNum: openNum }, 'none');
    }
    updateChatHints();
    await loadChat(true);
    if (openNum) await openChapter(openNum, { force: true });
  }, { btnId: 'undoChapterBtn', loadingText: '撤销中…' });
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
  let runtimeLogs = { status: {}, entries: [] };
  try {
    runtimeLogs = await api('/runtime-logs?limit=30');
  } catch (_) { /* optional */ }
  const grid = document.getElementById('reviewGrid');
  clearEl(grid);
  grid.appendChild(makeStatCard('总字数', s.total_chars.toLocaleString(), '全稿字符数（不含空白）'));
  grid.appendChild(makeStatCard('章节 / 场景', `${s.chapter_count} / ${s.scene_count}`, '章节数 · Plan 场景数'));
  grid.appendChild(makeStatCard('Codex / 概述', `${s.codex_count} / ${s.summary_count}`, '设定条目 · 已生成概述章数'));
  grid.appendChild(makeStatCard('API 费用', `$${(s.total_cost ?? st.total_cost).toFixed(4)}`, '累计费用 · 详见 data/cost_log.jsonl'));

  const rs = runtimeLogs.status || st.runtime_log || {};
  const envLabel = rs.runtime_env_label || '运行时';
  const logPath = rs.log_path || 'logs/';
  const logWide = makeStatCard(`${envLabel} · Bug 日志`, '', `${logPath} · 共 ${rs.entry_count ?? 0} 条`, true);
  const logList = document.createElement('div');
  logList.className = 'quality-history__list runtime-log-list';
  const entries = (runtimeLogs.entries || []).filter((e) => e.level === 'error' || e.level === 'warn');
  const showEntries = entries.length ? entries : (runtimeLogs.entries || []).slice(0, 8);
  if (showEntries.length) {
    for (const e of showEntries) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'quality-history__item runtime-log-item';
      btn.dataset.logId = e.id;
      btn.dataset.level = e.level || '';
      btn.innerHTML = `<div class="quality-history__meta">${escapeHtml(e.created_at)} · ${escapeHtml(e.level_label)} · ${escapeHtml(e.category)}</div><div class="quality-history__summary">${escapeHtml(e.summary || e.message)}</div>`;
      btn.onclick = () => openRuntimeLogDetail(e.id);
      logList.appendChild(btn);
    }
  } else {
    const empty = document.createElement('p');
    empty.className = 'quality-history__empty';
    empty.textContent = '暂无错误/警告记录';
    logList.appendChild(empty);
  }
  logWide.querySelector('.num').appendChild(logList);
  grid.appendChild(logWide);

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

async function openRuntimeLogDetail(entryId) {
  if (!entryId) return;
  try {
    const row = await api(`/runtime-logs/${encodeURIComponent(entryId)}`);
    const parts = [
      `${row.created_at || ''} · ${row.level_label || row.level || ''} · ${row.category || ''}`,
      row.location ? `位置：${row.location}` : '',
      row.message || '',
      row.detail ? `\n--- 详情 ---\n${row.detail}` : '',
      row.data && Object.keys(row.data).length
        ? `\n--- 数据 ---\n${JSON.stringify(row.data, null, 2)}`
        : '',
    ].filter(Boolean);
    showQualityResult(
      `Bug 日志 · ${row.runtime_env_label || ''}`,
      parts.join('\n\n'),
      `文件：${(row.runtime_env ? `logs/${row.runtime_env}/runtime.jsonl` : 'logs/')}`,
      { guide: '开发/写作环境日志分开存储；写作端 bug 在 novel_writer_write/logs/write/' },
    );
  } catch (e) {
    toast(String(e.message || e));
  }
}

// ── Overview（书架）──────────────────────────────
let _overviewReadChapter = null;

const BOOK_TYPE_LABELS = { novel: '长篇', world: '快穿世界', short: '短篇' };
const PLATFORM_LABELS = { tomato: '番茄', qimao: '七猫', jjwxc: '晋江', general: '通用' };

let _femaleReviewProfilesCache = null;

async function refreshFemaleReviewProfiles() {
  const sel = document.getElementById('femaleReviewProfile');
  const hint = document.getElementById('femaleReviewProfileHint');
  if (!sel) return;
  try {
    const data = await api('/review/profiles');
    _femaleReviewProfilesCache = data;
    const active = data.active || {};
    const prev = sel.value;
    sel.innerHTML = '<option value="">跟随本书设定</option>';
    for (const p of data.profiles || []) {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      sel.appendChild(opt);
    }
    if (prev && [...sel.options].some(o => o.value === prev)) sel.value = prev;
    if (hint) {
      const bt = BOOK_TYPE_LABELS[active.book_type] || active.book_type || '';
      const pf = PLATFORM_LABELS[active.platform] || active.platform || '';
      const modeHint = active.rewrite_only ? ' · 直改稿（只出全文）' : '';
      hint.textContent = `本书：${bt} · ${pf} → ${active.label || active.profile_id || '默认'}${modeHint}`;
    }
    document.getElementById('femaleReviewProfile')?.dispatchEvent(new Event('change'));
  } catch {
    if (hint) hint.textContent = 'Prompt 见 docs/review-prompts/';
  }
}

async function switchLibraryBook(bookId) {
  if (!bookId) return;
  await runWithLoading(async () => {
    await api('/library/switch', {
      method: 'POST',
      body: JSON.stringify({ book_id: bookId }),
    });
    invalidateCache(['chapters', 'plan', 'codex', 'chat', 'quality', 'freeChat']);
    _overviewReadChapter = null;
    _worldBatchCache = null;
    await loadStatus();
    await renderOverview();
    toast('已切换书籍');
  }, { loadingText: '切换书籍…' });
}

async function createLibraryBook() {
  const title = prompt('书名', '未命名小说');
  if (title === null || !title.trim()) return;
  const typeRaw = prompt('类型：novel（长篇）/ world（快穿）/ short（短篇）', 'novel');
  if (typeRaw === null) return;
  const type = ['novel', 'world', 'short'].includes(typeRaw.trim()) ? typeRaw.trim() : 'novel';
  const platformRaw = prompt('平台：tomato（番茄）/ qimao（七猫）/ jjwxc（晋江）', 'tomato');
  if (platformRaw === null) return;
  const platform = ['tomato', 'qimao', 'jjwxc', 'general'].includes(platformRaw.trim())
    ? platformRaw.trim()
    : 'tomato';
  await runWithLoading(async () => {
    await api('/library/books', {
      method: 'POST',
      body: JSON.stringify({ title: title.trim(), type, platform }),
    });
    invalidateCache(['chapters', 'plan', 'codex', 'chat', 'quality', 'freeChat']);
    _overviewReadChapter = null;
    await loadStatus();
    await renderOverview();
    toast('新书已创建');
  }, { loadingText: '创建书籍…' });
}

function renderLibraryPanel(lib, activeType) {
  const sec = document.createElement('section');
  sec.className = 'overview-section library-panel';
  const head = document.createElement('div');
  head.className = 'overview-section-head';
  head.innerHTML = '<h2>书库</h2>';
  const actions = document.createElement('div');
  actions.className = 'library-actions';
  const newBtn = document.createElement('button');
  newBtn.type = 'button';
  newBtn.className = 'btn btn-sm btn-primary';
  newBtn.textContent = '+ 新建书';
  newBtn.addEventListener('click', () => createLibraryBook());
  actions.appendChild(newBtn);
  head.appendChild(actions);
  sec.appendChild(head);

  const body = document.createElement('div');
  body.className = 'overview-body library-grid';
  const books = lib?.books || [];
  const activeId = lib?.active_book_id || '';
  if (!books.length) {
    body.textContent = '暂无书籍';
  }
  for (const b of books) {
    const card = document.createElement('button');
    card.type = 'button';
    card.className = 'library-card' + (b.id === activeId ? ' library-card--active' : '');
    const typeLabel = BOOK_TYPE_LABELS[b.type] || b.type || '长篇';
    card.innerHTML =
      `<span class="library-card__title">${escapeHtml(b.title || '未命名')}</span>` +
      `<span class="library-card__meta">${escapeHtml(typeLabel)}` +
      `${b.world_label ? ' · ' + escapeHtml(b.world_label) : ''}</span>`;
    if (b.id !== activeId) {
      card.addEventListener('click', () => switchLibraryBook(b.id));
    } else {
      card.disabled = true;
    }
    body.appendChild(card);
  }
  sec.appendChild(body);

  const hint = document.createElement('p');
  hint.className = 'library-type-hint muted';
  const cur = BOOK_TYPE_LABELS[activeType] || activeType || '长篇';
  hint.textContent = `当前书类型：${cur}。短篇自动跳过概述/档案维护。`;
  sec.appendChild(hint);
  return sec;
}

async function renderOverview() {
  const o = await api('/overview');
  const host = document.getElementById('overviewShell');
  clearEl(host);

  if (o.library) {
    host.appendChild(renderLibraryPanel(o.library, o.book_type));
  }

  const hero = document.createElement('div');
  hero.className = 'overview-hero';
  const worldBadge = o.project.world_label
    ? `<span class="overview-badge">${escapeHtml(o.project.world_label)}</span>` : '';
  hero.innerHTML = `
    <div class="overview-hero-top">
      <h1 class="overview-title">${escapeHtml(o.project.title || '未命名小说')}</h1>
      ${worldBadge}
      <button class="btn btn-sm" type="button" id="btnEditProject">改书名</button>
    </div>
    <p class="overview-tagline">${escapeHtml(o.project.tagline || '')}</p>
    <p class="overview-current">当前进度：<strong>第 ${o.current_chapter || '—'} 章</strong>
      ${o.current_chapter_title ? ` · ${escapeHtml(o.current_chapter_title)}` : ''}</p>
  `;
  host.appendChild(hero);
  hero.querySelector('#btnEditProject').addEventListener('click', () => editProjectMeta(o.project));

  host.appendChild(makeOverviewSection('世界观（全书框架）', o.world_excerpt || '（尚未填写 world.md）', () => openGlobal('world')));

  if (o.active_worlds?.length) {
    const worldBody = o.active_worlds.map(w =>
      `【${w.name}】\n${w.preview}`).join('\n\n');
    host.appendChild(makeOverviewSection('当前世界（已勾选 Codex）', worldBody, () => {
      setState({ mode: 'write', sidebar: 'codex' }, 'full');
      openCodexEntry(o.active_worlds[0].id);
    }));
  }

  const outlineEl = makeOverviewSection('大纲（章节 · 场景）', '', null);
  const outlineList = document.createElement('div');
  outlineList.className = 'overview-outline';
  for (const ch of o.outline || []) {
    const block = document.createElement('div');
    block.className = 'overview-chapter-block';
    const h = document.createElement('h3');
    h.textContent = `第 ${ch.num} 章 · ${ch.title}（${(ch.chars || 0).toLocaleString()} 字）`;
    block.appendChild(h);
    const ul = document.createElement('ul');
    for (const s of ch.scenes || []) {
      const li = document.createElement('li');
      li.textContent = `${s.done ? '✓ ' : ''}${s.title}${s.beat ? ' — ' + s.beat : ''}`;
      ul.appendChild(li);
    }
    if (!ch.scenes?.length) {
      const li = document.createElement('li');
      li.textContent = '（暂无场景，去规划模式添加）';
      ul.appendChild(li);
    }
    block.appendChild(ul);
    outlineList.appendChild(block);
  }
  outlineEl.querySelector('.overview-body').appendChild(outlineList);
  host.appendChild(outlineEl);

  const tocSec = makeOverviewSection('章节目录（点章节阅读正文）', '', null);
  const toc = document.createElement('div');
  toc.className = 'overview-toc';
  for (const ch of o.outline || []) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'overview-toc-item';
    btn.dataset.num = String(ch.num);
    btn.classList.toggle('active', _overviewReadChapter === ch.num);
    const status = ch.has_body === false ? ' · 规划中' : `（${(ch.chars || 0).toLocaleString()} 字）`;
    btn.textContent = `第 ${ch.num} 章 · ${ch.title}${status}`;
    if (ch.has_body === false) {
      btn.addEventListener('click', () => {
        setState({ mode: 'plan', currentChapter: ch.num }, 'full');
        toast(`第 ${ch.num} 章尚未开写，已打开规划看板`);
      });
    } else {
      btn.addEventListener('click', () => loadOverviewChapter(ch.num));
    }
    toc.appendChild(btn);
  }
  if (!o.outline?.length) {
    toc.textContent = '还没有章节，请先在规划或写作模式创建第一章';
  }
  tocSec.querySelector('.overview-body').appendChild(toc);
  const reader = document.createElement('pre');
  reader.id = 'overviewReader';
  reader.className = 'overview-reader';
  reader.textContent = _overviewReadChapter ? '加载中…' : '← 点上方章节阅读正文';
  tocSec.querySelector('.overview-body').appendChild(reader);
  if (_overviewReadChapter) loadOverviewChapter(_overviewReadChapter, reader);
  host.appendChild(tocSec);

  host.appendChild(makeOverviewSection('章节概述', o.summaries_excerpt || '（尚未生成概述）', () => openGlobal('summaries_recent')));
}

function makeOverviewSection(title, bodyText, onEdit) {
  const sec = document.createElement('section');
  sec.className = 'overview-section';
  const head = document.createElement('div');
  head.className = 'overview-section-head';
  head.innerHTML = `<h2>${escapeHtml(title)}</h2>`;
  if (onEdit) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-ghost';
    btn.textContent = '去编辑';
    btn.addEventListener('click', onEdit);
    head.appendChild(btn);
  }
  sec.appendChild(head);
  const body = document.createElement('div');
  body.className = 'overview-body';
  if (bodyText) {
    const pre = document.createElement('pre');
    pre.className = 'overview-pre';
    pre.textContent = bodyText;
    body.appendChild(pre);
  }
  sec.appendChild(body);
  return sec;
}

async function loadOverviewChapter(num, readerEl) {
  _overviewReadChapter = num;
  const reader = readerEl || document.getElementById('overviewReader');
  if (reader) reader.textContent = '加载中…';
  const ch = await api(`/chapters/${num}`);
  if (reader) {
    reader.textContent = ch.content?.trim() || '（本章尚无正文）';
  }
  document.querySelectorAll('.overview-toc-item').forEach(el => {
    el.classList.toggle('active', Number(el.dataset.num) === num);
  });
}

async function editProjectMeta(current) {
  const title = prompt('书名', current.title || '');
  if (title === null) return;
  const world_label = prompt('当前世界标签（如 世界一）', current.world_label || '');
  if (world_label === null) return;
  const tagline = prompt('一句话简介', current.tagline || '');
  if (tagline === null) return;
  const typeRaw = prompt(
    '类型：novel（长篇）/ world（快穿）/ short（短篇）',
    current.type || 'novel',
  );
  if (typeRaw === null) return;
  const type = ['novel', 'world', 'short'].includes(typeRaw.trim()) ? typeRaw.trim() : (current.type || 'novel');
  const platformRaw = prompt(
    '目标平台：tomato（番茄）/ qimao（七猫）/ jjwxc（晋江）',
    current.platform || 'tomato',
  );
  if (platformRaw === null) return;
  const platform = ['tomato', 'qimao', 'jjwxc', 'general'].includes(platformRaw.trim())
    ? platformRaw.trim()
    : (current.platform || 'tomato');
  await api('/project', {
    method: 'PUT',
    body: JSON.stringify({
      title: title.trim(),
      world_label: world_label.trim(),
      tagline: tagline.trim(),
      type,
      platform,
    }),
  });
  await loadStatus();
  await renderOverview();
  toast('书目信息已更新');
}

// ── Status / settings ─────────────────────────
async function loadStatus() {
  const s = await api('/status');
  setState({ writeChapterNum: s.write_chapter_num || null }, 'none');
  if (s.active_scene_id && s.active_scene_id !== state.currentSceneId) {
    await restoreActiveSceneFromStatus(s.active_scene_id);
  }
  updateApiKeyBanner(s);
  const titleEl = document.getElementById('brandTitle');
  if (titleEl && s.project_title) titleEl.textContent = s.project_title;
  const typeLabel = BOOK_TYPE_LABELS[s.book_type] || s.book_type || '';
  const sub = [
    typeLabel || null,
    s.world_label || null,
    s.chapter_num ? `第${s.chapter_num}章` : null,
    s.provider_name,
  ].filter(Boolean).join(' · ');
  document.getElementById('projectSub').textContent = sub;
  document.getElementById('ctxTurns').value = s.context_turns;
  const freeChatTurnsEl = document.getElementById('freeChatTurns');
  if (freeChatTurnsEl) freeChatTurnsEl.value = s.free_chat_context_turns ?? 20;
  document.getElementById('ctxMode').value = s.context_mode;
  document.getElementById('providerSel').value = s.provider;
  document.getElementById('providerSelDrawer').value = s.provider;
  setState({ writingProvider: s.provider }, 'none');
  const freeSel = document.getElementById('freeProviderSel');
  if (freeSel) freeSel.value = s.free_chat_provider || 'deepseek';
  document.getElementById('footerStat').textContent =
    `概述 ${s.summary_count} 章 · 设定 ${s.codex_count} 条 · 自由聊 ${s.free_chat_thread_count || 1} 话题 · $${s.total_cost.toFixed(4)}`;
  updateFreeProviderHint(s.free_chat_provider || 'deepseek');

  updateCachePill({
    writing_cache_supported: s.writing_cache_supported,
    last_call: s.last_call,
    provider: s.provider,
  });

  const info = document.getElementById('settingsInfo');
  clearEl(info);
  info.innerHTML =
    `主力：<b>${s.provider_name}</b><br>` +
    `概述 → ${s.summary_provider} · 检查 → ${s.check_provider} · 续章 → ${s.outline_provider}<br>` +
    `写书上下文：${s.context_mode} / ${s.context_turns} 轮 · 自由聊 ${s.free_chat_context_turns ?? 20} 轮<br>` +
    `输出上限：写书 ${s.max_tokens ?? 8192} · 自由聊 ${s.free_chat_max_tokens ?? 64000} tokens（.env 可改）`;

  document.getElementById('contextHint').textContent =
    `${s.context_mode} 模式 · 勾选 Codex 自动注入上下文`;
  updateChatHints();
  return s;
}

async function fillWriteChapterTargetSel() {
  const sel = document.getElementById('writeChapterTargetSel');
  if (!sel) return;
  await ensurePlanData();
  const list = _chaptersWithBody();
  clearEl(sel);
  for (const ch of list) {
    const opt = document.createElement('option');
    opt.value = ch.num;
    opt.textContent = `第 ${ch.num} 章`;
    sel.appendChild(opt);
  }
  const target = getWriteChapterNum() || list[list.length - 1]?.num;
  if (target) sel.value = target;
}

async function saveContext() {
  const turns = parseInt(document.getElementById('ctxTurns').value, 10);
  const freeChatTurns = parseInt(document.getElementById('freeChatTurns').value, 10);
  const mode = document.getElementById('ctxMode').value;
  if (Number.isNaN(turns) || turns < 0 || turns > 100) return toast('写书轮数须为 0–100');
  if (Number.isNaN(freeChatTurns) || freeChatTurns < 0 || freeChatTurns > 100) {
    return toast('自由聊轮数须为 0–100');
  }
  await api('/config/context', {
    method: 'PUT',
    body: JSON.stringify({ turns, free_chat_turns: freeChatTurns, mode }),
  });
  await loadStatus();
  toast(`写书 ${mode}/${turns} 轮 · 自由聊 ${freeChatTurns} 轮`);
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

const _REQUIRED_DOM_IDS = [
  'viewChat', 'viewFree', 'viewWrite', 'chatMessages', 'freeChatMessages',
  'chatInstruction', 'sendChatBtn', 'sendFreeChatBtn', 'chatComposeDock',
  'writeChapterTargetSel', 'writeQualityRow', 'chatResultOverlay',
];

function _checkPageDomHealth() {
  const missing = _REQUIRED_DOM_IDS.filter((id) => !document.getElementById(id));
  // #region agent log
  _dbgApiLog('app.js:init', 'page dom health', {
    missing,
    ok: missing.length === 0,
    mode: state.mode,
  }, 'H3');
  // #endregion
  return missing;
}

// ── Init ───────────────────────────────────────
async function init() {
  resetChatSendingUi();
  _checkPageDomHealth();
  initSidebarCollapsed();
  initChatReadingMode();
  const st = await loadStatus();
  await loadOutlineLatestIfAny();
  if (st.session_on_disk && !(st.history_len > 0)) {
    await restoreChatSession();
    await loadStatus();
  }
  const { chapters } = await api('/chapters');
  setState(
    { chapters, currentChapter: chapters.length ? chapters[chapters.length - 1].num : null },
    'none',
  );
  setMode('write');
  bindFemaleReviewReviseToggle();
  requestAnimationFrame(() => {
    _logMaintainUiState('init');
    // #region agent log
    _dbgApiLog('app.js:init', 'init complete', {
      chapters: chapters.length,
      api_ok: !!st,
      writeTargetSelOptions: document.getElementById('writeChapterTargetSel')?.options?.length ?? 0,
    }, 'H4');
    // #endregion
  });
}

document.getElementById('chatInstruction')?.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
  e.preventDefault();
  if (_isChatSending) {
    toast('请等待当前写书生成完成');
    return;
  }
  sendChat();
});

document.getElementById('mainEditor')?.addEventListener('input', scheduleAutosave);
['beatEditor', 'beatEmotionTarget', 'beatEmotionHow'].forEach((id) => {
  document.getElementById(id)?.addEventListener('input', () => {
    if (state.currentSceneId) updateChatBeatPreview();
  });
});
document.getElementById('beatPaceSel')?.addEventListener('change', () => {
  if (state.currentSceneId) updateChatBeatPreview();
});
document.getElementById('sidebarSearch').addEventListener('input', () => scheduleRender({ sidebar: true }));
document.getElementById('brandTitle')?.addEventListener('click', () => setMode('overview'));
document.getElementById('cachePill')?.addEventListener('click', (e) => {
  e.stopPropagation();
  toggleCachePanel();
});
document.addEventListener('click', (e) => {
  if (!_cachePanelOpen) return;
  const wrap = document.getElementById('cachePillWrap');
  if (wrap && !wrap.contains(e.target)) toggleCachePanel(false);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    toggleCachePanel(false);
    closeContextDrawer();
    closeObserveModal();
    if (!document.getElementById('chatResultOverlay')?.classList.contains('hidden')) {
      closeQualityPanel();
      closeOutlinePanel();
      closeChatCompare();
    }
  }
});

window.addEventListener('beforeunload', (e) => {
  if ((_autosaveTimer && state.editTarget) || (state.editTarget?.type === 'global' && isEditorDirty())) {
    e.preventDefault();
    e.returnValue = '';
  }
});

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden' && _autosaveTimer) flushAutosave();
});

// ── 写作引导 ─────────────────────────────────────
const guideState = {
  status: null,
  lastFetchTime: 0,
  modalDismissed: {},
  postChapterChapterNum: 0,
};

async function fetchGuideStatus(force = false) {
  const now = Date.now();
  if (!force && guideState.status && now - guideState.lastFetchTime < 30000) {
    return guideState.status;
  }
  try {
    const data = await api('/guide/status');
    if (!data?.ok) return null;
    guideState.status = data;
    guideState.lastFetchTime = now;
    return data;
  } catch {
    return null;
  }
}

async function renderGuideHints(page) {
  ['overview-guide-bar', 'plan-guide-panel', 'write-guide-bar', 'chat-guide-bar', 'qualityGuideBar'].forEach((id) => {
    setGuideHostVisible(id, false);
  });
  const status = await fetchGuideStatus();
  if (!status) return;
  switch (page) {
    case 'overview':
      renderOverviewHints(status);
      break;
    case 'plan':
      renderPlanHints(status);
      break;
    case 'write':
      renderWriteHints(status);
      break;
    case 'chat':
      renderChatHints(status);
      break;
    case 'quality':
      renderQualityGuideHints(status);
      break;
    default:
      break;
  }
}

function guideItem(needsAction, label, why) {
  if (!needsAction) {
    return `<div class="guide-bar__item guide-bar__item--ok">✅ ${escapeHtml(label)}</div>`;
  }
  return (
    `<div class="guide-bar__item guide-bar__item--todo">` +
    `<span class="guide-bar__item-dot">○</span>` +
    `<span class="guide-bar__item-label">${escapeHtml(label)}</span>` +
    `<span class="guide-bar__item-why" title="${escapeHtml(why)}">？</span>` +
    `</div>`
  );
}

function setGuideHostVisible(id, visible) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('hidden', !visible);
}

function renderOverviewHints(status) {
  const container = document.getElementById('overview-guide-bar');
  if (!container) return;
  const { stage, files, post_chapter_todos: todos, latest_chapter_num, summaries_recent_count, char_dynamic_last_chapter } = status;
  let html = '';

  if (stage === 'setup') {
    html =
      `<div class="guide-bar guide-bar--warn">` +
      `<div class="guide-bar__title">🚀 第一步：填写基础文件，再开始写</div>` +
      guideItem(!files.world, 'world.md · 世界观', '没有世界观，AI 不知道故事发生在哪个世界') +
      guideItem(!files.char_static, 'char_static.md · 人物锚点', '性格锚点与禁止写法，续写每章都会读') +
      guideItem(!files.style, 'style.md · 文风', '语气、节奏、禁用词') +
      `<div class="guide-bar__footer">填完这三个，再去「规划」页面</div></div>`;
  } else if (stage === 'planning') {
    html =
      `<div class="guide-bar guide-bar--warn">` +
      `<div class="guide-bar__title">📋 第二步：去规划页面，写前 5 章的场景</div>` +
      `<div class="guide-bar__item guide-bar__item--todo">` +
      `<span class="guide-bar__item-dot">○</span>` +
      `<span class="guide-bar__item-label">每章一句话 Beat 就够，不用规划全书</span></div></div>`;
  } else if (stage === 'first_chapter') {
    html = `<div class="guide-bar guide-bar--info"><div class="guide-bar__title">✍️ 第三步：去「写书对话」，开始写第一章</div></div>`;
  } else {
    const items = [];
    if (todos.summary) {
      items.push(`<div class="guide-bar__item guide-bar__item--todo">🔴 第${latest_chapter_num}章还没有概述 — 续写可能忘记本章内容</div>`);
    }
    if (todos.char_dynamic_never) {
      items.push('<div class="guide-bar__item guide-bar__item--todo">🟡 char_dynamic 从未更新 — 人物状态可能漂移</div>');
    } else if (todos.char_dynamic) {
      items.push(`<div class="guide-bar__item guide-bar__item--todo">🟡 人物动态距上次更新已过 ${latest_chapter_num - char_dynamic_last_chapter} 章</div>`);
    }
    if (todos.archive) {
      items.push(`<div class="guide-bar__item guide-bar__item--todo">🟡 近期概述已 ${summaries_recent_count} 条，建议归档到 summaries_archive</div>`);
    }
    html = items.length > 0
      ? `<div class="guide-bar guide-bar--warn"><div class="guide-bar__title">⚠️ 有待完成的维护</div>${items.join('')}</div>`
      : `<div class="guide-bar guide-bar--ok">✅ 当前状态良好，继续写作吧</div>`;
  }

  container.innerHTML = html;
  setGuideHostVisible('overview-guide-bar', true);
}

function renderPlanHints(status) {
  const container = document.getElementById('plan-guide-panel');
  if (!container) return;
  const tips = [];
  if (!status.has_plan) {
    tips.push({ icon: '💡', title: '怎么规划？', body: '先想前 5 章就够。每章一句话：谁做了什么，导致了什么。' });
  } else {
    tips.push({ icon: '📌', title: `已有 ${status.scene_count} 个场景`, body: '每写完一章可回来补后续场景，不必一次规划全书。' });
  }
  if (!status.files.char_static) {
    tips.push({ icon: '⚠️', title: '还没有人物锚点', body: '建议先填 char_static.md，规划时不容易忘记人设。' });
  }
  tips.push({ icon: '❓', title: 'Beat 怎么写？', body: '一句话核心事件。例：「沈织进片场，林珩提前改词，手册第一次失效」' });
  tips.push({ icon: '❓', title: '要规划多少？', body: '前 5 章；写到第 3 章再规划后 5 章。' });

  container.innerHTML = tips.map((t) =>
    `<div class="guide-tip">` +
    `<span class="guide-tip__icon">${t.icon}</span>` +
    `<div><div class="guide-tip__title">${escapeHtml(t.title)}</div>` +
    `<div class="guide-tip__body">${escapeHtml(t.body)}</div></div></div>`,
  ).join('');
  setGuideHostVisible('plan-guide-panel', true);
}

function renderWriteHints(status) {
  const container = document.getElementById('write-guide-bar');
  if (!container) return;
  const latest = status.latest_chapter_num;
  const charLast = status.char_dynamic_last_chapter;
  const plotLast = status.plot_threads_last_chapter;
  const items = [];

  if (status.char_dynamic_never_updated && latest > 0) {
    items.push('⚠️ <b>char_dynamic 从未更新</b> — AI 不知道人物当前状态');
  } else if (latest > 0 && charLast > 0 && latest - charLast >= 2) {
    items.push(`🟡 <b>char_dynamic 上次第 ${charLast} 章</b>，现在第 ${latest} 章 — 建议更新`);
  }
  if (status.plot_threads_never_updated && latest > 0) {
    items.push('⚠️ <b>plot_threads_active 从未更新</b> — 伏笔没有记录');
  } else if (latest > 0 && plotLast > 0 && latest - plotLast >= 2) {
    items.push(`🟡 <b>伏笔上次第 ${plotLast} 章</b> — 这几章有新伏笔吗？`);
  }
  if (!status.latest_chapter_has_summary && latest > 0) {
    items.push(`🔴 <b>第 ${latest} 章还没有概述</b> — 写书对话续写可能忘记本章`);
  }

  container.innerHTML = items.length === 0
    ? `<div class="guide-bar guide-bar--ok">✅ 文件状态正常</div>`
    : `<div class="guide-bar guide-bar--warn">${items.map((i) => `<div class="guide-bar__item">${i}</div>`).join('')}</div>`;
  setGuideHostVisible('write-guide-bar', true);
}

function renderChatHints(status) {
  const container = document.getElementById('chat-guide-bar');
  if (!container) return;
  const latest = status.latest_chapter_num;
  const todos = status.post_chapter_todos;

  if (latest === 0) {
    container.innerHTML = `<div class="guide-bar guide-bar--info">💡 写完第一章后点「本章定稿」，并视需要更新 char_dynamic</div>`;
    setGuideHostVisible('chat-guide-bar', true);
    return;
  }

  const activeKeys = ['summary', 'char_dynamic', 'plot_threads', 'char_dynamic_never', 'plot_threads_never', 'archive'];
  const activeCount = activeKeys.filter((k) => todos[k]).length;
  container.innerHTML = activeCount === 0
    ? `<div class="guide-bar guide-bar--ok">✅ 第 ${latest} 章维护完成，可以继续写</div>`
    : `<div class="guide-bar guide-bar--warn">⚠️ 第 ${latest} 章写完后还有 <b>${activeCount} 项维护</b> 未完成 ` +
      `<button type="button" class="guide-btn" onclick="showPostChapterModal(${latest}, true)">查看清单</button></div>`;
  setGuideHostVisible('chat-guide-bar', true);
}

function postChapterItemActionBtn(item, chapterNum) {
  const cn = chapterNum;
  if (item.key === 'summary') {
    return `<button type="button" class="btn btn-sm guide-modal__item-btn" onclick="dismissPostChapterModal(${cn}, false); runPostChapterFinalize(${cn}, { skipConfirm: true })">本章定稿</button>`;
  }
  if (item.key === 'char_dynamic' || item.key === 'char_dynamic_never') {
    return `<button type="button" class="btn btn-sm guide-modal__item-btn" onclick="openGlobalFromPostChapter('char_dynamic', ${cn})">打开 char_dynamic</button>`;
  }
  if (item.key === 'plot_threads' || item.key === 'plot_threads_never') {
    return `<button type="button" class="btn btn-sm guide-modal__item-btn" onclick="openGlobalFromPostChapter('plot_threads_active', ${cn})">打开伏笔清单</button>`;
  }
  if (item.key === 'archive') {
    return `<button type="button" class="btn btn-sm guide-modal__item-btn" onclick="openGlobalFromPostChapter('summaries_recent', ${cn})">打开近期概述</button>`;
  }
  return '';
}

async function openGlobalFromPostChapter(fileKey, chapterNum) {
  dismissPostChapterModal(chapterNum, false);
  guideState.postChapterChapterNum = chapterNum;
  setState({ mode: 'write', sidebar: 'global' }, 'full');
  await openGlobal(fileKey);
  toast('编辑后请点顶部「保存」并确认，待办才会消失（勾选不算保存）');
}

async function showPostChapterModal(chapterNum, force = false) {
  if (!force && guideState.modalDismissed[chapterNum]) return;
  const status = await fetchGuideStatus(true);
  if (!status) return;
  const todos = status.post_chapter_todos;
  const activeKeys = ['summary', 'char_dynamic', 'plot_threads', 'char_dynamic_never', 'plot_threads_never', 'archive'];
  if (!activeKeys.some((k) => todos[k])) return;

  document.getElementById('postChapterModal')?.remove();

  const allItems = [
    { key: 'summary', label: '本章定稿（含概述）', why: 'AI 靠概述记前文；定稿会写入概述并顺带观察/钉子与质检。', action: '点右侧「本章定稿」或质量页主按钮' },
    { key: 'char_dynamic_never', label: '首次更新 char_dynamic', why: '人物当前心理、关系要记在这里，否则容易人设漂移。', action: '点「打开」→ 填写 → 顶部「保存」并确认' },
    { key: 'char_dynamic', label: '更新 char_dynamic', why: '距上次更新已多章，人物状态可能过时。', action: '点「打开」→ 修改 → 顶部「保存」并确认' },
    { key: 'plot_threads_never', label: '首次更新 plot_threads_active', why: '伏笔清单是防止「坑」被遗忘的唯一手段。', action: '点「打开」→ 填写 → 顶部「保存」并确认' },
    { key: 'plot_threads', label: '更新 plot_threads_active', why: '这几章有新伏笔或已回收的线索吗？', action: '点「打开」→ 修改 → 顶部「保存」并确认' },
    { key: 'archive', label: `归档概述（近期 ${status.summaries_recent_count} 条）`, why: '旧概述剪切到 summaries_archive，只保留最近 3–5 章。', action: '打开近期概述，剪切旧条到 archive' },
  ].filter((item) => todos[item.key]);

  const modalHtml =
    `<div class="modal-backdrop guide-modal-backdrop" id="postChapterModal" onclick="closePostChapterModal(event)">` +
    `<div class="guide-modal" onclick="event.stopPropagation()">` +
    `<div class="guide-modal__header"><span>📋 第 ${chapterNum} 章写完了</span>` +
    `<button type="button" class="guide-modal__close" onclick="dismissPostChapterModal(${chapterNum}, false)">✕</button></div>` +
    `<div class="guide-modal__subtitle">推荐先点底部「本章定稿」。手动项须「打开」→ 编辑 → 顶部<b>「保存」</b>并确认；勾选只是备忘。</div>` +
    `<div class="guide-modal__items">` +
    allItems.map((item, i) =>
      `<div class="guide-modal__item" id="guide-item-${i}">` +
      `<div class="guide-modal__item-header">` +
      `<input type="checkbox" id="guide-check-${i}" onchange="toggleGuideItem(${i})">` +
      `<label for="guide-check-${i}" class="guide-modal__item-label">${escapeHtml(item.label)}</label>` +
      postChapterItemActionBtn(item, chapterNum) +
      `</div>` +
      `<div class="guide-modal__item-why"><span class="guide-modal__why-icon">💬</span>` +
      `<span><b>为什么：</b>${escapeHtml(item.why)}</span></div>` +
      `<div class="guide-modal__item-action">→ ${escapeHtml(item.action)}</div></div>`,
    ).join('') +
    `</div><div class="guide-modal__footer">` +
    `<button type="button" class="guide-modal__btn-skip" onclick="dismissPostChapterModal(${chapterNum}, true)">先跳过</button>` +
    `<button type="button" class="btn btn-primary guide-modal__btn-maintain" id="runPostChapterMaintainModalBtn" onclick="dismissPostChapterModal(${chapterNum}, false); runPostChapterFinalize(${chapterNum}, { skipConfirm: true })">本章定稿（推荐）</button>` +
    `<button type="button" class="guide-modal__btn-done" onclick="dismissPostChapterModal(${chapterNum}, true)">知道了</button>` +
    `</div></div></div>`;

  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function toggleGuideItem(i) {
  const checked = document.getElementById(`guide-check-${i}`)?.checked;
  document.getElementById(`guide-item-${i}`)?.classList.toggle('guide-modal__item--done');
}

function closePostChapterModal(e) {
  if (e.target.id === 'postChapterModal') {
    document.getElementById('postChapterModal')?.remove();
  }
}

function dismissPostChapterModal(chapterNum, rememberDismiss = true) {
  if (rememberDismiss) guideState.modalDismissed[chapterNum] = true;
  document.getElementById('postChapterModal')?.remove();
}

init();
