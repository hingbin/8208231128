(() => {
  const ctx = window.__CONFLICT_DETAIL__ || {};
  const conflictId = Number(ctx.conflictId || 0);
  const tokenFromTemplate = ctx.token || null;

  const statusBox = document.getElementById('conflict-status');
  const sourceBox = document.getElementById('source-json');
  const targetBox = document.getElementById('target-json');
  const badgeSource = document.getElementById('badge-source');
  const badgeTarget = document.getElementById('badge-target');

  const resolvePanel = document.getElementById('resolve-panel');
  const btnMysql = document.getElementById('resolve-mysql');
  const btnPg = document.getElementById('resolve-postgres');
  const btnMssql = document.getElementById('resolve-mssql');

  function showToast(message, variant = 'primary') {
    const toastEl = document.getElementById('global-toast');
    if (!toastEl) return;
    toastEl.classList.remove('text-bg-primary', 'text-bg-success', 'text-bg-danger', 'text-bg-warning');
    toastEl.classList.add(`text-bg-${variant}`);
    const body = toastEl.querySelector('.toast-body');
    if (body) body.textContent = message;
    bootstrap.Toast.getOrCreateInstance(toastEl).show();
  }

  function showStatus(msg, kind = 'info') {
    if (!statusBox) return;
    statusBox.className = `alert alert-${kind}`;
    statusBox.textContent = msg;
    statusBox.classList.remove('d-none');
  }

  function clearStatus() {
    statusBox?.classList.add('d-none');
  }

  function pretty(obj) {
    try {
      return JSON.stringify(obj, null, 2);
    } catch {
      return String(obj);
    }
  }

  async function fetchConflict() {
    if (!conflictId) {
      showStatus('缺少 conflict_id', 'danger');
      return null;
    }

    const params = new URLSearchParams(window.location.search);
    const tokenParam = params.get('t') || tokenFromTemplate;

    // Prefer email token-based read-only view.
    if (tokenParam) {
      showStatus('正在通过邮件 token 拉取冲突详情…', 'secondary');
      const res = await fetch(`/conflicts/${conflictId}/public?t=${encodeURIComponent(tokenParam)}`, {
        headers: { Accept: 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '拉取失败');
      return { data, mode: 'public' };
    }

    // Otherwise require admin bearer token.
    const bearer = localStorage.getItem('sync_admin_token');
    if (!bearer) {
      window.location.href = `/ui/login?next=${encodeURIComponent(window.location.pathname)}`;
      return null;
    }
    showStatus('正在拉取冲突详情…', 'secondary');
    const res = await fetch(`/conflicts/${conflictId}`, {
      headers: { Accept: 'application/json', Authorization: bearer },
    });
    const data = await res.json();
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('sync_admin_token');
        window.location.href = `/ui/login?next=${encodeURIComponent(window.location.pathname)}`;
        return null;
      }
      throw new Error(data.detail || '拉取失败');
    }
    return { data, mode: 'admin' };
  }

  function renderConflict(conflict) {
    const src = conflict.source_row_data || {};
    const tgt = conflict.target_row_data || {};

    if (badgeSource) badgeSource.textContent = (conflict.source_db || '-').toUpperCase();
    if (badgeTarget) badgeTarget.textContent = (conflict.target_db || '-').toUpperCase();
    if (sourceBox) sourceBox.textContent = pretty(src);
    if (targetBox) targetBox.textContent = pretty(tgt);
  }

  async function resolveConflict(winnerDb) {
    const bearer = localStorage.getItem('sync_admin_token');
    if (!bearer) {
      showToast('需要管理员登录后才能处理冲突', 'warning');
      window.location.href = `/ui/login?next=${encodeURIComponent(window.location.pathname)}`;
      return;
    }

    showStatus(`正在处理冲突：以 ${winnerDb.toUpperCase()} 为准…`, 'secondary');
    const res = await fetch(`/conflicts/${conflictId}/resolve?winner_db=${encodeURIComponent(winnerDb)}`, {
      method: 'POST',
      headers: { Accept: 'application/json', Authorization: bearer },
    });
    const data = await res.json();
    if (!res.ok) {
      showStatus(data.detail || '处理失败', 'danger');
      return;
    }
    showToast('冲突已处理并同步到三库', 'success');
    clearStatus();
    await init(); // refresh
  }

  async function init() {
    try {
      const result = await fetchConflict();
      if (!result) return;
      renderConflict(result.data);

      // Show resolve actions only when admin token exists and conflict is OPEN.
      const bearer = localStorage.getItem('sync_admin_token');
      const canResolve = !!bearer && (String(result.data.status || '').toUpperCase() === 'OPEN');
      if (resolvePanel) resolvePanel.classList.toggle('d-none', !canResolve);
      clearStatus();
    } catch (err) {
      showStatus(err.message || '加载失败', 'danger');
    }
  }

  btnMysql?.addEventListener('click', () => resolveConflict('mysql'));
  btnPg?.addEventListener('click', () => resolveConflict('postgres'));
  btnMssql?.addEventListener('click', () => resolveConflict('mssql'));

  init();
})();

