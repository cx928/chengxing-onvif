// 概览
import { api } from '../api.js';
import { h, icon, badge, fmtDuration, fmtAgo, emptyState } from '../ui.js';
import { cameraCard, GROUP_LABELS } from '../camera-card.js';
import { openCameraEditor } from '../editor.js';

export async function render(root, ctx) {
  const cleanups = [];
  const { info, cameras } = ctx.state;
  const running = cameras.filter((c) => c.status === 'running').length;
  const hardware = info?.hardware || {};
  const encoders = (hardware.encoders || []).filter((e) => e.available);

  let historyEvents = [];
  try {
    const data = await api.get('/system/events?since=0');
    historyEvents = (data.events || []).filter((e) => e.type === 'detection');
  } catch { /* ignore */ }
  const eventCount = Math.max(ctx.state.events.filter((e) => e.type === 'detection' && e.active).length, historyEvents.filter((e) => e.active).length);

  const stats = h('div', { class: 'stats' },
    stat('摄像机在线', `${running}`, `/ ${cameras.length}`, 'camera', cameras.length ? `${cameras.length - running} 路未运行` : '尚未添加摄像机'),
    stat('检测事件', `${eventCount}`, '次', 'bell', '本次运行累计触发'),
    stat('推理后端', shortBackend(hardware.recommendedInference), '', 'cpu', `GPU ${(hardware.gpus || []).length} 个 · 模型 ${info?.models?.installed?.length || 0} 个`),
    stat('硬件编码', hardware.recommendedEncoder || 'libx264', '', 'layers', encoders.length ? `${encoders.length} 个编码器可用` : '当前使用软件编码'),
  );

  const addButton = h('button', { class: 'btn primary', html: `${icon('plus')} 添加摄像机`, onclick: () => openCameraEditor(null, ctx) });

  const grid = h('div', { class: 'cam-grid' });
  if (!cameras.length) {
    grid.append(emptyState('还没有摄像机，点击「添加摄像机」接入第一路 RTSP / ONVIF 视频', 'camera'));
    grid.firstElementChild.append(h('div', { style: { marginTop: '12px' } }, addButton));
  } else {
    cameras.forEach((cam) => {
      const card = cameraCard(cam, ctx);
      cleanups.push(card.__cleanup);
      grid.append(card);
    });
  }

  const cameraSection = h('section', { class: 'section' },
    h('div', { class: 'section-head' },
      h('h3', { text: '摄像机' }),
      h('span', { class: 'desc', text: '点击卡片编辑 · 预览使用 WebRTC 低延迟' }),
      h('div', { class: 'spacer' }),
      addButton,
    ),
    grid,
  );

  // 事件
  const eventList = h('div', { class: 'event-list' });
  let recent = ctx.state.events.filter((e) => e.type === 'detection').slice(0, 8);
  if (!recent.length) {
    try {
      const data = await api.get('/system/events?since=0');
      recent = (data.events || []).filter((e) => e.type === 'detection').reverse().slice(0, 8);
    } catch { /* ignore */ }
  }
  renderEvents(eventList, recent);

  const eventsCard = h('div', { class: 'card' },
    h('div', { class: 'card-head' },
      h('h3', { text: '最近检测事件' }),
      h('span', { class: 'sub', text: 'ONVIF / 水星推送实时记录' }),
      h('div', { class: 'spacer' }),
      h('button', { class: 'btn sm ghost', text: '查看全部', onclick: () => ctx.navigate('events') }),
    ),
    eventList,
  );

  const encoderNote = !encoders.length
    ? h('div', { class: 'note warn', html: `${icon('cpu')}<div>未检测到可用硬件编码器，叠加输出将使用 libx264 软件编码。若使用 Intel 核显，请确认已安装显卡驱动；NVIDIA 需安装支持 NVENC 的驱动。</div>` })
    : h('div', { class: 'note ok', html: `${icon('check')}<div>已启用硬件加速：<b>${hardware.recommendedEncoder}</b>${hardware.recommendedDecoder ? ` · 解码 ${hardware.recommendedDecoder}` : ''} · 推理 ${shortBackend(hardware.recommendedInference)}。可在「硬件加速」页查看详情。</div>` });

  root.append(
    h('div', { class: 'row', style: { marginBottom: '16px' } },
      h('div', {},
        h('div', { style: { fontSize: '20px', fontWeight: '700', letterSpacing: '.5px' }, text: `你好，欢迎使用 ${info?.brand || '程星 ONVIF'}` }),
        h('div', { class: 'muted small', text: `${info?.tagline || ''} · 已运行 ${fmtDuration(info?.uptime || 0)}` }),
      ),
    ),
    stats,
    encoderNote,
    cameraSection,
    h('div', { style: { height: '18px' } }),
    eventsCard,
  );

  const onEvent = (event) => {
    const payload = event.detail;
    if (payload.type !== 'detection') return;
    recent.unshift(payload);
    recent = recent.slice(0, 8);
    renderEvents(eventList, recent);
  };
  window.addEventListener('cx:event', onEvent);

  return () => {
    window.removeEventListener('cx:event', onEvent);
    cleanups.forEach((fn) => fn?.());
  };
}

function stat(label, value, suffix, iconName, hint) {
  return h('div', { class: 'stat' },
    h('div', { class: 'label' }, h('span', { html: icon(iconName) }), label),
    h('div', { class: 'value' }, String(value), suffix ? h('small', { text: suffix }) : null),
    h('div', { class: 'hint', text: hint || '' }),
  );
}

function shortBackend(value) {
  if (!value) return 'CPU';
  const [name, device] = String(value).split(':');
  const map = { ultralytics: 'PyTorch', onnxruntime: 'ONNX', openvino: 'OpenVINO' };
  return `${map[name] || name}${device ? ` · ${device.toUpperCase()}` : ''}`;
}

function renderEvents(container, events) {
  container.innerHTML = '';
  if (!events.length) {
    container.append(h('div', { class: 'empty', text: '暂无检测事件，触发后会实时显示在这里' }));
    return;
  }
  events.forEach((event) => {
    const groups = (event.groups || []).map((g) => GROUP_LABELS[g] || g).join(' / ');
    container.append(h('div', { class: 'event-item' },
      h('span', { class: `event-dot ${event.active ? '' : 'off'}` }),
      h('div', { class: 'event-main' },
        h('div', { class: 'event-title' },
          h('strong', { text: event.cameraName || `摄像机 ${event.cameraId}` }),
          badge(groups || '检测', event.active ? 'green' : ''),
          event.source === 'test' ? badge('测试', 'amber') : null,
        ),
        h('div', { class: 'event-sub', text: event.active ? '检测到目标' : '目标离开 / 事件结束' }),
      ),
      h('span', { class: 'event-time', text: fmtAgo(event.timestamp) }),
    ));
  });
}
