// 区域编辑器：在快照上绘制多边形（包含 / 排除）
import { h, modal, toast, copyText } from './ui.js';
import { getToken } from './api.js';

const POINT_RADIUS = 4;

export function openZoneEditor({ cameraId, zones = [], running = false, onChange }) {
  const localZones = JSON.parse(JSON.stringify(zones));
  let current = null; // {type, points: []}
  let selected = null;

  const canvas = h('canvas', { width: 720, height: 405 });
  const ctx2d = canvas.getContext('2d');
  const list = h('div', { class: 'zone-list' });
  const typeSeg = h('div', { class: 'seg' });
  let drawType = 'include';
  ['include', 'exclude'].forEach((type) => {
    const button = h('button', { class: type === drawType ? 'active' : '' }, type === 'include' ? '包含区域' : '排除区域');
    button.addEventListener('click', () => {
      drawType = type;
      typeSeg.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === button));
    });
    typeSeg.append(button);
  });

  let background = null;
  if (cameraId && running) {
    const image = new Image();
    image.onload = () => { background = image; draw(); };
    image.src = `/api/v2/cameras/${cameraId}/snapshot?token=${encodeURIComponent(getToken())}&t=${Date.now()}`;
  }

  function draw() {
    ctx2d.clearRect(0, 0, canvas.width, canvas.height);
    if (background) {
      ctx2d.drawImage(background, 0, 0, canvas.width, canvas.height);
    } else {
      const gradient = ctx2d.createLinearGradient(0, 0, canvas.width, canvas.height);
      gradient.addColorStop(0, '#0a1220');
      gradient.addColorStop(1, '#101c2f');
      ctx2d.fillStyle = gradient;
      ctx2d.fillRect(0, 0, canvas.width, canvas.height);
      ctx2d.strokeStyle = '#18263a';
      ctx2d.lineWidth = 1;
      for (let x = 0; x < canvas.width; x += 45) {
        ctx2d.beginPath(); ctx2d.moveTo(x, 0); ctx2d.lineTo(x, canvas.height); ctx2d.stroke();
      }
      for (let y = 0; y < canvas.height; y += 45) {
        ctx2d.beginPath(); ctx2d.moveTo(0, y); ctx2d.lineTo(canvas.width, y); ctx2d.stroke();
      }
      ctx2d.fillStyle = '#4b5b72';
      ctx2d.font = '13px "Segoe UI", sans-serif';
      ctx2d.fillText('摄像机未运行，仅可规划区域', 16, 28);
    }

    localZones.forEach((zone) => {
      const points = (zone.points || []).map(([x, y]) => [x * canvas.width, y * canvas.height]);
      if (points.length < 2) return;
      const isInclude = zone.type !== 'exclude';
      ctx2d.beginPath();
      ctx2d.moveTo(points[0][0], points[0][1]);
      points.slice(1).forEach(([x, y]) => ctx2d.lineTo(x, y));
      if (points.length >= 3) ctx2d.closePath();
      ctx2d.fillStyle = isInclude ? 'rgba(34,197,94,.16)' : 'rgba(239,68,68,.16)';
      ctx2d.strokeStyle = isInclude ? '#22c55e' : '#ef4444';
      ctx2d.lineWidth = zone === selected ? 2.5 : 1.6;
      if (points.length >= 3) ctx2d.fill();
      ctx2d.stroke();
      points.forEach(([x, y]) => {
        ctx2d.beginPath();
        ctx2d.arc(x, y, POINT_RADIUS, 0, Math.PI * 2);
        ctx2d.fillStyle = ctx2d.strokeStyle;
        ctx2d.fill();
      });
    });

    if (current) {
      const points = current.points;
      if (points.length) {
        ctx2d.beginPath();
        ctx2d.moveTo(points[0][0], points[0][1]);
        points.slice(1).forEach(([x, y]) => ctx2d.lineTo(x, y));
        ctx2d.strokeStyle = current.type === 'include' ? '#86efac' : '#fca5a5';
        ctx2d.setLineDash([5, 4]);
        ctx2d.lineWidth = 2;
        ctx2d.stroke();
        ctx2d.setLineDash([]);
        points.forEach(([x, y]) => {
          ctx2d.beginPath();
          ctx2d.arc(x, y, POINT_RADIUS, 0, Math.PI * 2);
          ctx2d.fillStyle = ctx2d.strokeStyle;
          ctx2d.fill();
        });
      }
    }
    renderList();
  }

  function renderList() {
    list.innerHTML = '';
    if (!localZones.length && !current) {
      list.append(h('div', { class: 'form-hint', text: '还没有区域。点击画布添加顶点，至少 3 个点后点击“闭合区域”。' }));
      return;
    }
    localZones.forEach((zone, index) => {
      const row = h('div', { class: 'zone-row' },
        h('span', { class: `badge ${zone.type === 'exclude' ? 'red' : 'green'}`, text: zone.type === 'exclude' ? '排除' : '包含' }),
        h('input', {
          class: 'grow', type: 'text', value: zone.name || `区域 ${index + 1}`,
          style: 'height:26px;font-size:12px',
          oninput: (event) => { zone.name = event.target.value; },
        }),
        h('button', {
          class: 'icon-btn', title: '删除', html: '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>',
          onclick: () => {
            localZones.splice(index, 1);
            selected = null;
            draw();
          },
        }),
      );
      row.addEventListener('click', (event) => {
        if (event.target.tagName === 'INPUT') return;
        selected = zone;
        draw();
      });
      list.append(row);
    });
    if (current) {
      list.append(h('div', { class: 'zone-row' },
        h('span', { class: `badge ${current.type === 'exclude' ? 'red' : 'green'}`, text: '绘制中' }),
        h('span', { class: 'grow', text: `${current.points.length} 个顶点` }),
        h('button', {
          class: 'btn sm', text: '撤销点',
          onclick: () => { current.points.pop(); draw(); },
        }),
        h('button', { class: 'btn sm primary', text: '闭合区域', onclick: finishCurrent }),
      ));
    }
  }

  function canvasPoint(event) {
    const rect = canvas.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((event.clientY - rect.top) / rect.height) * canvas.height;
    return [Math.max(0, Math.min(canvas.width, x)), Math.max(0, Math.min(canvas.height, y))];
  }

  function finishCurrent() {
    if (!current) return;
    if (current.points.length < 3) {
      toast('至少需要 3 个顶点', 'err');
      return;
    }
    localZones.push({
      id: `z${Date.now()}`,
      name: `区域 ${localZones.length + 1}`,
      type: current.type,
      points: current.points.map(([x, y]) => [Number((x / canvas.width).toFixed(4)), Number((y / canvas.height).toFixed(4))]),
      enabled: true,
      targets: [],
    });
    current = null;
    draw();
  }

  canvas.addEventListener('click', (event) => {
    if (!current) current = { type: drawType, points: [] };
    current.points.push(canvasPoint(event));
    draw();
  });
  canvas.addEventListener('dblclick', (event) => {
    event.preventDefault();
    finishCurrent();
  });

  const body = h('div', { class: 'col', style: { gap: '12px' } },
    h('div', { class: 'row wrap' }, typeSeg,
      h('button', { class: 'btn sm ghost', onclick: () => { current = null; draw(); } }, '取消当前绘制'),
      h('div', { class: 'spacer' }),
      h('span', { class: 'form-hint', text: '单击添加顶点 · 双击闭合' }),
    ),
    h('div', { class: 'canvas-wrap' }, canvas),
    list,
  );

  const dialog = modal({
    title: '检测区域',
    body,
    wide: true,
    footer: [
      h('button', { class: 'btn ghost', onclick: () => dialog.close() }, '取消'),
      h('button', {
        class: 'btn primary',
        onclick: () => {
          onChange?.(localZones);
          dialog.close();
        },
      }, '保存区域'),
    ],
  });
  draw();
}

