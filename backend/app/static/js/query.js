(() => {
  const token = localStorage.getItem('sync_admin_token');
  const nextPath = encodeURIComponent(window.location.pathname + window.location.search);
  if (!token) {
    window.location.href = `/ui/login?next=${nextPath}`;
    return;
  }

  const headers = {
    Accept: 'application/json',
    Authorization: token,
  };

  const topForm = document.getElementById('query-form');
  const statusBox = document.getElementById('query-status');
  const tableBody = document.getElementById('query-body');
  const sqlBox = document.getElementById('query-sql');
  const metaBadge = document.getElementById('query-meta');
  const highlightsBox = document.getElementById('query-highlights');

  const sqlForm = document.getElementById('sql-form');
  const sqlDbSelect = document.getElementById('sql-db');
  const sqlLimitInput = document.getElementById('sql-limit');
  const sqlInput = document.getElementById('sql-input');
  const sqlStatusBox = document.getElementById('sql-status');
  const sqlResultMeta = document.getElementById('sql-result-meta');
  const sqlResultHead = document.getElementById('sql-result-head');
  const sqlResultBody = document.getElementById('sql-result-body');
  const sqlFillBtn = document.getElementById('sql-fill-sample');

  function showStatus(message, kind = 'info') {
    if (!statusBox) return;
    statusBox.textContent = message;
    statusBox.className = `alert alert-${kind} mt-3`;
    statusBox.classList.remove('d-none');
  }

  function clearStatus() {
    statusBox?.classList.add('d-none');
  }

  function formatAmount(value) {
    if (value === null || value === undefined) return '-';
    const num = Number(value);
    if (Number.isNaN(num)) return '-';
    return `¥ ${num.toFixed(2)}`;
  }

  function renderRows(rows = []) {
    if (!tableBody) return;
    if (!rows.length) {
      tableBody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">暂无满足条件的订单</td></tr>';
      return;
    }
    tableBody.innerHTML = rows.map((row, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td>
          <div class="fw-semibold">${row.customer_name || '-'}</div>
          <div class="text-muted small">${row.customer_id || ''}</div>
        </td>
        <td>${formatAmount(row.total_amount)}</td>
      </tr>
    `).join('');
  }

  function updateMeta(db = '', count = 0) {
    if (!metaBadge) return;
    const label = db ? db.toUpperCase() : 'DB';
    metaBadge.textContent = `${label} · ${count} 条`;
  }

  function updateSql(sql = '') {
    if (!sqlBox) return;
    sqlBox.textContent = sql.trim();
  }

  function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function renderHighlights(rows = []) {
    if (!highlightsBox) return;
    if (!rows.length) {
      highlightsBox.innerHTML = '<span class="badge text-bg-light">暂无结果，尝试调整参数</span>';
      return;
    }
    const topRows = rows.slice(0, 3);
    highlightsBox.innerHTML = topRows.map((row, index) => {
      const badgeClass = index === 0 ? 'text-bg-primary' : 'text-bg-secondary';
      return `
        <span class="badge ${badgeClass}">
          #${index + 1} · ${row.customer_name || '-'} · ${formatAmount(row.total_amount)}
        </span>
      `;
    }).join('');
  }

  function updateUrl(params) {
    const newUrl = `${window.location.pathname}?${params}`;
    window.history.replaceState({}, '', newUrl);
  }

  function redirectToLogin() {
    localStorage.removeItem('sync_admin_token');
    window.location.href = `/ui/login?next=${nextPath}`;
  }

  function showSqlStatus(message, kind = 'info') {
    if (!sqlStatusBox) return;
    sqlStatusBox.textContent = message;
    sqlStatusBox.className = `alert alert-${kind}`;
    sqlStatusBox.classList.remove('d-none');
  }

  function clearSqlStatus() {
    sqlStatusBox?.classList.add('d-none');
  }

  function updateSqlMeta(data) {
    if (!sqlResultMeta) return;
    if (!data) {
      sqlResultMeta.textContent = '尚未执行';
      return;
    }
    const dbLabel = data.db ? data.db.toUpperCase() : 'DB';
    const took = typeof data.took_ms === 'number' ? ` · ${data.took_ms} ms` : '';
    const truncated = data.truncated ? ' · 已截断' : '';
    sqlResultMeta.textContent = `${dbLabel} · ${data.row_count || 0} 行${took}${truncated}`;
  }

  function renderSqlTable(columns = [], rows = []) {
    if (!sqlResultHead || !sqlResultBody) return;
    if (!columns.length) {
      sqlResultHead.innerHTML = '<tr><th>列名</th></tr>';
    } else {
      sqlResultHead.innerHTML = `<tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join('')}</tr>`;
    }
    if (!rows.length) {
      const colspan = Math.max(columns.length, 1);
      sqlResultBody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted">暂无数据</td></tr>`;
      return;
    }
    sqlResultBody.innerHTML = rows.map((row) => {
      const cells = columns.map((col) => {
        const value = row[col];
        if (value === null || value === undefined) {
          return '<td><span class="text-muted">NULL</span></td>';
        }
        if (typeof value === 'object') {
          return `<td><code>${escapeHtml(JSON.stringify(value))}</code></td>`;
        }
        return `<td>${escapeHtml(value)}</td>`;
      }).join('');
      return `<tr>${cells}</tr>`;
    }).join('');
  }

  async function runQuery(event) {
    event?.preventDefault?.();
    if (!topForm) return;
    const formData = new FormData(topForm);
    const db = formData.get('db') || 'mysql';
    const days = formData.get('days') || '30';
    const limit = formData.get('limit') || '10';
    const params = new URLSearchParams({ db, days, limit });

    updateUrl(params.toString());
    showStatus('查询执行中，请稍候...', 'secondary');
    if (highlightsBox) {
      highlightsBox.innerHTML = '<span class="badge text-bg-light">查询执行中...</span>';
    }

    try {
      const res = await fetch(`/queries/top-customers?${params}`, { headers });
      const data = await res.json();
      if (res.status === 401) {
        redirectToLogin();
        return;
      }
      if (!res.ok) {
        throw new Error(data.detail || '查询失败');
      }
      renderRows(data.rows || []);
      updateMeta(data.db, (data.rows || []).length);
      updateSql(data.sql || '');
      renderHighlights(data.rows || []);
      showStatus(`已获取 ${data.db?.toUpperCase() || ''} 的最新结果`, 'success');
      setTimeout(clearStatus, 1500);
    } catch (error) {
      showStatus(error.message || '查询失败，请稍后重试', 'danger');
      if (highlightsBox) {
        highlightsBox.innerHTML = '<span class="badge text-bg-danger">查询失败</span>';
      }
    }
  }

  async function runSql(event) {
    event?.preventDefault?.();
    if (!sqlForm) return;
    const db = sqlDbSelect?.value || 'mysql';
    const limit = Math.min(Math.max(Number(sqlLimitInput?.value) || 200, 1), 1000);
    const sqlText = (sqlInput?.value || '').trim();
    if (!sqlText) {
      showSqlStatus('SQL 不能为空', 'warning');
      return;
    }
    showSqlStatus('SQL 执行中，请稍候...', 'secondary');
    updateSqlMeta(null);
    renderSqlTable([], []);
    try {
      const res = await fetch('/queries/run', {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ db, sql: sqlText, limit }),
      });
      const data = await res.json();
      if (res.status === 401) {
        redirectToLogin();
        return;
      }
      if (!res.ok) {
        throw new Error(data.detail || 'SQL 执行失败');
      }
      renderSqlTable(data.columns || [], data.rows || []);
      updateSqlMeta(data);
      showSqlStatus(`执行成功：${data.row_count || 0} 行`, 'success');
      setTimeout(clearSqlStatus, 1500);
    } catch (error) {
      showSqlStatus(error.message || 'SQL 执行失败', 'danger');
    }
  }

  sqlForm?.addEventListener('submit', runSql);
  sqlFillBtn?.addEventListener('click', () => {
    if (!sqlInput) return;
    sqlInput.value = sqlInput.defaultValue || '';
  });

  topForm?.addEventListener('submit', runQuery);
  if (topForm) {
    runQuery();
  }
})();
