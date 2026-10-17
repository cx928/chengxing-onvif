// 摄像机卡片（含实时预览）
import { h, icon, badge, statusDot, fmtAgo, toast, copyText } from './ui.js';
import { CameraPreview } from './preview.js';
import { api } from './api.js';
import { openCameraEditor } from './editor.js';

export const GROUP_LABELS = { person: '人形', vehicle: '车辆', animal: '动物', package: '物品', face: '人脸', other: '其他' };
export const STATUS_LABELS = { running: '运行中', stopped: '已停止', starting: '启动中', stopping: '停止中', error: '异常' };

export function cameraCard(cam, ctx) {
  const config = cam.config || {};
  const overlay = cam.streams?.overlay || {};
  const pathName = config.pathName || `cam${cam.id}`;
  const status = cam.status || 'stopped';
  const card = h('div', { class: 'cam-card' });

  const previewBox = h('div', { class: 'cam-preview video-preview' });
  let preview = null;

  if (status === 'running') {
    preview = new CameraPreview(previewBox, {
      path: `${pathName}_main`,
      cameraId: cam.id,
      webrtcPort: ctx.state.webrtcPort,
    });
    preview.start();
  } else {
    previewBox.innerHTML = `<div class="placeholder">${icon('camera')}<div>${status === 'error' ? '启动异常' : '摄像机未运行'}</div></div>`;
  }

  const groups = (config.detect?.targets || []).map((g) => GROUP_LABELS[g] || g);
  const meta = h('div', { class: 'cam-meta' },
    h('div', { class: 'row' },
      statusDot(status),
      h('span', { class: 'cam-name grow truncate', text: cam.name || config.name || `摄像机 ${cam.id}` }),
      overlay.enabled ? badge('叠加', 'purple') : null,
    ),
    h('div', { class: 'cam-line' },
      h('span', { text: `${config.source?.mainWidth || 0}×${config.source?.mainHeight || 0}` }),
      h('span', { text: '·' }),
      h('span', { text: `ONVIF :${cam.onvif?.port || config.onvif?.port || '—'}` }),
      h('span', { class: 'spacer' }),
      h('span', { text: STATUS_LABELS[status] || status }),
    ),
    h('div', { class: 'cam-line' },
      h('span', { class: 'cam-detect' }, ...(groups.length ? groups.map((g) => badge(g, 'green')) : [badge('未配置检测', '')])),
      h('span', { class: 'spacer' }),
      h('span', { text: cam.lastEventAt ? fmtAgo(cam.lastEventAt * 1000) : '无事件' }),
    ),
  );

  const startStop = h('button', {
    class: `btn sm ${status === 'running' ? 'ghost' : 'primary'}`,
    onclick: async (event) => {
      event.stopPropagation();
      const button = event.currentTarget;
      button.disabled = true;
      try {
        if (status === 'running') await api.post(`/cameras/${cam.id}/stop`);
        else await api.post(`/cameras/${cam.id}/start`);
        toast(status === 'running' ? '已请求停止' : '正在启动');
        setTimeout(() => ctx.refresh(), 900);
      } catch (error) {
        toast(error.message, 'err');
      } finally {
        button.disabled = false;
      }
    },
  }, status === 'running' ? '停止' : '启动');

  const actions = h('div', { class: 'cam-actions' },
    startStop,
    h('button', { class: 'btn sm ghost', onclick: () => openCameraEditor(cam, ctx) }, '编辑'),
    h('button', {
      class: 'btn sm ghost', title: '发送一次测试检测事件',
      onclick: async (event) => {
        event.stopPropagation();
        try {
          await api.post(`/cameras/${cam.id}/test-event`, {});
          toast('测试事件已发送');
        } catch (error) {
          toast(error.message, 'err');
        }
      },
    }, '测试'),
    h('button', {
      class: 'btn sm ghost', title: '复制 RTSP 地址',
      html: icon('copy'),
      onclick: (event) => {
        event.stopPropagation();
        copyText(cam.streams?.overlay?.url || cam.streams?.main?.url || '');
      },
    }),
  );

  card.append(previewBox, meta, actions);
  card.__cleanup = () => preview?.stop();
  card.addEventListener('click', (event) => {
    if (event.target.closest('button')) return;
    openCameraEditor(cam, ctx);
  });
  return card;
}

