// 检测事件
import { api } from '../api.js';
import { h, icon, badge, fmtTime, fmtAgo, emptyState, modal } from '../ui.js';
import { GROUP_LABELS } from '../camera-card.js';

export async function render(root, ctx) {
  let events = [];
  try {
    const data = await api.get('/system/events?since=0');
    events = (data.events || []).filter((e) => e.type === 'detection').reverse();
  } catch { /* ignore */ }

  let cameraFilter = 'all';
  let groupFilter = 'all';
  let stateFilter = 'all';

  const tbody = h('tbody');
  const summary = h('span', { class: 'desc' });

  const cameraSelect = h('select', { onchange: (event) => { cameraFilter = event.target.value; draw(); } },
    h('option', { value: 'all', text: '全部摄像机' }),
    ...ctx.state.cameras.map((cam) => h('option', { value: String(cam.id), text: cam.name })),
  );
  const groupSelect = h('select', { onchange: (event) => { groupFilter = event.target.value; draw(); } },
    h('option', { value: 'all', text: '全部目标' }),
    ...Object.entries(GROUP_LABELS).map(([key, label]) => h('option', { value: key, text: label })),
  );
  const stateSelect = h('select', { onchange: (event) => { stateFilter = event.target.value; draw(); } },
    h('option', { value: 'all', text: '全部状态' }),
    h('option', { value: 'active', text: '触发' }),
    h('option', { value: 'inactive', text: '结束' }),
  );

  const table = h('div', { class: 'table-wrap' },
    h('table', { class: 'tbl' },
      h('thead', {}, h('tr', {},
        h('th', { text: '时间' }), h('th', { text: '摄像机' }), h('th', { text: '目标' }),
        h('th', { text: '状态' }), h('th', { text: '来源' }), h('th', { text: '设备画像' }), h('th', {}),
      )),
      tbody,
    ),
  );

  function draw() {
    tbody.innerHTML = '';
    const filtered = events.filter((event) => {
      if (cameraFilter !== 'all' && String(event.cameraId) !== cameraFilter) return false;
      if (groupFilter !== 'all' && !(event.groups || []).includes(groupFilter)) return false;
      if (stateFilter === 'active' && !event.active) return false;
      if (stateFilter === 'inactive' && event.active) return false;
      return true;
    });
    summary.textContent = `${filtered.length} 条事件${events.length > filtered.length ? `（共 ${events.length}）` : ''}`;
    if (!filtered.length) {
      tbody.append(h('tr', {}, h('td', { colspan: '7' }, emptyState('暂无检测事件。可在摄像机卡片点击「测试」生成一次事件。', 'bell'))));
      return;
    }
    filtered.slice(0, 200).forEach((event) => {
      const groups = (event.groups || []).map((g) => GROUP_LABELS[g] || g).join(' / ');
      const row = h('tr', { style: { cursor: 'pointer' } },
        h('td', { class: 'nowrap' }, h('div', { text: fmtTime(event.timestamp) }), h('div', { class: 'small muted', text: fmtAgo(event.timestamp) })),
        h('td', { text: event.cameraName || `摄像机 ${event.cameraId}` }),
        h('td', {}, badge(groups || '—', event.active ? 'green' : '')),
        h('td', {}, event.active ? badge('触发', 'green') : badge('结束', '')),
        h('td', {}, badge(event.source === 'test' ? '测试' : 'AI', event.source === 'test' ? 'amber' : 'blue')),
        h('td', { class: 'small muted', text: event.manufacturer || '—' }),
        h('td', { class: 'actions' }, h('button', { class: 'btn sm ghost', text: '详情' })),
      );
      row.addEventListener('click', () => showDetail(event));
      tbody.append(row);
    });
  }

  function showDetail(event) {
    const body = h('div', { class: 'col', style: { gap: '12px' } },
      h('div', { class: 'kv' },
        h('dt', { text: '时间' }), h('dd', { text: fmtTime(event.timestamp) }),
        h('dt', { text: '摄像机' }), h('dd', { text: `${event.cameraName || ''} (#${event.cameraId})` }),
        h('dt', { text: '目标' }), h('dd', { text: (event.groups || []).map((g) => GROUP_LABELS[g] || g).join('、') }),
        h('dt', { text: '状态' }), h('dd', { text: event.active ? '触发（active）' : '结束（inactive）' }),
        h('dt', { text: '置信度' }), h('dd', { text: JSON.stringify(event.confidence || {}) }),
        h('dt', { text: 'ONVIF 主题数' }), h('dd', { text: String(event.queuedOnvif ?? '—') }),
        h('dt', { text: '设备画像' }), h('dd', { text: `${event.manufacturer || ''} ${event.profile || ''}` }),
      ),
      h('div', {},
        h('div', { class: 'small muted', text: '检测框（归一化坐标 x1,y1,x2,y2）' }),
        h('pre', { class: 'logbox', style: { height: '180px' }, text: (event.detections || []).map((d) => `${d.label} ${(d.confidence * 100).toFixed(0)}%  [${d.box.map((v) => v.toFixed(3)).join(', ')}]`).join('\n') || '无检测框' }),
      ),
    );
    modal({ title: '事件详情', body, footer: [h('button', { class: 'btn', text: '关闭', onclick: () => document.querySelector('.modal-mask')?.click() })] });
  }

  root.append(
    h('div', { class: 'toolbar' },
      cameraSelect, groupSelect, stateSelect,
      h('div', { class: 'spacer' }),
      summary,
      h('button', { class: 'btn sm ghost', html: `${icon('refresh')} 清空`, onclick: () => { events = []; draw(); } }),
    ),
    table,
  );
  draw();

  const onEvent = (event) => {
    const payload = event.detail;
    if (payload.type !== 'detection') return;
    events.unshift(payload);
    if (events.length > 500) events.pop();
    draw();
  };
  window.addEventListener('cx:event', onEvent);
  return () => window.removeEventListener('cx:event', onEvent);
}
