(() => {
  const token = localStorage.getItem('sync_admin_token');
  if (!token) {
    window.location.href = '/ui/login';
    return;
  }

  const headers = {
    Accept: 'application/json',
    Authorization: token,
  };

  const summaryContainer = document.getElementById('db-summary');
  const productTable = document.getElementById('product-matrix');
  const conflictList = document.getElementById('conflict-list');
  const conflictSummary = document.getElementById('conflict-summary');
  const conflictAlert = document.getElementById('conflict-alert');
  const conflictAlertText = document.getElementById('conflict-alert-text');
  const overviewStatus = document.getElementById('overview-status');
  const overviewTime = document.getElementById('overview-time');
  const reportMini = document.getElementById('report-mini');
  const manualModalEl = document.getElementById('manualModal');
  const manualPayload = document.getElementById('manualPayload');
  const manualConflictId = document.getElementById('manualConflictId');
  const manualSubmit = document.getElementById('manualSubmit');
  const dailyChartCanvas = document.getElementById('daily-chart');
  const dailyChartEmpty = document.getElementById('daily-chart-empty');
  const tableChartCanvas = document.getElementById('table-chart');
  const tableChartEmpty = document.getElementById('table-chart-empty');
  const tableVolumeGrid = document.getElementById('table-volume-grid');
  const manualModal = manualModalEl ? bootstrap.Modal.getOrCreateInstance(manualModalEl) : null;

  const DB_ORDER = ['mysql', 'postgres', 'mssql'];
  let lastConflictCount = 0;
  let dailyChart = null;
  let tableChart = null;
  const TABLE_COLOR_PALETTE = ['#0d6efd', '#20c997', '#e83e8c', '#ffc107', '#198754', '#6f42c1', '#0dcaf0'];
  const TABLE_VOLUME_KEYS = ['users', 'customers', 'products', 'orders', 'order_items', 'change_log', 'conflicts'];
  const TABLE_LABEL_MAP = {
    users: '用户',
    customers: '客户',
    products: '商品',
    orders: '订单',
    order_items: '订单明细',
    change_log: '变更日志',
    conflicts: '冲突',
  };

  function showToast(message, variant = 'primary') {
    const toastEl = document.getElementById('global-toast');
    if (!toastEl) return;
    toastEl.className = `toast text-bg-${variant} border-0`;
    const body = toastEl.querySelector('.toast-body');
    if (body) body.textContent = message;
    bootstrap.Toast.getOrCreateInstance(toastEl).show();
  }

  function renderDbSummary(stats) {
    if (!summaryContainer) return;
    summaryContainer.innerHTML = '';
    Object.entries(stats).forEach(([db, values]) => {
      const col = document.createElement('div');
      col.className = 'col-md-6';
      col.innerHTML = `
        <div class="summary-stat h-100">
          <h6>${db.toUpperCase()}</h6>
          <div class="value">${values.products}</div>
          <div class="text-muted small">订单：${values.orders} · 客户：${values.customers}</div>
          <div class="text-muted small">用户：${values.users}</div>
          <div class="text-muted small">待同步：${values.pending_changes}</div>
          <div class="text-muted small">最近更新：${values.last_product_update ? new Date(values.last_product_update).toLocaleString() : '—'}</div>
        </div>
      `;
      summaryContainer.appendChild(col);
    });
  }

  function renderProductMatrix(matrix) {
    if (!productTable) return;
    if (!matrix.length) {
      productTable.innerHTML = '<tr><td colspan="4" class="text-muted">暂无数据，请先写入商品再刷新。</td></tr>';
      return;
    }
    productTable.innerHTML = '';
    matrix.forEach((item) => {
      const tr = document.createElement('tr');
      if (item.has_diff) tr.classList.add('different');
      const cells = DB_ORDER.map((dbKey) => {
        const detail = item.per_db[dbKey];
        if (!detail) return '<span class="text-muted">—</span>';
        const price = detail.price != null ? detail.price.toFixed(2) : '—';
        const stock = detail.stock != null ? detail.stock : '—';
        const rv = detail.row_version != null ? detail.row_version : '—';
        const dbTag = detail.updated_by_db || dbKey.toUpperCase();
        return `
          <div class="fw-semibold">¥ ${price}</div>
          <div class="text-muted small">库存 ${stock}</div>
          <div class="text-muted small">v${rv} · ${dbTag}</div>
        `;
      });
      tr.innerHTML = `
        <td class="text-start">
          <div class="fw-semibold">${item.product_name}</div>
          <div class="text-muted small">ID: ${item.product_id}</div>
        </td>
        <td>${cells[0]}</td>
        <td>${cells[1]}</td>
        <td>${cells[2]}</td>
      `;
      productTable.appendChild(tr);
    });
  }

  function renderConflictSummary(conflicts) {
    if (!conflictSummary) return;
    conflictSummary.innerHTML = '';
    if (!conflicts.items.length) {
      conflictSummary.innerHTML = '<span class="text-muted">当前没有待处理冲突。</span>';
      return;
    }
    conflicts.items.forEach((item) => {
      const div = document.createElement('div');
      div.className = 'conflict-card';
      div.innerHTML = `
        <div class="d-flex justify-content-between">
          <div>
            <div class="fw-semibold">#${item.conflict_id} · ${item.table_name}</div>
            <div class="text-muted small">主键：${item.pk_value}</div>
            <div class="text-muted small">来源：${item.source_db} → ${item.target_db}</div>
            <div class="text-muted small">时间：${item.created_at ? new Date(item.created_at).toLocaleString() : '—'}</div>
          </div>
          <span class="badge bg-danger">待处理</span>
        </div>
        <div class="conflict-actions d-flex flex-wrap gap-2 mt-3">
          <button class="btn btn-sm btn-outline-primary" data-action="resolve" data-db="mysql" data-id="${item.conflict_id}">采用 MySQL</button>
          <button class="btn btn-sm btn-outline-primary" data-action="resolve" data-db="postgres" data-id="${item.conflict_id}">采用 PostgreSQL</button>
          <button class="btn btn-sm btn-outline-primary" data-action="resolve" data-db="mssql" data-id="${item.conflict_id}">采用 SQL Server</button>
          <button class="btn btn-sm btn-warning" data-action="manual" data-id="${item.conflict_id}">手动修复</button>
        </div>
      `;
      conflictSummary.appendChild(div);
    });
  }

  function renderConflictList(conflicts) {
    if (!conflictList) return;
    conflictList.innerHTML = conflictSummary.innerHTML;
  }

  function renderReportMini(report) {
    if (!reportMini) return;
    if (!report.changes || !report.changes.length) {
      reportMini.innerHTML = '<span class="text-muted">暂无统计数据。</span>';
      return;
    }
    const list = document.createElement('ul');
    list.className = 'list-unstyled mb-0';
    const conflictMap = new Map((report.conflicts || []).map((c) => [c.d, c.conflicts]));
    (report.changes || []).slice(0, 5).forEach((row) => {
      const li = document.createElement('li');
      li.className = 'd-flex justify-content-between small py-1 border-bottom';
      li.innerHTML = `
        <span>${row.d}</span>
        <span>变更 ${row.changes} · 冲突 ${conflictMap.get(row.d) || 0}</span>
      `;
      list.appendChild(li);
    });
    reportMini.innerHTML = '';
    reportMini.appendChild(list);
  }

  function renderDailyChart(report) {
    if (!dailyChartCanvas) return;
    const map = new Map();
    (report.changes || []).forEach((r) => {
      const d = (r.d || r.D || '').toString();
      if (!d) return;
      map.set(d, { changes: Number(r.changes || 0), conflicts: 0 });
    });
    (report.conflicts || []).forEach((r) => {
      const d = (r.d || r.D || '').toString();
      if (!d) return;
      if (!map.has(d)) map.set(d, { changes: 0, conflicts: 0 });
      map.get(d).conflicts = Number(r.conflicts || 0);
    });
    const labels = Array.from(map.keys()).sort();
    const changes = labels.map((d) => map.get(d).changes);
    const conflicts = labels.map((d) => map.get(d).conflicts);

    if (!labels.length) {
      dailyChartEmpty?.classList.remove('d-none');
      if (dailyChart) {
        dailyChart.destroy();
        dailyChart = null;
      }
      return;
    }
    dailyChartEmpty?.classList.add('d-none');

    const data = {
      labels,
      datasets: [
        { label: '同步变更', data: changes, tension: 0.2, borderColor: '#0d6efd', backgroundColor: 'rgba(13,110,253,0.15)' },
        { label: '冲突', data: conflicts, tension: 0.2, borderColor: '#dc3545', backgroundColor: 'rgba(220,53,69,0.15)' },
      ],
    };
    const options = {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom' } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
    };
    if (dailyChart) {
      dailyChart.data = data;
      dailyChart.options = options;
      dailyChart.update();
    } else {
      dailyChart = new Chart(dailyChartCanvas, { type: 'line', data, options });
    }
  }

  function renderTableGrid(volume) {
    if (!tableVolumeGrid) return;
    if (!volume || !Object.keys(volume).length) {
      tableVolumeGrid.innerHTML = '<div class="text-muted small">暂无数据。</div>';
      return;
    }
    tableVolumeGrid.innerHTML = '';
    TABLE_VOLUME_KEYS.forEach((key) => {
      const label = TABLE_LABEL_MAP[key] || key;
      const value = Number(volume[key] || 0).toLocaleString();
      const col = document.createElement('div');
      col.innerHTML = `
        <div class="p-2 border rounded-3 bg-light-subtle text-center">
          <div class="small text-muted">${label}</div>
          <div class="fw-semibold">${value}</div>
        </div>
      `;
      tableVolumeGrid.appendChild(col);
    });
  }

  function renderTableChart(report) {
    if (!tableChartCanvas) return;
    const volume = report?.table_volume;
    if (!volume || !Object.keys(volume).length) {
      tableChartEmpty?.classList.remove('d-none');
      if (tableChart) {
        tableChart.destroy();
        tableChart = null;
      }
      renderTableGrid(null);
      return;
    }

    const labels = TABLE_VOLUME_KEYS.map((key) => TABLE_LABEL_MAP[key] || key);
    const data = TABLE_VOLUME_KEYS.map((key) => Number(volume[key] || 0));
    const colors = TABLE_VOLUME_KEYS.map((_, idx) => TABLE_COLOR_PALETTE[idx % TABLE_COLOR_PALETTE.length]);

    tableChartEmpty?.classList.add('d-none');
    const barDataset = {
      label: '记录条数',
      data,
      backgroundColor: colors,
      borderColor: colors,
      borderWidth: 1,
    };
    const config = {
      type: 'bar',
      data: { labels, datasets: [barDataset] },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
          x: { ticks: { autoSkip: false } },
        },
      },
    };
    if (tableChart) {
      tableChart.data = config.data;
      tableChart.options = config.options;
      tableChart.update();
    } else {
      tableChart = new Chart(tableChartCanvas, config);
    }
    renderTableGrid(volume);
  }

  async function fetchDailyReport() {
    try {
      const res = await fetch('/report/daily?days=14', { headers });
      if (!res.ok) throw new Error('无法加载日报');
      const data = await res.json();
      renderReportMini(data || {});
      renderDailyChart(data || {});
      renderTableChart(data || {});
    } catch (error) {
      showToast(error.message || '日报加载失败', 'danger');
    }
  }

  async function fetchOverview() {
    try {
      const res = await fetch('/dashboard/overview?limit=8', { headers });
      if (!res.ok) throw new Error('无法加载概览');
      const data = await res.json();
      renderDbSummary(data.db_stats || {});
      renderProductMatrix(data.product_matrix || []);
      renderConflictSummary(data.conflicts || { items: [] });
      renderConflictList(data.conflicts || { items: [] });
      if (overviewTime) overviewTime.textContent = `更新于 ${new Date(data.generated_at).toLocaleString()}`;

      const openCount = data.conflicts?.open_count || 0;
      const pending = data.pending_changes_total || 0;
      if (openCount > 0) {
        overviewStatus.className = 'status-pill danger';
        overviewStatus.textContent = `${openCount} 条冲突`;
      } else if (pending > 0) {
        overviewStatus.className = 'status-pill warn';
        overviewStatus.textContent = `${pending} 条待同步`;
      } else {
        overviewStatus.className = 'status-pill ok';
        overviewStatus.textContent = '同步正常';
      }

      if (conflictAlert && conflictAlertText) {
        if (openCount > 0) {
          conflictAlert.classList.remove('d-none');
          conflictAlertText.textContent = `检测到 ${openCount} 条冲突，请及时处理。`;
        } else {
          conflictAlert.classList.add('d-none');
        }
      }

      if (openCount > lastConflictCount) {
        showToast(`新增 ${openCount - lastConflictCount} 条冲突，请处理`, 'warning');
      }
      lastConflictCount = openCount;
    } catch (error) {
      showToast(error.message || '概览加载失败', 'danger');
    }
  }

  async function resolveConflict(conflictId, winnerDb) {
    try {
      const res = await fetch(`/conflicts/${conflictId}/resolve?winner_db=${winnerDb}`, {
        method: 'POST',
        headers,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '处理失败');
      showToast(`冲突 #${conflictId} 已采用 ${winnerDb.toUpperCase()} 数据`, 'success');
      fetchOverview();
    } catch (error) {
      showToast(error.message || '处理失败', 'danger');
    }
  }

  async function openManualModal(conflictId) {
    try {
      const res = await fetch(`/conflicts/${conflictId}`, { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '加载冲突失败');
      manualConflictId.value = conflictId;
      manualPayload.value = JSON.stringify(data.source_row_data || data.target_row_data || {}, null, 2);
      manualModal?.show();
    } catch (error) {
      showToast(error.message || '无法加载冲突详情', 'danger');
    }
  }

  async function submitManual() {
    const conflictId = manualConflictId.value;
    if (!conflictId) return;
    let payload;
    try {
      payload = JSON.parse(manualPayload.value);
    } catch (error) {
      showToast('JSON 解析失败，请检查格式', 'danger');
      return;
    }

    try {
      const res = await fetch(`/conflicts/${conflictId}/resolve/custom`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '修复失败');
      showToast(`冲突 #${conflictId} 已手动修复`, 'success');
      manualModal?.hide();
      fetchOverview();
    } catch (error) {
      showToast(error.message || '修复失败', 'danger');
    }
  }

  if (conflictList) {
    conflictList.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-action]');
      if (!btn) return;
      const conflictId = btn.dataset.id;
      if (btn.dataset.action === 'resolve') {
        resolveConflict(conflictId, btn.dataset.db);
      } else if (btn.dataset.action === 'manual') {
        openManualModal(conflictId);
      }
    });
  }

  if (manualSubmit) {
    manualSubmit.addEventListener('click', submitManual);
  }

  // Initial load
  fetchOverview();
  fetchDailyReport();
  setInterval(fetchOverview, 8000);
  setInterval(fetchDailyReport, 60000);
})();
