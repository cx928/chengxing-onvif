// 应用入口：登录、布局、路由、实时事件
import { api, auth, clearToken, getToken, setToken, eventStreamUrl } from './api.js';
import { $, $$, h, icon, setIcons, toast, fmtDuration } from './ui.js';
import { openPasswordDialog } from './account.js';

import * as overview from './pages/overview.js';
import * as cameras from './pages/cameras.js';
import * as events from './pages/events.js';
import * as models from './pages/models.js';
import * as hardware from './pages/hardware.js';
import * as settings from './pages/settings.js';
import * as about from './pages/about.js';

const PAGES = { overview, cameras, events, models, hardware, settings, about };
const TITLES = {
  overview: ['概览', '实时掌握摄像机、检测与算力状态'],
  cameras: ['摄像机', '添加、配置与调试每一路虚拟摄像机'],
  events: ['检测事件', 'ONVIF 事件与水星安防推送记录'],
  models: ['模型库', 'YOLO / RT-DETR / ONNX / OpenVINO 多模型管理'],
  hardware: ['硬件加速', 'Intel / AMD / NVIDIA GPU 与编码器能力'],
  settings: ['系统设置', '服务、安全、开机自启与维护'],
  about: ['关于', '程星 ONVIF 产品信息与联系方式'],
};

export const state = {
  info: null,
  status: null,
  cameras: [],
  profiles: [],
  hardware: null,
  models: null,
  events: [],
  health: null,
  webrtcPort: 8889,
  route: 'overview',
  params: {},
  mustChangePassword: false,
  username: 'admin',
};

let currentCleanup = null;
let currentRoute = '';
let eventSource = null;
let healthTimer = null;
let refreshTimer = null;
let entering = false;

window.__cxStage = 'module-loaded';

// ---------------------------------------------------------------- 启动
async function boot() {
  window.__cxStage = 'boot';
  setIcons();
  bindStatic();
  try {
    const authState = await auth.state();
    window.__cxStage = 'auth-state';
    state.username = authState.username || 'admin';
    state.mustChangePassword = Boolean(authState.mustChangePassword);
    if (!authState.requireLogin) {
      await enterApp();
      return;
    }
    if (getToken()) {
      try {
        await auth.session();
        await enterApp();
        return;
      } catch {
        clearToken();
      }
    }
    showLogin();
  } catch (error) {
    showLogin(error.message);
  }
}

function showLogin(message = '') {
  hideBoot();
  $('#app').classList.add('hidden');
  $('#login').classList.remove('hidden');
  const errorBox = $('#login-error');
  if (message) {
    errorBox.textContent = message;
    errorBox.classList.remove('hidden');
  } else {
    errorBox.classList.add('hidden');
  }
  setTimeout(() => $('#login-pass').focus(), 120);
}

function hideBoot() {
  const boot = $('#boot');
  if (boot) {
    boot.classList.add('fade');
    setTimeout(() => boot.remove(), 400);
  }
}

