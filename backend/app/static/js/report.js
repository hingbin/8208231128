(async function () {
  const token = localStorage.getItem('sync_admin_token');
  if (!token) {
    window.location.href = '/ui/login';
    return;
  }

  const summaryCanvas = document.getElementById('chart');
  const summaryMeta = document.getElementById('chart-meta');
  const tableCanvas = document.getElementById('table-chart-full');
  const tableEmpty = document.getElementById('table-chart-empty');
  const tableVolumeGrid = document.getElementById('table-volume-grid');
  const SUMMARY_EMPTY_ID = 'chart-empty-helper';
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
  let summaryChart = null;
  let tableTrendChart = null;

  function showSummaryEmpty(message) {
    if (!summaryCanvas) return;
    let helper = document.getElementById(SUMMARY_EMPTY_ID);
    if (!helper) {
      summaryCanvas.insertAdjacentHTML('afterend', `<div id="${SUMMARY_EMPTY_ID}" class="text-muted mt-2">${message}</div>`);
    } else {
      helper.textContent = message;
    }
  }

  function clearSummaryEmpty() {
    const helper = document.getElementById(SUMMARY_EMPTY_ID);
    if (helper) helper.remove();
  }

  function renderSummaryChart(payload) {
    if (!summaryCanvas) return;
    const map = new Map();
    (payload.changes || []).forEach((row) => {
      const d = (row.d || row.D || '').toString();
      if (!d) return;
      if (!map.has(d)) map.set(d, { changes: 0, conflicts: 0 });
      map.get(d).changes = Number(row.changes || 0);
    });
    (payload.conflicts || []).forEach((row) => {
      const d = (row.d || row.D || '').toString();
      if (!d) return;
      if (!map.has(d)) map.set(d, { changes: 0, conflicts: 0 });
      map.get(d).conflicts = Number(row.conflicts || 0);
    });

    const labels = Array.from(map.keys()).sort();
    if (summaryMeta) {
      summaryMeta.textContent = labels.length ? `最新日期：${labels[labels.length - 1]}` : '暂无数据';
    }

    if (!labels.length) {
      if (summaryChart) {
        summaryChart.destroy();
        summaryChart = null;
      }
      showSummaryEmpty('暂无数据，请先产生同步或冲突记录。');
      return;
    }

    clearSummaryEmpty();
    const changes = labels.map((d) => map.get(d).changes);
    const conflicts = labels.map((d) => map.get(d).conflicts);
    const chartData = {
      labels,
      datasets: [
        { label: '同步变更', data: changes, tension: 0.2, borderColor: '#4f46e5', backgroundColor: 'rgba(79,70,229,0.1)', fill: true },
        { label: '冲突', data: conflicts, tension: 0.2, borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,0.12)', fill: true },
      ],
    };
    const chartOptions = {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom' } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
    };

    if (summaryChart) {
      summaryChart.data = chartData;
      summaryChart.options = chartOptions;
      summaryChart.update();
    } else {
      summaryChart = new Chart(summaryCanvas, { type: 'line', data: chartData, options: chartOptions });
    }
  }

  function renderTableVolumeGrid(volume) {
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

  function renderTableVolume(volume) {
    if (!tableCanvas) return;
    if (!volume || !Object.keys(volume).length) {
      if (tableEmpty) {
        tableEmpty.classList.remove('d-none');
        tableEmpty.textContent = '暂无数据，请先触发一次同步。';
      }
      if (tableTrendChart) {
        tableTrendChart.destroy();
        tableTrendChart = null;
      }
      renderTableVolumeGrid(null);
      return;
    }

    const labels = TABLE_VOLUME_KEYS.map((key) => TABLE_LABEL_MAP[key] || key);
    const data = TABLE_VOLUME_KEYS.map((key) => Number(volume[key] || 0));
    const colors = TABLE_VOLUME_KEYS.map((_, idx) => TABLE_COLOR_PALETTE[idx % TABLE_COLOR_PALETTE.length]);

    if (tableEmpty) {
      tableEmpty.classList.add('d-none');
    }

    const config = {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: '记录条数',
          data,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
          x: { ticks: { autoSkip: false } },
        },
      },
    };

    if (tableTrendChart) {
      tableTrendChart.data = config.data;
      tableTrendChart.options = config.options;
      tableTrendChart.update();
    } else {
      tableTrendChart = new Chart(tableCanvas, config);
    }
    renderTableVolumeGrid(volume);
  }

  try {
    const res = await fetch('/report/daily?days=14', {
      headers: {
        accept: 'application/json',
        Authorization: token,
      },
    });

    if (!res.ok) {
      showSummaryEmpty('加载失败，请确认已登录且 worker 正在运行。');
      if (tableEmpty) {
        tableEmpty.classList.remove('d-none');
        tableEmpty.textContent = '表级数据加载失败，请稍后重试。';
      }
      return;
    }

    const payload = await res.json();
    renderSummaryChart(payload || {});
    renderTableVolume(payload?.table_volume || {});
  } catch (error) {
    showSummaryEmpty(error?.message || '加载失败，请稍后重试。');
    if (tableEmpty) {
      tableEmpty.classList.remove('d-none');
      tableEmpty.textContent = '表级数据加载失败，请稍后重试。';
    }
  }
})();
