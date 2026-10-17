// 系统设置
import { api, getToken } from '../api.js';
import { h, icon, badge, field, switchEl, toast, confirmDialog, modal } from '../ui.js';
import { openPasswordDialog } from '../account.js';

export async function render(root, ctx) {
  const [settingsData, autostart] = await Promise.all([
    api.get('/system/settings'),
    api.get('/service/autostart').catch(() => ({})),
  ]);
  const draft = { ...settingsData.settings };
  const authInfo = settingsData.auth || {};
  const hardware = ctx.state.hardware || {};
  const cleanups = [];

  let activeTab = 'general';
  const tabBar = h('div', { class: 'tabs' });
  const panel = h('div', {});

  const tabs = [
    ['general', '基础'],
    ['security', '安全'],
    ['startup', '开机自启'],
    ['maintenance', '维护'],
  ];
  tabs.forEach(([key, label]) => {
    const button = h('button', { class: key === activeTab ? 'active' : '', text: label });
    button.addEventListener('click', () => {
      activeTab = key;
      tabBar.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === button));
      draw();
    });
    tabBar.append(button);
  });

  function draw() {
    panel.innerHTML = '';
    if (activeTab === 'general') panel.append(generalTab());
    if (activeTab === 'security') panel.append(securityTab());
    if (activeTab === 'startup') panel.append(startupTab());
    if (activeTab === 'maintenance') panel.append(maintenanceTab());
  }

  function input(value, onchange, props = {}) {
    return h('input', { type: 'text', value: value ?? '', ...props, oninput: (event) => onchange(event.target.value) });
  }
  function number(value, onchange) {
    return h('input', { type: 'number', value: value ?? 0, oninput: (event) => onchange(Number(event.target.value)) });
  }
  function select(value, options, onchange) {
    const el = h('select', { onchange: (event) => onchange(event.target.value) });
    options.forEach(([key, label]) => el.append(h('option', { value: key, selected: String(key) === String(value), text: label })));
    return el;
  }

  // ---------------------------------------------------------------- 基础
  function generalTab() {
    const encoderOptions = [['auto', '自动（推荐）'], ['libx264', 'libx264 软件编码']];
    (hardware.encoders || []).filter((e) => e.available && e.name !== 'libx264').forEach((e) => encoderOptions.push([e.name, `${e.name} · ${e.description}`]));
    return h('div', { class: 'col', style: { gap: '16px' } },
      h('div', { class: 'form-grid' },
        field('Web 端口', number(draft.webPort, (v) => { draft.webPort = v; }), '修改后需重启服务'),
        field('RTSP 端口', number(draft.rtspPort, (v) => { draft.rtspPort = v; }), 'NVR / 播放器连接端口'),
        field('监听地址', input(draft.bind, (v) => { draft.bind = v; }), '0.0.0.0 为全部网卡'),
        field('ONVIF 起始端口', number(draft.onvifPortStart, (v) => { draft.onvifPortStart = v; }), '每路摄像机依次占用'),
        field('HLS 端口', number(draft.hlsPort, (v) => { draft.hlsPort = v; })),
        field('WebRTC 端口', number(draft.webrtcPort, (v) => { draft.webrtcPort = v; })),
        field('视频编码器', select(draft.encoder || 'auto', encoderOptions, (v) => { draft.encoder = v; })),
        field('硬件解码', select(draft.decodeMode || 'auto', [
          ['auto', '自动（推荐，软件解码更稳）'], ['software', '软件解码'], ['qsv', 'Intel QSV'],
          ['cuda', 'NVIDIA CUDA'], ['d3d11va', 'D3D11VA'], ['vaapi', 'VAAPI (Linux)'],
        ], (v) => { draft.decodeMode = v; })),
        field('FFmpeg 路径', input(draft.ffmpegPath, (v) => { draft.ffmpegPath = v; }, { placeholder: '留空自动查找' })),
        field('MediaMTX 路径', input(draft.mediamtxPath, (v) => { draft.mediamtxPath = v; }, { placeholder: '留空自动查找 / 下载' })),
        h('div', { class: 'full row wrap', style: { gap: '18px' } },
          switchEl(Boolean(draft.openBrowser), (v) => { draft.openBrowser = v; }, '启动时自动打开浏览器'),
          switchEl(Boolean(draft.checkUpdates), (v) => { draft.checkUpdates = v; }, '检查更新'),
        ),
      ),
      h('div', { class: 'row' },
        h('button', {
          class: 'btn primary', text: '保存设置',
          onclick: async () => {
            try {
              const result = await api.put('/system/settings', draft);
              toast(result.restartRequired ? '已保存，部分设置需重启服务生效' : '设置已保存');
              await ctx.refresh();
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        }),
        h('span', { class: 'form-hint', text: `数据目录：${settingsData.paths?.home || ''} · 模型目录：${settingsData.paths?.models || ''}` }),
      ),
    );
  }

  // ---------------------------------------------------------------- 安全
  function securityTab() {
    const requireLogin = switchEl(Boolean(authInfo.requireLogin), async (value) => {
      try {
        await api.put('/system/settings', { ...draft, requireLogin: value });
        authInfo.requireLogin = value;
        toast(value ? '已开启登录验证' : '已关闭登录验证（局域网内任何人可访问）');
      } catch (error) {
        toast(error.message, 'err');
      }
    }, '启用登录验证');
    return h('div', { class: 'col', style: { gap: '16px' } },
      h('div', { class: 'card pad' },
        h('div', { class: 'row' }, h('div', { class: 'grow' },
          h('div', { style: { fontSize: '13px' }, text: `管理员账号：${authInfo.username || 'admin'}` }),
          h('div', { class: 'form-hint', text: authInfo.mustChangePassword ? '当前仍在使用默认密码，请立即修改。' : '密码使用 PBKDF2 加盐存储。' }),
        ), h('button', { class: 'btn', text: '修改密码', onclick: () => openPasswordDialog({ force: Boolean(authInfo.mustChangePassword) }) })),
        h('div', { style: { height: '12px' } }),
        h('div', { class: 'row' }, requireLogin),
      ),
      h('div', { class: 'note warn', html: `${icon('shield')}<div>关闭登录验证后，同一局域网内任何人都能打开控制台并修改配置。建议仅在完全可信的内网环境中使用。</div>` }),
      h('div', { class: 'card pad' },
        h('div', { style: { fontSize: '13px', marginBottom: '8px' }, text: 'ONVIF 与 RTSP 凭据' }),
        h('div', { class: 'form-grid' },
          field('RTSP 用户名', input(draft.rtspUsername, (v) => { draft.rtspUsername = v; })),
          field('RTSP 密码', input(draft.rtspPassword, (v) => { draft.rtspPassword = v; }, { type: 'password' })),
          h('div', { class: 'full' }, h('label', { class: 'switch' },
            h('input', { type: 'checkbox', checked: Boolean(draft.rtspAuthEnabled), onchange: (event) => { draft.rtspAuthEnabled = event.target.checked; } }),
            h('span', { class: 'track' }), h('span', { text: 'RTSP 播放需要认证（NVR 需填写上面的用户名密码）' }),
          )),
        ),
        h('div', { style: { marginTop: '12px' } }, h('button', {
          class: 'btn', text: '保存凭据',
          onclick: async () => {
            try {
              await api.put('/system/settings', { rtspUsername: draft.rtspUsername, rtspPassword: draft.rtspPassword, rtspAuthEnabled: draft.rtspAuthEnabled });
              toast('凭据已保存');
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        })),
      ),
    );
  }

  // ---------------------------------------------------------------- 开机自启
  function startupTab() {
    const installed = Boolean(autostart.installed);
    return h('div', { class: 'col', style: { gap: '16px' } },
      h('div', { class: 'card pad' },
        h('div', { class: 'row' },
          h('div', { class: 'grow' },
            h('div', { style: { fontSize: '13px' }, text: '开机静默启动' }),
            h('div', { class: 'form-hint', text: installed ? `已安装 · ${autostart.platform === 'windows' ? (autostart.task ? '系统计划任务（SYSTEM，开机即启动，无窗口）' : '当前用户启动文件夹') : autostart.unit || ''}` : '未安装，服务不会自动启动' }),
          ),
          installed ? badge('已启用', 'green') : badge('未启用', ''),
        ),
        h('div', { class: 'row', style: { marginTop: '12px' } },
          h('button', {
            class: 'btn primary', text: installed ? '重新安装' : '启用开机自启',
            onclick: async (event) => {
              const button = event.currentTarget;
              button.disabled = true;
              try {
                const result = await api.post('/service/autostart', { enabled: true, mode: 'auto' });
                toast(result.message);
                autostart.installed = true;
                draw();
              } catch (error) {
                toast(error.message, 'err');
              } finally {
                button.disabled = false;
              }
            },
          }),
          installed ? h('button', {
            class: 'btn danger', text: '关闭自启',
            onclick: async () => {
              try {
                const result = await api.post('/service/autostart', { enabled: false });
                toast(result.message);
                autostart.installed = false;
                draw();
              } catch (error) {
                toast(error.message, 'err');
              }
            },
          }) : null,
        ),
      ),
      h('div', { class: 'note info', html: `${icon('power')}<div>Windows 下以管理员身份安装会创建 <b>SYSTEM 计划任务</b>，开机后无需登录、无控制台窗口，日志写入数据目录 <code>logs/cxonvif.log</code>。非管理员则加入当前用户启动文件夹（登录后静默启动）。</div>` }),
      h('div', { class: 'card pad' },
        h('div', { style: { fontSize: '13px', marginBottom: '6px' }, text: '手动命令' }),
        h('pre', { class: 'logbox', style: { height: 'auto' }, text: 'python -m cxonvif serve            # 前台启动\npython -m cxonvif serve --silent   # 静默启动\npython -m cxonvif autostart install\npython -m cxonvif autostart status' }),
      ),
    );
  }

  // ---------------------------------------------------------------- 维护
  function maintenanceTab() {
    const logBox = h('div', { class: 'logbox', text: '正在加载日志…' });
    let logTimer = null;
    const loadLogs = async () => {
      try {
        const logs = await api.get('/system/logs?limit=200');
        logBox.innerHTML = '';
        logs.forEach((entry) => {
          logBox.append(h('div', { class: `lv-${entry.level}` },
            h('span', { class: 'ts', text: entry.time }),
            ` ${entry.source.padEnd(9)} ${entry.message}`,
          ));
        });
        logBox.scrollTop = logBox.scrollHeight;
      } catch (error) {
        logBox.textContent = error.message;
      }
    };
    loadLogs();
    logTimer = setInterval(loadLogs, 4000);
    cleanups.push(() => clearInterval(logTimer));

    const importPath = h('input', { type: 'text', placeholder: 'C:\\Program Files\\Tonys-Onvif-Server\\data\\camera_config.json' });

    return h('div', { class: 'col', style: { gap: '16px' } },
      h('div', { class: 'row' },
        h('button', { class: 'btn', html: `${icon('refresh')} 刷新日志`, onclick: loadLogs }),
        h('div', { class: 'spacer' }),
        h('button', {
          class: 'btn', html: `${icon('download')} 导出配置`,
          onclick: async () => {
            try {
              const response = await fetch('/api/v2/system/config/export', { headers: { Authorization: `Bearer ${getToken()}` } });
              const blob = await response.blob();
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement('a');
              anchor.href = url;
              anchor.download = 'chengxing-onvif-backup.json';
              anchor.click();
              URL.revokeObjectURL(url);
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        }),
      ),
      logBox,
      h('div', { class: 'card pad' },
        h('div', { style: { fontSize: '13px', marginBottom: '8px' }, text: '导入旧版 Tonys-onvif 配置' }),
        h('div', { class: 'row' }, importPath, h('button', {
          class: 'btn', text: '导入',
          onclick: async () => {
            try {
              const result = await api.post('/import/tonys', { path: importPath.value.trim() });
              toast(`已导入 ${result.imported} 路摄像机`);
              if (result.warnings?.length) toast(result.warnings.join('；'), 'err');
              await ctx.refresh();
            } catch (error) {
              toast(error.message, 'err');
            }
          },
        })),
      ),
      h('div', { class: 'card pad' },
        h('div', { style: { fontSize: '13px', marginBottom: '8px' }, text: '服务操作' }),
        h('div', { class: 'row wrap' },
          h('button', {
            class: 'btn', html: `${icon('refresh')} 重启服务`,
            onclick: async () => {
              if (!(await confirmDialog({ title: '重启服务', message: '重启期间所有摄像机与推流会短暂中断，确定继续？', confirmText: '重启' }))) return;
              try {
                await api.post('/system/restart', {});
                showRestarting();
              } catch (error) {
                toast(error.message, 'err');
              }
            },
          }),
          h('button', {
            class: 'btn danger', html: `${icon('power')} 停止服务`,
            onclick: async () => {
              if (!(await confirmDialog({ title: '停止服务', message: '停止后网页与 ONVIF 服务将不可用，需要通过命令行或桌面端重新启动。', confirmText: '停止', danger: true }))) return;
              try {
                await api.post('/system/shutdown', {});
                document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font-family:sans-serif;color:#8fa3bd;background:#070b13">服务已停止，可关闭此页面</div>';
              } catch (error) {
                toast(error.message, 'err');
              }
            },
          }),
        ),
      ),
    );
  }

  root.append(tabBar, panel);
  draw();

  const onTab = (event) => {
    const tab = event.detail;
    const index = tabs.findIndex(([key]) => key === tab);
    if (index >= 0) {
      activeTab = tab;
      tabBar.querySelectorAll('button').forEach((b, i) => b.classList.toggle('active', i === index));
      draw();
    }
  };
  window.addEventListener('cx:settings-tab', onTab);

  return () => {
    window.removeEventListener('cx:settings-tab', onTab);
    cleanups.forEach((fn) => fn?.());
  };
}

function showRestarting() {
  modal({
    title: '正在重启服务',
    body: h('div', { class: 'col', style: { gap: '12px' } },
      h('div', { class: 'note info', text: '服务正在重新加载，请稍候…' }),
      h('div', { class: 'progress' }, h('span', { style: { width: '60%' } })),
    ),
  });
  let attempts = 0;
  const timer = setInterval(async () => {
    attempts += 1;
    try {
      const health = await fetch('/api/v2/health').then((r) => (r.ok ? r.json() : null));
      if (health?.status === 'ok') {
        clearInterval(timer);
        location.reload();
      }
    } catch { /* not ready */ }
    if (attempts > 40) {
      clearInterval(timer);
      toast('重启超时，请手动刷新页面', 'err');
    }
  }, 1500);
}
