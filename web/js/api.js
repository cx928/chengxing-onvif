// API 客户端
const TOKEN_KEY = 'cxonvif_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}
export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}
export function clearToken() {
  setToken('');
}

async function request(path, { method = 'GET', body, auth = true, raw = false } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`;
  let response;
  try {
    response = await fetch(`/api/v2${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    throw new Error('无法连接服务，请确认程星 ONVIF 正在运行');
  }
  if (response.status === 401) {
    clearToken();
    window.dispatchEvent(new CustomEvent('cx:unauthorized'));
    throw new Error('登录已失效，请重新登录');
  }
  if (raw) {
    if (!response.ok) throw new Error(`请求失败 (${response.status})`);
    return response;
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`服务返回异常 (${response.status})`);
  }
  if (!response.ok || payload.ok === false) {
    throw new Error(payload?.error || `请求失败 (${response.status})`);
  }
  return payload.data !== undefined ? payload.data : payload;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: 'POST', body }),
  put: (path, body) => request(path, { method: 'PUT', body }),
  del: (path) => request(path, { method: 'DELETE' }),
  raw: (path) => request(path, { raw: true }),
  public: (path) => request(path, { auth: false }),
};

export const auth = {
  state: () => request('/auth/state', { auth: false }),
  login: (username, password) => request('/auth/login', { method: 'POST', body: { username, password }, auth: false }),
  logout: () => request('/auth/logout', { method: 'POST', body: {} }).catch(() => {}),
  session: () => request('/auth/session'),
  changePassword: (currentPassword, newPassword) => request('/auth/password', { method: 'POST', body: { currentPassword, newPassword } }),
};

export function eventStreamUrl() {
  const token = getToken();
  return `/api/v2/system/events/stream?token=${encodeURIComponent(token)}&since=0`;
}

/** 浏览器端 WebRTC 地址（MediaMTX WHEP） */
export function webrtcBase(port) {
  const protocol = location.protocol === 'https:' ? 'https:' : 'http:';
  const host = location.hostname || '127.0.0.1';
  return `${protocol}//${host}:${port}`;
}

export function snapshotUrl(cameraId, token = getToken()) {
  return `/api/v2/cameras/${cameraId}/snapshot?token=${encodeURIComponent(token)}&t=${Date.now()}`;
}