async function enterApp() {
  if (entering) return;
  entering = true;
  window.__cxStage = 'enter';
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  hideBoot();
  try {
    await refreshCore();
  } catch (error) {
    toast(error.message, 'err');
  }
  const initial = (location.hash.replace(/^#\/?/, '') || 'overview').split('?')[0] || 'overview';
  await navigate(initial, true);
  startRealtime();
  startHealthPolling();
  entering = false;
}

function startHealthPolling() {
  clearInterval(healthTimer);
  const tick = async () => {
    try {
      const health = await api.public('/health');
      state.health = health;
      updateHealthPill(true, health);
      $('#side-stat').textContent = `${health.running}/${health.cameras} 路运行 · v${health.version}`;
    } catch {
      state.health = null;
      updateHealthPill(false);
      $('#side-stat').textContent = '服务连接中断';
    }
  };
  tick();
  healthTimer = setInterval(tick, 5000);
}

function updateHealthPill(online, health) {
  const pill = $('#health-pill');
  pill.className = `pill ${online ? 'online' : 'offline'}`;
  pill.innerHTML = `<i></i><span>${online ? `运行中 · ${health?.running ?? 0} 路` : '未连接'}</span>`;
}

// ---------------------------------------------------------------- 数据
export async function refreshCore() {
  const [info, status, camerasData, profiles] = await Promise.all([
    api.get('/system/info'),
    api.get('/system/status'),
    api.get('/cameras'),
    api.get('/onvif/profiles').catch(() => []),
  ]);
  state.info = info;
  state.status = status;
  state.cameras = camerasData.cameras || [];
  state.profiles = profiles || [];
  state.hardware = info.hardware || null;
  state.webrtcPort = info.ports?.webrtc || 8889;
  state.username = info.auth?.username || state.username;
  $('#side-version').textContent = `v${info.version}`;
  $('#user-name').textContent = state.username;
  $('.avatar').textContent = (state.username || 'A').slice(0, 1).toUpperCase();
  return state;
}

export async function refreshStatusOnly() {
  const status = await api.get('/system/status');
  state.status = status;
  state.cameras = status.cameras || [];
  return state;
}

// ---------------------------------------------------------------- 实时事件
function startRealtime() {
  stopRealtime();
  if (!getToken()) return;
  eventSource = new EventSource(eventStreamUrl());
  eventSource.onmessage = (event) => {
    let payload;
    try { payload = JSON.parse(event.data); } catch { return; }
    if (payload.type === 'detection') {
      state.events.unshift(payload);
      if (state.events.length > 300) state.events.pop();
    }
    window.dispatchEvent(new CustomEvent('cx:event', { detail: payload }));
    if (payload.type === 'camera_state') scheduleCameraRefresh();
  };
  eventSource.onerror = () => {
    // EventSource 会自动重连；此处仅避免控制台噪音
  };
}

function stopRealtime() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

let cameraRefreshTimer = null;
function scheduleCameraRefresh() {
  clearTimeout(cameraRefreshTimer);
  cameraRefreshTimer = setTimeout(async () => {
    try {
      await refreshStatusOnly();
      window.dispatchEvent(new CustomEvent('cx:cameras'));
    } catch { /* ignore */ }
  }, 600);
}

// ---------------------------------------------------------------- 路由
export async function navigate(route, replace = false) {
  if (!PAGES[route]) route = 'overview';
  if (currentCleanup) {
    try { currentCleanup(); } catch { /* ignore */ }
    currentCleanup = null;
  }
  document.querySelectorAll('.video-preview').forEach((el) => { el.innerHTML = ''; });
  // 切换页面时关闭抽屉与弹窗，避免残留遮罩
  const drawerRoot = document.getElementById('drawer-root');
  const modalRoot = document.getElementById('modal-root');
  if (drawerRoot) drawerRoot.innerHTML = '';
  if (modalRoot) modalRoot.innerHTML = '';
  state.route = route;
  currentRoute = route;
  if (!replace && location.hash !== `#/${route}`) {
    location.hash = `#/${route}`;
  }
  $$('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.route === route));
  const [title, sub] = TITLES[route] || ['程星 ONVIF', ''];
  $('#page-title').textContent = title;
  $('#page-sub').textContent = sub;
  $('#view').innerHTML = '';
  const ctx = {
    state,
    navigate,
    refresh: async () => {
      await refreshCore();
      window.dispatchEvent(new CustomEvent('cx:cameras'));
    },
  };
  try {
    const cleanup = await PAGES[route].render($('#view'), ctx);
    currentCleanup = typeof cleanup === 'function' ? cleanup : null;
  } catch (error) {
    $('#view').append(h('div', { class: 'note warn', text: `页面加载失败：${error.message}` }));
  }
  $('#view').scrollTop = 0;
}

// ---------------------------------------------------------------- 静态交互
function bindStatic() {
  $('#login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = event.target.querySelector('button[type=submit]');
    const errorBox = $('#login-error');
    errorBox.classList.add('hidden');
    button.disabled = true;
    button.textContent = '登录中…';
    try {
      const result = await auth.login($('#login-user').value.trim() || 'admin', $('#login-pass').value);
      setToken(result.token);
      state.mustChangePassword = Boolean(result.mustChangePassword);
      await enterApp();
      if (result.mustChangePassword) {
        const changed = await openPasswordDialog({ force: true });
        if (changed) state.mustChangePassword = false;
      }
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove('hidden');
    } finally {
      button.disabled = false;
      button.textContent = '登 录';
    }
  });

  $('#nav').addEventListener('click', (event) => {
    const item = event.target.closest('.nav-item');
    if (item?.dataset.route) {
      event.preventDefault();
      navigate(item.dataset.route);
    }
  });

  window.addEventListener('hashchange', () => {
    const route = location.hash.replace(/^#\/?/, '').split('?')[0] || 'overview';
    if (route !== currentRoute) navigate(route, true);
  });

  $('#btn-refresh').addEventListener('click', async () => {
    try {
      await refreshCore();
      await navigate(state.route, true);
      toast('已刷新');
    } catch (error) {
      toast(error.message, 'err');
    }
  });

  $('#btn-user').addEventListener('click', (event) => {
    event.stopPropagation();
    $('#user-pop').classList.toggle('hidden');
  });
  document.addEventListener('click', (event) => {
    if (!event.target.closest('.user-menu')) $('#user-pop').classList.add('hidden');
  });
  $('#user-pop').addEventListener('click', async (event) => {
    const target = event.target.closest('.pop-item');
    if (!target) return;
    $('#user-pop').classList.add('hidden');
    if (target.id === 'btn-logout') {
      await auth.logout();
      clearToken();
      stopRealtime();
      clearInterval(healthTimer);
      state.events = [];
      showLogin();
      return;
    }
    if (target.dataset.go) {
      await navigate(target.dataset.go);
      if (target.dataset.tab) {
        window.dispatchEvent(new CustomEvent('cx:settings-tab', { detail: target.dataset.tab }));
      }
    }
  });

  window.addEventListener('cx:unauthorized', () => {
    stopRealtime();
    clearInterval(healthTimer);
    showLogin('登录已失效，请重新登录');
  });

  // 全局工具：复制按钮
  document.addEventListener('click', async (event) => {
    const copy = event.target.closest('[data-copy]');
    if (copy) {
      const { copyText } = await import('./ui.js');
      copyText(copy.dataset.copy);
    }
  });
}

// 供页面使用
export { openPasswordDialog };

boot();
