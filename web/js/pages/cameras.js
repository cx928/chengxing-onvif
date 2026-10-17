// 摄像机列表
import { h, icon, badge, emptyState } from '../ui.js';
import { cameraCard } from '../camera-card.js';
import { openCameraEditor } from '../editor.js';

export async function render(root, ctx) {
  const cleanups = [];
  let filter = 'all';
  let keyword = '';

  const grid = h('div', { class: 'cam-grid' });
  const count = h('span', { class: 'desc' });

  const toolbar = h('div', { class: 'toolbar' },
    h('div', { class: 'search' }, h('span', { html: icon('search') }),
      h('input', {
        type: 'search', placeholder: '搜索名称 / 地址 / 端口',
        oninput: (event) => { keyword = event.target.value.trim().toLowerCase(); draw(); },
      })),
    h('div', { class: 'seg' },
      ...[['all', '全部'], ['running', '运行中'], ['stopped', '已停止'], ['error', '异常']].map(([key, label]) => {
        const button = h('button', { class: key === filter ? 'active' : '', text: label });
        button.addEventListener('click', () => {
          filter = key;
          toolbar.querySelectorAll('.seg button').forEach((b) => b.classList.toggle('active', b === button));
          draw();
        });
        return button;
      }),
    ),
    h('div', { class: 'spacer' }),
    count,
    h('button', { class: 'btn primary', html: `${icon('plus')} 添加摄像机`, onclick: () => openCameraEditor(null, ctx) }),
  );

  function draw() {
    cleanups.splice(0).forEach((fn) => fn?.());
    grid.innerHTML = '';
    const cameras = (ctx.state.cameras || []).filter((cam) => {
      if (filter !== 'all' && cam.status !== filter) return false;
      if (!keyword) return true;
      const text = `${cam.name} ${cam.config?.source?.mainUrl || ''} ${cam.onvif?.port || ''} ${cam.config?.pathName || ''}`.toLowerCase();
      return text.includes(keyword);
    });
    count.textContent = `${cameras.length} / ${ctx.state.cameras.length} 路`;
    if (!cameras.length) {
      grid.append(emptyState(filter === 'all' ? '还没有摄像机，点击右上角添加' : '没有符合条件的摄像机', 'camera'));
      return;
    }
    cameras.forEach((cam) => {
      const card = cameraCard(cam, ctx);
      cleanups.push(card.__cleanup);
      grid.append(card);
    });
  }

  root.append(toolbar, grid);
  draw();

  const onCameras = () => draw();
  window.addEventListener('cx:cameras', onCameras);
  return () => {
    window.removeEventListener('cx:cameras', onCameras);
    cleanups.forEach((fn) => fn?.());
  };
}
