// 通用 UI 工具：元素构建、图标、提示、弹窗、抽屉
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  camera: '<path d="M4 8.5A2.5 2.5 0 0 1 6.5 6h7A2.5 2.5 0 0 1 16 8.5v7A2.5 2.5 0 0 1 13.5 18h-7A2.5 2.5 0 0 1 4 15.5z"/><path d="M16 11l4-2.5v7L16 13"/>',
  bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
  layers: '<path d="M12 2 2 7l10 5 10-5-10-5z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/>',
  cpu: '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="m8 5 11 7-11 7z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6M10 11v6M14 11v6"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  check: '<path d="m4 12 5 5L20 6"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  power: '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/>',
  external: '<path d="M15 3h6v6M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  upload: '<path d="M12 21V9M7 14l5-5 5 5M4 3h16"/>',
  chevron: '<path d="m9 18 6-6-6-6"/>',
  wifi: '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 20h.01"/>',
  chip: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 9h6v6H9z"/>',
  box: '<path d="M21 8v8a2 2 0 0 1-1 1.7l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.7l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  lock: '<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  link: '<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7L12.5 20"/>',
  map: '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3z"/><path d="M9 3v15M15 6v15"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
};

export function icon(name, cls = '') {
  const path = ICONS[name] || ICONS.info;
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

export function setIcons(root = document) {
  $$('[data-icon]', root).forEach((el) => {
    if (!el.dataset.done) {
      el.innerHTML = icon(el.dataset.icon);
      el.dataset.done = '1';
    }
  });
}

/** 轻量元素构建器 */
export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key === 'html') el.innerHTML = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'value') el.value = value;
    else if (key === 'checked' || key === 'disabled' || key === 'selected') el[key] = Boolean(value);
    else el.setAttribute(key, value);
  }
  for (const child of children.flat(3)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function fmtTime(value, withDate = true) {
  if (!value) return '—';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const pad = (n) => String(n).padStart(2, '0');
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  return withDate ? `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${time}` : time;
}

export function fmtAgo(value) {
  if (!value) return '—';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 5) return '刚刚';
  if (seconds < 60) return `${seconds} 秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

export function fmtDuration(seconds) {
  seconds = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d} 天 ${h} 小时`;
  if (h) return `${h} 小时 ${m} 分`;
  if (m) return `${m} 分 ${seconds % 60} 秒`;
  return `${seconds} 秒`;
}

export function fmtBytes(size) {
  const value = Number(size) || 0;
  if (value > 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  if (value > 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${value} B`;
}

export function toast(message, type = 'ok', timeout = 3600) {
  const box = h('div', { class: `toast ${type}` },
    h('span', { class: 't-ico', html: icon(type === 'err' ? 'x' : 'check') }),
    h('div', { class: 't-msg', text: message }),
  );
  $('#toasts').append(box);
  setTimeout(() => {
    box.style.opacity = '0';
    box.style.transform = 'translateY(6px)';
    box.style.transition = 'all .2s';
    setTimeout(() => box.remove(), 220);
  }, timeout);
  return box;
}

export function confirmDialog({ title = '确认操作', message, confirmText = '确认', danger = false } = {}) {
  return new Promise((resolve) => {
    const mask = h('div', { class: 'modal-mask' });
    const close = (value) => { mask.remove(); card.remove(); resolve(value); };
    const card = h('div', { class: 'modal' },
      h('div', { class: 'modal-head' }, h('h3', { text: title })),
      h('div', { class: 'modal-body' }, h('div', { class: 'form-hint', text: message })),
      h('div', { class: 'modal-foot' },
        h('button', { class: 'btn ghost', onclick: () => close(false) }, '取消'),
        h('button', { class: `btn ${danger ? 'danger' : 'primary'}`, onclick: () => close(true) }, confirmText),
      ),
    );
    $('#modal-root').append(mask, card);
    mask.addEventListener('click', () => close(false));
  });
}

export function modal({ title, body, footer, wide = false, onClose } = {}) {
  const mask = h('div', { class: 'modal-mask' });
  const card = h('div', { class: `modal${wide ? ' wide' : ''}` });
  const close = () => {
    mask.remove();
    card.remove();
    onClose?.();
  };
  const head = h('div', { class: 'modal-head' }, h('h3', { text: title }), h('div', { class: 'spacer' }),
    h('button', { class: 'icon-btn', html: icon('x'), onclick: close }));
  const bodyEl = h('div', { class: 'modal-body' });
  if (body instanceof Node) bodyEl.append(body); else if (body) bodyEl.innerHTML = body;
  card.append(head, bodyEl);
  if (footer) {
    const foot = h('div', { class: 'modal-foot' });
    footer.forEach((el) => foot.append(el));
    card.append(foot);
  }
  mask.addEventListener('click', close);
  $('#modal-root').append(mask, card);
  return { card, body: bodyEl, close };
}

export function drawer({ title, subtitle, body, footer, onClose } = {}) {
  const mask = h('div', { class: 'drawer-mask' });
  const panel = h('div', { class: 'drawer' });
  const close = () => {
    mask.remove();
    panel.remove();
    onClose?.();
  };
  panel.append(
    h('div', { class: 'drawer-head' },
      h('div', {},
        h('h3', { text: title }),
        subtitle ? h('div', { class: 'sub muted small', text: subtitle }) : null,
      ),
      h('div', { class: 'spacer' }),
      h('button', { class: 'icon-btn', html: icon('x'), onclick: close }),
    ),
  );
  const bodyEl = h('div', { class: 'drawer-body' });
  if (body instanceof Node) bodyEl.append(body); else if (body) bodyEl.innerHTML = body;
  panel.append(bodyEl);
  if (footer) {
    const foot = h('div', { class: 'drawer-foot' });
    footer.forEach((el) => foot.append(el));
    panel.append(foot);
  }
  mask.addEventListener('click', close);
  $('#drawer-root').append(mask, panel);
  return { panel, body: bodyEl, close };
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('已复制到剪贴板');
    return true;
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.append(area);
    area.select();
    try { document.execCommand('copy'); toast('已复制到剪贴板'); } catch { toast('复制失败', 'err'); }
    area.remove();
    return false;
  }
}

export function debounce(fn, delay = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

export function switchEl(checked, onChange, label = '') {
  const input = h('input', { type: 'checkbox', checked });
  const wrap = h('label', { class: 'switch' }, input, h('span', { class: 'track' }));
  if (label) wrap.append(h('span', { text: label }));
  input.addEventListener('change', () => onChange?.(input.checked));
  wrap.input = input;
  return wrap;
}

export function field(label, control, hint = '') {
  return h('label', { class: 'field' },
    h('span', { text: label }),
    control,
    hint ? h('div', { class: 'form-hint', text: hint }) : null,
  );
}

export function badge(text, tone = '') {
  return h('span', { class: `badge ${tone}`, text });
}

export function emptyState(text, iconName = 'box') {
  return h('div', { class: 'empty', html: `${icon(iconName)}<div>${escapeHtml(text)}</div>` });
}

export function statusDot(status) {
  return h('span', { class: `cam-status ${status || ''}`, title: status });
}
