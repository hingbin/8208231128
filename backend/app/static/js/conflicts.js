(() => {
  const statusBox = document.getElementById('conflicts-status');
  const tbody = document.getElementById('conflicts-body');

  function showStatus(msg, kind = 'info') {
    if (!statusBox) return;
    statusBox.className = `alert alert-${kind}`;
    statusBox.textContent = msg;
    statusBox.classList.remove('d-none');
  }

  function clearStatus() {
    statusBox?.classList.add('d-none');
  }

  function fmtTime(value) {
    if (!value) return '-';
    try {
      return new Date(value).toLocaleString();
    } catch {
      return String(value);
    }
  }

  function renderRows(rows) {
    tbody.innerHTML = '';
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-muted text-center py-4">暂无 OPEN 冲突</td></tr>';
      return;
    }
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="fw-semibold">#${row.conflict_id}</td>
        <td>${row.table_name || '-'}</td>
        <td class="text-muted small">${row.pk_value || '-'}</td>
        <td><span class="badge text-bg-light">${row.source_db || '-'}</span></td>
        <td><span class="badge text-bg-light">${row.target_db || '-'}</span></td>
        <td><span class="badge ${row.status === 'OPEN' ? 'text-bg-warning' : 'text-bg-success'}">${row.status || '-'}</span></td>
        <td class="small text-muted">${fmtTime(row.created_at)}</td>
        <td><a class="btn btn-sm btn-outline-secondary" href="/ui/conflicts/${row.conflict_id}">查看</a></td>
      `;
      tbody.appendChild(tr);
    });
  }

  async function loadConflicts() {
    const bearer = localStorage.getItem('sync_admin_token');
    if (!bearer) {
      window.location.href = '/ui/login?next=/ui/conflicts';
      return;
    }
    showStatus('正在加载冲突列表…', 'secondary');
    try {
      const res = await fetch('/conflicts?status=OPEN', {
        headers: { Accept: 'application/json', Authorization: bearer },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '加载失败');
      renderRows(data || []);
      clearStatus();
    } catch (err) {
      showStatus(err.message || '加载失败', 'danger');
    }
  }

  loadConflicts();
})();

