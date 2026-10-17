// 摄像机编辑抽屉
import { api } from './api.js';
import { h, drawer, field, switchEl, toast, confirmDialog, badge, copyText, icon } from './ui.js';
import { openZoneEditor } from './zones.js';

const GROUP_OPTIONS = [
  ['person', '人形'],
  ['vehicle', '车辆'],
  ['animal', '动物'],
  ['package', '物品'],
];

const BACKEND_OPTIONS = [
  ['auto', '自动选择（推荐）'],
  ['ultralytics', 'Ultralytics PyTorch (.pt)'],
  ['onnxruntime', 'ONNX Runtime (.onnx)'],
  ['openvino', 'Intel OpenVINO'],
  ['mock', '模拟检测器（演示）'],
];

const PUSH_FORMATS = [
  ['json', '通用 JSON'],
  ['dahua', '大华 JSON'],
  ['hikvision', '海康 XML'],
  ['tplink', '水星 / TP-LINK 报警推送'],
  ['form', '表单 POST'],
];

function defaultCamera() {
  return {
    name: '',
    enabled: true,
    autoStart: true,
    pathName: '',
    notes: '',
    source: {
      mainUrl: '', subUrl: '',
      mainWidth: 1920, mainHeight: 1080, mainFramerate: 25,
      subWidth: 640, subHeight: 480, subFramerate: 15,
      transport: 'tcp', enabled: true,
    },
    stream: { transcodeMain: false, transcodeSub: false, enableAudio: false, enableSubstream: true, useMainAsSubstream: false, record: false },
    onvif: {
      enabled: true, port: 0, username: 'admin', password: '', profile: 'mercury',
      manufacturer: '', model: '', firmware: '', hardwareId: '', serial: '', scopes: [],
      eventTopics: {}, sendMotion: true, sendSmart: true, sendHeartbeat: true, wsDiscovery: true,
    },
    detect: {
      enabled: true, model: 'yolo11n', backend: 'auto', device: 'auto',
      confidence: 0.45, iou: 0.45, fps: 5, frameWidth: 960,
      targets: ['person', 'vehicle'], motionGate: true, motionSensitivity: 55, cooldown: 5,
      minBox: 0.0015, tracker: true, saveSnapshot: true, maxDetections: 30, zones: [],
    },
    overlay: {
      enabled: true, width: 1280, height: 720, fps: 10, encoder: 'auto', bitrate: 2000,
      showBoxes: true, showLabels: true, showConfidence: true, showZones: false,
      boxThickness: 2, boxColor: '#00D68F', fontScale: 0.55, drawTimestamp: false, extraText: '',
    },
    mercury: {
      enabled: true, pushEnabled: false, pushUrl: '', pushFormat: 'json', pushToken: '',
      pushTimeout: 5, pushRetries: 2, includeSnapshot: true, snapshotQuality: 70,
      heartbeatInterval: 30, eventCooldown: 2, extraHeaders: {},
    },
  };
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function openCameraEditor(cam, ctx) {
  const isNew = !cam || !cam.id;
  const config = cam?.config || {};
  const draft = isNew ? defaultCamera() : clone(config);
  if (isNew) {
    const defaults = ctx.state.info?.defaults || {};
    if (defaults.model) draft.detect.model = defaults.model;
    if (defaults.backend) draft.detect.backend = defaults.backend;
    if (defaults.device) draft.detect.device = defaults.device;
  }
  draft.source.mainUrl = cam?.streams?.main?.source || draft.source.mainUrl || '';
  draft.source.subUrl = cam?.streams?.sub?.source || draft.source.subUrl || '';
  const passwordWasSet = Boolean(config?.onvif?.passwordSet);
  if (!draft.onvif.port) draft.onvif.port = 0;
  if (cam) draft.name = cam.name || draft.name;

  const tabs = [
    ['basic', '基础'],
    ['detect', 'AI 检测'],
    ['overlay', '叠加输出'],
    ['onvif', 'ONVIF / 水星'],
    ['push', '事件推送'],
    ['advanced', '高级'],
  ];
  let activeTab = 'basic';

  const panel = h('div', { class: 'col', style: { gap: '14px' } });
  const tabBar = h('div', { class: 'tabs' });
  const modelsCache = { list: [] };

  const dialog = drawer({
    title: isNew ? '添加摄像机' : `编辑 · ${cam.name}`,
    subtitle: isNew ? '支持 ONVIF / RTSP 摄像机，也可接入 NVR 通道' : `ID ${cam.id} · ${draft.pathName || '未命名路径'}`,
    body: h('div', {}, tabBar, panel),
    footer: [
      !isNew ? h('button', {
        class: 'btn danger sm',
        onclick: async () => {
          if (!(await confirmDialog({ title: '删除摄像机', message: `确定删除「${cam.name}」？相关 ONVIF 端口与推流会立即释放。`, confirmText: '删除', danger: true }))) return;
          try {
            await api.del(`/cameras/${cam.id}`);
            toast('已删除');
            dialog.close();
            ctx.refresh();
          } catch (error) {
            toast(error.message, 'err');
          }
        },
      }, '删除') : null,
      h('div', { class: 'spacer' }),
      h('button', { class: 'btn ghost', onclick: () => dialog.close() }, '取消'),
      h('button', {
        class: 'btn primary',
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          button.textContent = '保存中…';
          try {
            await save();
            button.textContent = '已保存';
          } catch (error) {
            toast(error.message, 'err');
            button.disabled = false;
            button.textContent = '保存';
          }
        },
      }, '保存'),
    ].filter(Boolean),
  });

  tabs.forEach(([key, label]) => {
    const button = h('button', { class: key === activeTab ? 'active' : '', text: label });
    button.addEventListener('click', () => {
      activeTab = key;
      tabBar.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === button));
      renderPanel();
    });
    tabBar.append(button);
  });

  function input(value, onchange, props = {}) {
    return h('input', { type: 'text', value: value ?? '', ...props, oninput: (event) => onchange(event.target.value) });
  }
  function number(value, onchange, props = {}) {
    return h('input', { type: 'number', value: value ?? 0, ...props, oninput: (event) => onchange(Number(event.target.value)) });
  }
  function select(value, options, onchange) {
    const el = h('select', { onchange: (event) => onchange(event.target.value) });
    options.forEach(([key, label]) => el.append(h('option', { value: key, selected: String(key) === String(value), text: label })));
    return el;
  }
  function sw(value, onchange, label) {
    return switchEl(Boolean(value), onchange, label);
  }

  function renderPanel() {
    panel.innerHTML = '';
    if (activeTab === 'basic') panel.append(...basicTab());
    if (activeTab === 'detect') panel.append(...detectTab());
    if (activeTab === 'overlay') panel.append(...overlayTab());
    if (activeTab === 'onvif') panel.append(...onvifTab());
    if (activeTab === 'push') panel.append(...pushTab());
    if (activeTab === 'advanced') panel.append(...advancedTab());
  }

  // ---------------------------------------------------------------- 基础
  function basicTab() {
    const probeResult = h('div', { class: 'form-hint' });
    const probe = h('button', {
      class: 'btn sm ghost', html: `${icon('scan')} 探测`,
      onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        probeResult.textContent = '正在探测…';
        try {
          const result = await api.post('/probe', { url: draft.source.mainUrl });
          if (result.width) {
            draft.source.mainWidth = result.width;
            draft.source.mainHeight = result.height;
            draft.source.mainFramerate = Math.round(result.fps) || draft.source.mainFramerate;
            probeResult.innerHTML = `✔ ${result.codec?.toUpperCase()} ${result.width}×${result.height} @ ${result.fps}fps · 已回填分辨率`;
            renderPanel();
          } else {
            probeResult.textContent = '探测成功，但未读取到视频参数';
          }
        } catch (error) {
          probeResult.textContent = `✖ ${error.message}`;
        } finally {
          button.disabled = false;
        }
      },
    });
    return [
      h('div', { class: 'form-grid' },
        field('摄像机名称', input(draft.name, (v) => { draft.name = v; }), '将显示在录像机与网页控制台'),
        field('MediaMTX 路径（可选）', input(draft.pathName, (v) => { draft.pathName = v; }, { placeholder: '自动生成，如 cam3_qianmen' })),
        h('div', { class: 'full' }, field('主码流地址', input(draft.source.mainUrl, (v) => { draft.source.mainUrl = v; }, { placeholder: 'rtsp://admin:密码@192.168.1.10:554/Streaming/Channels/101' }))),
        h('div', { class: 'full' }, h('div', { class: 'row' }, probe, probeResult)),
        h('div', { class: 'full' }, field('子码流地址（可选）', input(draft.source.subUrl, (v) => { draft.source.subUrl = v; }, { placeholder: 'rtsp://.../Streaming/Channels/102' }))),
        field('主码流分辨率宽', number(draft.source.mainWidth, (v) => { draft.source.mainWidth = v; })),
        field('主码流分辨率高', number(draft.source.mainHeight, (v) => { draft.source.mainHeight = v; })),
        field('主码流帧率', number(draft.source.mainFramerate, (v) => { draft.source.mainFramerate = v; })),
        field('传输协议', select(draft.source.transport, [['tcp', 'TCP（推荐）'], ['udp', 'UDP']], (v) => { draft.source.transport = v; })),
        field('子码流宽', number(draft.source.subWidth, (v) => { draft.source.subWidth = v; })),
        field('子码流高', number(draft.source.subHeight, (v) => { draft.source.subHeight = v; })),
        field('子码流帧率', number(draft.source.subFramerate, (v) => { draft.source.subFramerate = v; })),
        h('div', { class: 'full row wrap', style: { gap: '18px', marginTop: '4px' } },
          sw(draft.enabled, (v) => { draft.enabled = v; }, '启用此摄像机'),
          sw(draft.autoStart, (v) => { draft.autoStart = v; }, '开机 / 启动服务时自动开始'),
        ),
      ),
      h('div', { class: 'note info', html: `${icon('info')}<div>主码流用于 ONVIF 与 NVR 录像；子码流可选。若不确定地址，可在摄像机后台复制 RTSP 地址，或使用「探测」验证连通性。</div>` }),
    ];
  }

  // ---------------------------------------------------------------- 检测
  function detectTab() {
    const modelSelect = h('select', {});
    const options = [{ key: 'yolo11n', name: 'YOLO11n', family: 'pt', installed: false }];
    const list = modelsCache.list.length ? modelsCache.list : options;
    list.forEach((model) => {
      modelSelect.append(h('option', {
        value: model.key,
        selected: model.key === draft.detect.model,
        text: `${model.name}${model.family ? ` · ${model.family.toUpperCase()}` : ''}${model.installed ? ' · 已安装' : ''}`,
      }));
    });
    modelSelect.value = draft.detect.model;
    modelSelect.addEventListener('change', () => { draft.detect.model = modelSelect.value; });

    const zonesInfo = h('div', { class: 'form-hint', text: `${draft.detect.zones?.length || 0} 个区域` });

    return [
      h('div', { class: 'row wrap', style: { marginBottom: '4px' } },
        sw(draft.detect.enabled, (v) => { draft.detect.enabled = v; }, '启用 AI 检测'),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn sm ghost',
          text: '使用模拟检测器',
          onclick: () => { draft.detect.backend = 'mock'; draft.detect.model = 'yolo11n'; renderPanel(); },
        }),
      ),
      h('div', { class: 'form-grid' },
        field('检测模型', modelSelect, '模型库可下载更多（YOLO26/11/8、RT-DETR、ONNX）'),
        field('推理后端', select(draft.detect.backend, BACKEND_OPTIONS, (v) => { draft.detect.backend = v; })),
        field('推理设备', select(draft.detect.device || 'auto', [
          ['auto', '自动（推荐）'], ['cpu', 'CPU'], ['cuda:0', 'NVIDIA CUDA'], ['dml', 'DirectML（Intel/AMD/NVIDIA）'],
          ['openvino', 'OpenVINO'], ['xpu', 'Intel XPU'], ['npu', 'Intel NPU'],
        ], (v) => { draft.detect.device = v; })),
        field('检测频率 (FPS)', number(draft.detect.fps, (v) => { draft.detect.fps = v; }), '建议 3–8；过高会占用更多算力'),
        field('置信度阈值', number(draft.detect.confidence, (v) => { draft.detect.confidence = v; }, { step: '0.01', min: '0.05', max: '0.99' }), '0.45 适合大多数场景'),
        field('运动灵敏度', number(draft.detect.motionSensitivity, (v) => { draft.detect.motionSensitivity = v; }), '越高越容易触发；仅运动门控开启时生效'),
        field('事件冷却（秒）', number(draft.detect.cooldown, (v) => { draft.detect.cooldown = v; })),
        h('div', { class: 'full' },
          h('div', { class: 'row wrap', style: { gap: '16px', margin: '4px 0' } },
            sw(draft.detect.motionGate, (v) => { draft.detect.motionGate = v; }, '运动门控（省算力）'),
            sw(draft.detect.tracker, (v) => { draft.detect.tracker = v; }, '目标跟踪'),
            sw(draft.detect.saveSnapshot, (v) => { draft.detect.saveSnapshot = v; }, '保存事件截图'),
          ),
        ),
        h('div', { class: 'full' }, h('div', { class: 'field' },
          h('span', { text: '检测目标' }),
          h('div', { class: 'row wrap', style: { gap: '16px', padding: '4px 0' } },
            ...GROUP_OPTIONS.map(([key, label]) => {
              const checkbox = h('input', {
                type: 'checkbox', checked: (draft.detect.targets || []).includes(key),
                onchange: (event) => {
                  const targets = new Set(draft.detect.targets || []);
                  if (event.target.checked) targets.add(key); else targets.delete(key);
                  draft.detect.targets = Array.from(targets);
                },
              });
              return h('label', { class: 'check' }, checkbox, label);
            }),
          ),
        )),
        h('div', { class: 'full row' },
          h('button', {
            class: 'btn sm',
            onclick: () => openZoneEditor({
              cameraId: cam?.id,
              zones: draft.detect.zones || [],
              running: cam?.status === 'running',
              onChange: (zones) => { draft.detect.zones = zones; renderPanel(); },
            }),
          }, '编辑检测区域'),
          zonesInfo,
        ),
      ),
      h('div', { class: 'note info', html: `${icon('cpu')}<div>Intel 核显/独显建议选择 <b>OpenVINO</b>；NVIDIA 选 <b>CUDA</b>；Windows 上 Intel/AMD/NVIDIA 都可尝试 <b>DirectML</b>。留空为自动选择。</div>` }),
    ];
  }

  // ---------------------------------------------------------------- 叠加
  function overlayTab() {
    const encoders = [{ key: 'auto', name: '自动（推荐）' }];
    (ctx.state.hardware?.encoders || []).filter((e) => e.available).forEach((encoder) => {
      encoders.push({ key: encoder.name, name: `${encoder.name} · ${encoder.description}` });
    });
    if (!encoders.find((e) => e.key === 'libx264')) encoders.push({ key: 'libx264', name: 'libx264（软件）' });
    return [
      h('div', { class: 'row wrap', style: { marginBottom: '4px' } },
        sw(draft.overlay.enabled, (v) => { draft.overlay.enabled = v; }, '输出叠加检测框的 RTSP 流'),
        h('div', { class: 'spacer' }),
        cam?.id ? h('button', {
          class: 'btn sm ghost', text: '复制叠加流地址',
          onclick: () => copyText(cam.streams?.overlay?.url || ''),
        }) : null,
      ),
      h('div', { class: 'form-grid' },
        field('输出宽度', number(draft.overlay.width, (v) => { draft.overlay.width = v; }, { step: '2' })),
        field('输出高度', number(draft.overlay.height, (v) => { draft.overlay.height = v; }, { step: '2' })),
        field('输出帧率', number(draft.overlay.fps, (v) => { draft.overlay.fps = v; })),
        field('视频编码器', select(draft.overlay.encoder, encoders.map((e) => [e.key, e.name]), (v) => { draft.overlay.encoder = v; })),
        field('码率 (kbps)', number(draft.overlay.bitrate, (v) => { draft.overlay.bitrate = v; })),
        field('边框粗细', number(draft.overlay.boxThickness, (v) => { draft.overlay.boxThickness = v; })),
        field('主色', input(draft.overlay.boxColor, (v) => { draft.overlay.boxColor = v; }, { placeholder: '#00D68F' })),
        field('字体缩放', number(draft.overlay.fontScale, (v) => { draft.overlay.fontScale = v; }, { step: '0.05' })),
        h('div', { class: 'full' },
          h('div', { class: 'row wrap', style: { gap: '16px', margin: '4px 0' } },
            sw(draft.overlay.showBoxes, (v) => { draft.overlay.showBoxes = v; }, '显示检测框'),
            sw(draft.overlay.showLabels, (v) => { draft.overlay.showLabels = v; }, '显示标签'),
            sw(draft.overlay.showConfidence, (v) => { draft.overlay.showConfidence = v; }, '显示置信度'),
            sw(draft.overlay.drawTimestamp, (v) => { draft.overlay.drawTimestamp = v; }, '显示时间戳'),
            sw(draft.overlay.showZones, (v) => { draft.overlay.showZones = v; }, '显示区域'),
          ),
        ),
        h('div', { class: 'full' }, field('自定义文字（可选）', input(draft.overlay.extraText, (v) => { draft.overlay.extraText = v; }, { placeholder: '例如：正门 · 仓库 A' }))),
      ),
      h('div', { class: 'note info', html: `${icon('layers')}<div>叠加流路径为 <b>${draft.pathName || 'camN'}_overlay</b>，NVR 可直接添加该 RTSP 地址；检测框、标签与区域会实时绘制。硬件编码器可显著降低 CPU 占用。</div>` }),
    ];
  }

  // ---------------------------------------------------------------- ONVIF
  function onvifTab() {
    const profile = (ctx.state.profiles || []).find((p) => p.key === draft.onvif.profile) || ctx.state.profiles?.[0];
    const port = draft.onvif.port || '自动分配';
    const xaddr = `http://${ctx.state.info?.localIp || '127.0.0.1'}:${port}/onvif/device_service`;
    const identity = {
      manufacturer: draft.onvif.manufacturer || profile?.manufacturer || '—',
      model: draft.onvif.model || profile?.model || '—',
      firmware: draft.onvif.firmware || profile?.firmware || '—',
    };
    return [
      h('div', { class: 'row wrap', style: { marginBottom: '4px' } },
        sw(draft.onvif.enabled, (v) => { draft.onvif.enabled = v; }, '启用 ONVIF 服务'),
        h('div', { class: 'spacer' }),
        !isNew ? h('button', {
          class: 'btn sm primary', text: '发送测试事件',
          onclick: async () => {
            try {
              await api.post(`/cameras/${cam.id}/test-event`, {});
              toast('已向 ONVIF 订阅者与推送通道发送测试事件');
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        }) : null,
      ),
      h('div', { class: 'form-grid' },
        field('ONVIF 端口', number(draft.onvif.port, (v) => { draft.onvif.port = v; }, { placeholder: '0 = 自动分配' }), '每路摄像机占用一个端口'),
        field('设备画像', select(draft.onvif.profile, (ctx.state.profiles || []).map((p) => [p.key, p.name]), (v) => { draft.onvif.profile = v; renderPanel(); }), profile?.description || ''),
        field('ONVIF 用户名', input(draft.onvif.username, (v) => { draft.onvif.username = v; })),
        field('ONVIF 密码', input(draft.onvif.password, (v) => { draft.onvif.password = v; }, { type: 'password', placeholder: passwordWasSet ? '留空保持不变' : '设置访问密码' })),
        field('厂商（覆盖画像）', input(draft.onvif.manufacturer, (v) => { draft.onvif.manufacturer = v; }, { placeholder: identity.manufacturer })),
        field('型号（覆盖画像）', input(draft.onvif.model, (v) => { draft.onvif.model = v; }, { placeholder: identity.model })),
        h('div', { class: 'full' },
          h('div', { class: 'row wrap', style: { gap: '16px', margin: '4px 0' } },
            sw(draft.onvif.wsDiscovery, (v) => { draft.onvif.wsDiscovery = v; }, 'WS-Discovery 自动发现'),
            sw(draft.onvif.sendMotion, (v) => { draft.onvif.sendMotion = v; }, '上报移动事件'),
            sw(draft.onvif.sendSmart, (v) => { draft.onvif.sendSmart = v; }, '上报人形/车辆等智能事件'),
            sw(draft.onvif.sendHeartbeat, (v) => { draft.onvif.sendHeartbeat = v; }, '订阅心跳'),
          ),
        ),
      ),
      h('div', { class: 'card pad' },
        h('div', { class: 'kv' },
          h('dt', { text: 'ONVIF 地址' }),
          h('dd', { class: 'copyable' }, h('span', { class: 'mono', text: xaddr }),
            h('button', { html: icon('copy'), title: '复制', onclick: () => copyText(xaddr) })),
          h('dt', { text: '设备身份' }),
          h('dd', {}, badge(`${identity.manufacturer} / ${identity.model}`, 'purple'), ' ', badge(`固件 ${identity.firmware}`, '')),
          h('dt', { text: '事件主题' }),
          h('dd', { class: 'form-hint', text: (profile?.topics || []).map((t) => t.label).join('、') || '标准移动事件' }),
        ),
      ),
      h('div', { class: 'note info', html: `${icon('shield')}<div>水星画像会让录像机识别为 MERCURY 设备，并通过 PullPoint 事件上报移动/人形/车辆检测。部分品牌录像机只识别自身品牌设备，可切换画像测试。</div>` }),
    ];
  }

  // ---------------------------------------------------------------- 推送
  function pushTab() {
    return [
      h('div', { class: 'row wrap', style: { marginBottom: '4px' } },
        sw(draft.mercury.pushEnabled, (v) => { draft.mercury.pushEnabled = v; }, '启用 HTTP 主动推送'),
        h('div', { class: 'spacer' }),
        !isNew ? h('button', {
          class: 'btn sm ghost', text: '测试推送',
          onclick: async () => {
            try {
              const result = await api.post(`/cameras/${cam.id}/push-test`, {});
              toast(result.message || '推送完成');
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        }) : null,
      ),
      h('div', { class: 'form-grid' },
        h('div', { class: 'full' }, field('推送地址', input(draft.mercury.pushUrl, (v) => { draft.mercury.pushUrl = v; }, { placeholder: 'http://192.168.1.100:8080/alarm' }))),
        field('推送格式', select(draft.mercury.pushFormat, PUSH_FORMATS, (v) => { draft.mercury.pushFormat = v; })),
        field('鉴权 Token（可空）', input(draft.mercury.pushToken, (v) => { draft.mercury.pushToken = v; })),
        field('超时（秒）', number(draft.mercury.pushTimeout, (v) => { draft.mercury.pushTimeout = v; })),
        field('重试次数', number(draft.mercury.pushRetries, (v) => { draft.mercury.pushRetries = v; })),
        field('事件冷却（秒）', number(draft.mercury.eventCooldown, (v) => { draft.mercury.eventCooldown = v; })),
        h('div', { class: 'full row wrap', style: { gap: '16px' } },
          sw(draft.mercury.enabled, (v) => { draft.mercury.enabled = v; }, '启用水星安防事件模拟'),
          sw(draft.mercury.includeSnapshot, (v) => { draft.mercury.includeSnapshot = v; }, '附带检测截图（Base64）'),
        ),
      ),
      h('div', { class: 'note info', html: `${icon('link')}<div>推送用于不支持 ONVIF 订阅的录像机 / 平台。若录像机支持 ONVIF 事件，优先使用上一页的 ONVIF 上报。</div>` }),
    ];
  }

  // ---------------------------------------------------------------- 高级
  function advancedTab() {
    return [
      h('div', { class: 'form-grid' },
        field('转码主码流', select(String(draft.stream.transcodeMain), [['false', '关闭（直接转发）'], ['true', '开启（兼容 H.265）']], (v) => { draft.stream.transcodeMain = v === 'true'; }), '开启会增加 CPU/GPU 占用'),
        field('转码子码流', select(String(draft.stream.transcodeSub), [['false', '关闭'], ['true', '开启']], (v) => { draft.stream.transcodeSub = v === 'true'; })),
        field('音频', select(String(draft.stream.enableAudio), [['false', '关闭'], ['true', '开启']], (v) => { draft.stream.enableAudio = v === 'true'; })),
        field('子码流', select(String(draft.stream.enableSubstream), [['true', '启用'], ['false', '禁用']], (v) => { draft.stream.enableSubstream = v === 'true'; })),
        h('div', { class: 'full' }, field('备注', h('textarea', { oninput: (event) => { draft.notes = event.target.value; } }, draft.notes || ''))),
      ),
      h('div', { class: 'note warn', html: `${icon('info')}<div>H.265 摄像机在浏览器中通常无法直接播放，但 NVR 可以正常录像。若网页预览黑屏，可在摄像机后台改为 H.264，或开启转码。</div>` }),
    ];
  }

  async function save() {
    if (!draft.name.trim()) throw new Error('请填写摄像机名称');
    if (!draft.source.mainUrl.trim()) throw new Error('请填写主码流地址');
    const payload = clone(draft);
    if (!payload.onvif.password) delete payload.onvif.password;
    payload.onvif.port = Number(payload.onvif.port) || 0;
    if (isNew) {
      const created = await api.post('/cameras', payload);
      toast(`摄像机「${created.name}」已创建`);
    } else {
      await api.put(`/cameras/${cam.id}`, payload);
      toast('已保存');
    }
    dialog.close();
    await ctx.refresh();
    window.dispatchEvent(new CustomEvent('cx:cameras'));
    if (ctx.state.route !== 'cameras') ctx.navigate('cameras');
  }

  api.get('/models').then((data) => {
    modelsCache.list = data.registry || [];
    if (activeTab === 'detect') renderPanel();
  }).catch(() => {});

  renderPanel();
  return dialog;
}
