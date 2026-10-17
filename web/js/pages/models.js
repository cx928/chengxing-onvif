// 模型库
import { api } from '../api.js';
import { h, icon, badge, toast, confirmDialog, fmtBytes, emptyState, modal } from '../ui.js';

const FAMILY_LABELS = { pt: 'PyTorch', onnx: 'ONNX', openvino: 'OpenVINO', custom: '自定义' };

export async function render(root, ctx) {
  root.append(h('div', { class: 'note info', html: `${icon('layers')}<div>正在加载模型注册表…</div>` }));
  let data;
  try {
    data = await api.get('/models');
  } catch (error) {
    root.innerHTML = '';
    root.append(h('div', { class: 'note warn', text: error.message }));
    return;
  }
  root.innerHTML = '';

  const registry = data.registry || [];
  const custom = data.custom || [];
  const backends = data.backends || [];

  const toolbar = h('div', { class: 'toolbar' },
    h('div', { class: 'seg' },
      ...['all', 'pt', 'onnx', 'installed'].map((key) => {
        const label = key === 'all' ? '全部' : key === 'installed' ? '已安装' : FAMILY_LABELS[key];
        const button = h('button', { class: key === 'all' ? 'active' : '', text: label });
        button.addEventListener('click', () => {
          toolbar.querySelectorAll('.seg button').forEach((b) => b.classList.toggle('active', b === button));
          draw(key);
        });
        return button;
      }),
    ),
    h('div', { class: 'spacer' }),
    h('span', { class: 'desc', text: '支持导出 ONNX / OpenVINO 以启用 GPU 加速' }),
  );

  const grid = h('div', { class: 'model-grid' });
  root.append(toolbar, grid);

  // 推理后端
  const backendCard = h('div', { class: 'card', style: { marginTop: '22px' } },
    h('div', { class: 'card-head' }, h('h3', { text: '推理后端' }), h('span', { class: 'sub', text: '按需安装即可获得 GPU 加速' })),
    h('div', { class: 'card-body' },
      h('div', { class: 'hw-grid' }, ...backends.map((backend) => h('div', { class: 'hw-item' },
        h('div', { class: 'ico', html: icon('cpu') }),
        h('div', {},
          h('div', { class: 'name' }, backend.name, ' ', backend.installed ? badge('已安装', 'green') : badge('未安装', '')),
          h('div', { class: 'meta', text: backend.installed ? `${backend.version || ''} ${(backend.devices || []).join(' / ')}` : backend.note || '' }),
        ),
      ))),
    ),
  );
  if (!backends.length) backendCard.remove();

  root.append(h('div', { class: 'section' },
    h('div', { class: 'section-head' }, h('h3', { text: '自定义模型' }), h('span', { class: 'desc', text: '放入 data/models 目录后自动识别' })),
    h('div', { class: 'model-grid' },
      ...(custom.length ? custom.map((model) => h('div', { class: 'model-card installed' },
        h('div', { class: 'model-top' },
          h('div', {}, h('div', { class: 'model-name', text: model.name }), h('div', { class: 'model-key', text: model.file })),
          h('div', { class: 'spacer' }),
          badge('本机', 'green'),
        ),
        h('div', { class: 'model-desc', text: `${model.family.toUpperCase()} · ${model.sizeMb} MB · 可直接在选择模型时使用` }),
      )) : [emptyState('暂无自定义模型', 'box')]),
    ),
  ));

  draw('all');

  function draw(filter) {
    grid.innerHTML = '';
    const items = registry.filter((model) => {
      if (filter === 'installed') return model.installed;
      if (filter === 'all') return true;
      return model.family === filter;
    });
    if (!items.length) {
      grid.append(emptyState('该分类下暂无模型', 'layers'));
      return;
    }
    items.forEach((model) => grid.append(modelCard(model)));
  }

  function modelCard(model) {
    const actions = h('div', { class: 'model-actions' });
    if (!model.installed && model.url) {
      actions.append(h('button', {
        class: 'btn sm primary', html: `${icon('download')} 下载`,
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            const job = await api.post(`/models/${model.key}/download`, {});
            await pollJob(job.id, (progress) => { button.textContent = `下载中 ${Math.round(progress * 100)}%`; });
            toast(`${model.name} 下载完成`);
            await ctx.refresh();
            refreshPage();
          } catch (error) {
            toast(error.message, 'err');
          } finally {
            button.disabled = false;
          }
        },
      }));
    }
    if (model.installed) {
      actions.append(badge('已安装', 'green'));
      if (model.family === 'pt') {
        actions.append(h('button', {
          class: 'btn sm ghost', text: '导出',
          onclick: () => exportModel(model),
        }));
      }
      actions.append(h('button', {
        class: 'btn sm ghost', title: '删除模型文件',
        html: icon('trash'),
        onclick: async () => {
          if (!(await confirmDialog({ title: '删除模型', message: `确定删除 ${model.name} 的本地文件？`, confirmText: '删除', danger: true }))) return;
          try {
            await api.del(`/models/${model.key}`);
            toast('已删除');
            refreshPage();
          } catch (error) {
            toast(error.message, 'err');
          }
        },
      }));
    }
    if (!model.url && model.family === 'custom') {
      actions.append(h('span', { class: 'form-hint', text: '将模型文件放入 models 目录' }));
    }
    return h('div', { class: `model-card ${model.installed ? 'installed' : ''}` },
      h('div', { class: 'model-top' },
        h('div', {},
          h('div', { class: 'model-name', text: model.name }),
          h('div', { class: 'model-key', text: `${model.key} · ${FAMILY_LABELS[model.family] || model.family}` }),
        ),
        h('div', { class: 'spacer' }),
        model.installed ? badge('已安装', 'green') : badge(model.sizeMb ? `${model.sizeMb} MB` : '—', ''),
      ),
      h('div', { class: 'chip-list' },
        ...(model.tags || []).map((tag) => badge(tag, tag === '推荐' ? 'green' : '')),
        badge(`${model.labels} 类`, ''),
      ),
      h('div', { class: 'model-desc', text: model.description || '' }),
      actions,
    );
  }

  function exportModel(model) {
    const format = 'onnx';
    const body = h('div', { class: 'col', style: { gap: '12px' } },
      h('div', { class: 'form-hint', text: '导出后可在「推理后端」中选择 ONNX Runtime / OpenVINO，显著提升 GPU 利用率。导出在后台执行，可能需要数分钟。' }),
      h('div', { class: 'row' },
        h('button', {
          class: 'btn primary', text: '导出 ONNX',
          onclick: async () => {
            try {
              const job = await api.post(`/models/${model.key}/export`, { format: 'onnx' });
              await pollJob(job.id, () => {});
              toast('ONNX 导出完成，可在模型列表中看到');
              dialog.close();
              refreshPage();
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        }),
        h('button', {
          class: 'btn', text: '导出 OpenVINO',
          onclick: async () => {
            try {
              const job = await api.post(`/models/${model.key}/export`, { format: 'openvino' });
              await pollJob(job.id, () => {});
              toast('OpenVINO 导出完成');
              dialog.close();
              refreshPage();
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        }),
      ),
    );
    const dialog = modal({ title: `导出 ${model.name}`, body, footer: [h('button', { class: 'btn ghost', text: '关闭', onclick: () => dialog.close() })] });
  }

  function refreshPage() {
    ctx.navigate('models', true);
  }
}

async function pollJob(jobId, onProgress) {
  for (let i = 0; i < 600; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const job = await api.get(`/jobs/${jobId}`);
    onProgress?.(job.progress, job);
    if (job.status === 'done') return job;
    if (job.status === 'error') throw new Error(job.error || '任务失败');
  }
  throw new Error('任务超时');
}
