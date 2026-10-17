// 硬件加速
import { api } from '../api.js';
import { h, icon, badge, toast, emptyState } from '../ui.js';

const VENDOR_LABELS = { nvidia: 'NVIDIA', intel: 'Intel', amd: 'AMD', apple: 'Apple', virtual: '虚拟显示', unknown: '未知' };

function backendLabel(value) {
  const [name, device] = String(value || 'cpu').split(':');
  const map = { ultralytics: 'PyTorch', onnxruntime: 'ONNX Runtime', openvino: 'OpenVINO' };
  return `${map[name] || name}${device ? ` · ${device.toUpperCase()}` : ''}`;
}

export async function render(root) {
  const info = await api.get('/system/info');
  const hw = info.hardware || {};
  const encoders = hw.encoders || [];
  const gpus = hw.gpus || [];
  const available = encoders.filter((e) => e.available);

  const stats = h('div', { class: 'stats' },
    stat('CPU', hw.cpu || '未知', `${hw.cpuCores || 0} 核 / ${hw.cpuThreads || 0} 线程`, 'cpu', '', true),
    stat('内存', `${Math.round((hw.ramMb || 0) / 1024)}`, 'GB', 'layers', hw.machine || ''),
    stat('硬件编码器', hw.recommendedEncoder || 'libx264', '', 'scan', available.length ? `${available.length} 个可用` : '仅软件编码'),
    stat('推理设备', backendLabel(hw.recommendedInference), '', 'chip', (hw.inference || []).filter((b) => b.installed).map((b) => b.name).join(' · ') || '未安装加速后端', true),
  );

  const gpuSection = h('section', { class: 'section' },
    h('div', { class: 'section-head' }, h('h3', { text: '显卡' }), h('span', { class: 'desc', text: '核显 / 独显自动识别' })),
    h('div', { class: 'hw-grid' },
      ...(gpus.length ? gpus.map((gpu) => h('div', { class: 'hw-item' },
        h('div', { class: 'ico', html: icon('cpu') }),
        h('div', {},
          h('div', { class: 'name', text: gpu.name }),
          h('div', { class: 'meta', text: `${VENDOR_LABELS[gpu.vendor] || gpu.vendor} · ${gpu.kind}${gpu.driver ? ` · 驱动 ${gpu.driver}` : ''}` }),
        ),
      )) : [emptyState('未检测到独立/集成显卡', 'cpu')]),
    ),
  );

  const encoderTable = h('div', { class: 'table-wrap' },
    h('table', { class: 'tbl' },
      h('thead', {}, h('tr', {},
        h('th', { text: '编码器' }), h('th', { text: '编码' }), h('th', { text: '厂商' }),
        h('th', { text: '状态' }), h('th', { text: '说明' }), h('th', { text: '实测信息' }),
      )),
      h('tbody', {}, ...encoders.map((encoder) => h('tr', {},
        h('td', { class: 'mono', text: encoder.name }),
        h('td', { text: encoder.codec?.toUpperCase() }),
        h('td', { text: VENDOR_LABELS[encoder.vendor] || encoder.vendor.toUpperCase() }),
        h('td', {}, encoder.available ? badge('可用', 'green') : encoder.present ? badge('不可用', 'red') : badge('未编译', '')),
        h('td', { class: 'small muted', text: encoder.description }),
        h('td', { class: 'small muted', text: encoder.testError || (encoder.available ? '实测通过' : '—') }),
      ))),
    ),
  );

  const inferenceSection = h('div', { class: 'hw-grid' },
    ...(hw.inference || []).map((backend) => h('div', { class: 'hw-item' },
      h('div', { class: 'ico', html: icon('chip') }),
      h('div', {},
        h('div', { class: 'name' }, backend.name, ' ', backend.installed ? badge('已安装', 'green') : badge('未安装', '')),
        h('div', { class: 'meta', text: backend.installed ? `${backend.version || ''} · ${(backend.devices || []).join(' / ') || 'CPU'}` : backend.note }),
      ),
    )),
  );

  const notes = (hw.notes || []).map((note) => h('div', { class: 'note warn', html: `${icon('info')}<div>${note}</div>` }));

  const refresh = h('button', {
    class: 'btn', html: `${icon('refresh')} 重新探测`,
    onclick: async (event) => {
      const button = event.currentTarget;
      button.disabled = true;
      try {
        const job = await api.post('/hardware/refresh', {});
        for (let i = 0; i < 120; i += 1) {
          await new Promise((resolve) => setTimeout(resolve, 1000));
          const status = await api.get(`/jobs/${job.id}`);
          button.textContent = `探测中 ${Math.round(status.progress * 100)}%`;
          if (status.status === 'done') break;
          if (status.status === 'error') throw new Error(status.error);
        }
        toast('硬件画像已更新');
        const { navigate } = await import('../app.js');
        navigate('hardware', true);
      } catch (error) {
        toast(error.message, 'err');
      } finally {
        button.disabled = false;
        button.textContent = '重新探测';
      }
    },
  });

  root.append(
    h('div', { class: 'toolbar' },
      h('span', { class: 'desc', text: `FFmpeg ${hw.ffmpegVersion || '未安装'} · ${hw.ffmpegPath || ''}` }),
      h('div', { class: 'spacer' }),
      refresh,
    ),
    stats,
    ...notes,
    gpuSection,
    h('section', { class: 'section' },
      h('div', { class: 'section-head' }, h('h3', { text: '视频编码器' }), h('span', { class: 'desc', text: '实测可用性（启动时探测并缓存）' })),
      encoderTable,
    ),
    h('section', { class: 'section' },
      h('div', { class: 'section-head' }, h('h3', { text: '推理后端' }), h('span', { class: 'desc', text: '检测模型运行在哪种加速框架上' })),
      inferenceSection,
    ),
    h('div', { class: 'note info', html: `${icon('cpu')}<div><b>推荐搭配：</b>Intel 核显/锐炫 → OpenVINO（推理）+ h264_qsv（编码）；NVIDIA → CUDA/TensorRT + h264_nvenc；AMD → DirectML（推理）+ h264_amf（Windows）。无需独显也能用 CPU 运行全部功能。</div>` }),
  );
}

function stat(label, value, suffix, iconName, hint, compact = false) {
  return h('div', { class: 'stat' },
    h('div', { class: 'label' }, h('span', { html: icon(iconName) }), label),
    h('div', { class: `value${compact ? ' compact' : ''}` }, String(value), suffix ? h('small', { text: suffix }) : null),
    h('div', { class: 'hint', text: hint || '' }),
  );
}
