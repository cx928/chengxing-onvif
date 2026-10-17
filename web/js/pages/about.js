// 关于
import { h, icon, badge } from '../ui.js';

export async function render(root, ctx) {
  const info = ctx.state.info || {};
  const links = info.links || {};
  const features = [
    ['layers', '多模型检测', 'YOLO26 / YOLO11 / YOLOv8 / YOLOv10 / RT-DETR / YOLO-World，支持 ONNX 与 OpenVINO，随时切换。'],
    ['camera', 'ONVIF 虚拟摄像机', '把任意 RTSP 摄像头变成标准 ONVIF 设备，支持 WS-Discovery、多码流、快照与事件订阅。'],
    ['bell', '水星安防事件模拟', '以内置厂商画像（MERCURY / TP-LINK VIGI 等）向录像机上报移动、人形、车辆检测事件。'],
    ['scan', '检测框叠加输出', '在视频流上实时绘制检测框、标签、置信度与区域，输出独立 RTSP 流供 NVR 使用。'],
    ['cpu', '硬件加速', 'Intel QSV / NVIDIA NVENC / AMD AMF / VAAPI 编码，OpenVINO / CUDA / DirectML 推理，自动测速选用。'],
    ['power', '开机静默启动', 'Windows 计划任务、systemd、launchd 一键安装，开机无窗口自动运行。'],
  ];

  const linkCard = (label, value, href, iconName) => h('a', { class: 'hw-item', href, target: '_blank', rel: 'noreferrer', style: { textDecoration: 'none', color: 'inherit' } },
    h('div', { class: 'ico', html: icon(iconName) }),
    h('div', {},
      h('div', { class: 'name', text: label }),
      h('div', { class: 'meta', text: value }),
    ),
  );

  root.append(
    h('div', { class: 'card pad', style: { display: 'flex', gap: '18px', alignItems: 'center', marginBottom: '18px' } },
      h('div', { class: 'logo-mark', style: { width: '64px', height: '64px', fontSize: '24px' }, text: 'CX' }),
      h('div', { class: 'grow' },
        h('div', { style: { fontSize: '22px', fontWeight: '700', letterSpacing: '1px' }, text: info.brand || '程星 ONVIF' }),
        h('div', { class: 'muted', text: info.tagline || '多模型 AI 检测 · ONVIF 虚拟摄像机 · 硬件加速' }),
        h('div', { class: 'row', style: { marginTop: '8px' } },
          badge(`版本 ${info.versionString || info.version || '1.0.0'}`, 'green'),
          badge('MIT License', ''),
          badge(`Python ${info.python || ''}`, ''),
          badge(info.os || '', ''),
        ),
      ),
      h('div', { class: 'col', style: { alignItems: 'flex-end', gap: '6px' } },
        h('span', { class: 'form-hint', text: `© ${new Date().getFullYear()} 程星 ONVIF` }),
        h('span', { class: 'form-hint', text: `主机 ${info.host || ''} · ${info.localIp || ''}` }),
      ),
    ),
    h('div', { class: 'model-grid', style: { marginBottom: '18px' } },
      ...features.map(([iconName, title, desc]) => h('div', { class: 'model-card' },
        h('div', { class: 'row' }, h('div', { class: 'ico', style: { width: '30px', height: '30px', borderRadius: '8px', display: 'grid', placeItems: 'center', background: 'rgba(34,197,94,.1)', color: 'var(--accent)' }, html: icon(iconName) }),
          h('div', { class: 'model-name', text: title })),
        h('div', { class: 'model-desc', text: desc }),
      )),
    ),
    h('section', { class: 'section' },
      h('div', { class: 'section-head' }, h('h3', { text: '联系作者' })),
      h('div', { class: 'hw-grid' },
        linkCard('B 站主页', 'space.bilibili.com/1765875510', links.bilibili || 'https://space.bilibili.com/1765875510', 'external'),
        linkCard('GitHub', 'github.com/cx928', links.github || 'https://github.com/cx928', 'link'),
        linkCard('电子邮箱', links.email || 'wanghaotian@cxdx.edu.kg', `mailto:${links.email || 'wanghaotian@cxdx.edu.kg'}`, 'info'),
      ),
    ),
    h('section', { class: 'section' },
      h('div', { class: 'section-head' }, h('h3', { text: '两个版本，同一内核' })),
      h('div', { class: 'card pad' },
        h('div', { class: 'kv' },
          h('dt', { text: '纯网页版' }), h('dd', { text: '浏览器打开即用，适合 NAS / 服务器 / 长期运行的录像机场景。' }),
          h('dt', { text: 'WinUI 桌面版' }), h('dd', { text: '本地控制台：启动/停止服务、修改密码、开机自启，一键打开网页控制台。' }),
          h('dt', { text: '数据目录' }), h('dd', { class: 'mono', text: info.paths?.home || '%ProgramData%\\ChengXingOnvif' }),
          h('dt', { text: '技术栈' }), h('dd', { text: 'Python · Flask · MediaMTX · FFmpeg · OpenCV · Ultralytics · ONNX Runtime · OpenVINO · WinUI 3' }),
        ),
      ),
    ),
    h('div', { class: 'note info', html: `${icon('info')}<div>本项目以 MIT 协议开源。视频编解码依赖 <a href="https://ffmpeg.org/" target="_blank" rel="noreferrer">FFmpeg</a>，RTSP 服务依赖 <a href="https://github.com/bluenviron/mediamtx" target="_blank" rel="noreferrer">MediaMTX</a>；YOLO 系列模型的使用需遵守 Ultralytics AGPL-3.0 许可。请遵守当地法律法规，仅用于合法的安防场景。</div>` }),
  );
}
