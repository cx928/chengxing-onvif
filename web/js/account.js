// 账号相关：修改密码
import { auth } from './api.js';
import { h, modal, toast, field } from './ui.js';

export function openPasswordDialog({ force = false } = {}) {
  return new Promise((resolve) => {
    const current = h('input', { type: 'password', placeholder: '当前密码', autocomplete: 'current-password' });
    const next = h('input', { type: 'password', placeholder: '新密码（至少 8 位）', autocomplete: 'new-password' });
    const confirm = h('input', { type: 'password', placeholder: '再次输入新密码', autocomplete: 'new-password' });
    const error = h('div', { class: 'form-error hidden' });
    const submit = h('button', { class: 'btn primary' }, '保存新密码');

    const body = h('div', { class: 'col', style: { gap: '13px' } },
      force ? h('div', { class: 'note warn', text: '为了安全，请先修改默认密码再继续使用。' }) : null,
      field('当前密码', current),
      field('新密码', next, '建议使用 12 位以上，包含大小写字母、数字与符号'),
      field('确认新密码', confirm),
      error,
    );

    const dialog = modal({
      title: force ? '必须修改密码' : '修改管理员密码',
      body,
      footer: [
        force ? null : h('button', { class: 'btn ghost', onclick: () => { dialog.close(); resolve(false); } }, '取消'),
        submit,
      ].filter(Boolean),
      onClose: () => resolve(false),
    });

    submit.addEventListener('click', async () => {
      error.classList.add('hidden');
      if (next.value.length < 8) return showError('新密码至少 8 位');
      if (next.value !== confirm.value) return showError('两次输入的新密码不一致');
      submit.disabled = true;
      submit.textContent = '保存中…';
      try {
        const result = await auth.changePassword(current.value, next.value);
        toast(result.message || '密码已更新');
        dialog.close();
        resolve(true);
      } catch (err) {
        showError(err.message);
      } finally {
        submit.disabled = false;
        submit.textContent = '保存新密码';
      }
    });

    function showError(message) {
      error.textContent = message;
      error.classList.remove('hidden');
    }
  });
}
