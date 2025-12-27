(() => {
  const token = localStorage.getItem('sync_admin_token');
  if (!token) {
    window.location.href = '/ui/login?next=/ui/data';
    return;
  }

  const headers = {
    Accept: 'application/json',
    Authorization: token,
  };

  const dbSelect = document.getElementById('db-select');
  const refreshBtn = document.getElementById('refresh-btn');
  const tableBody = document.getElementById('data-table');
  const statusBox = document.getElementById('data-status');
  const metaBox = document.getElementById('table-meta');

  const productId = document.getElementById('product-id');
  const productName = document.getElementById('product-name');
  const productPrice = document.getElementById('product-price');
  const productStock = document.getElementById('product-stock');
  const submitBtn = document.getElementById('submit-btn');

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
    if (statusBox) statusBox.classList.add('d-none');
  }

  function renderRows(rows) {
    tableBody.innerHTML = '';
    if (!rows.length) {
      tableBody.innerHTML = '<tr><td colspan="6" class="text-muted text-center">暂无数据，先写入一条试试看。</td></tr>';
      return;
    }
    rows.slice(0, 30).forEach((row, idx) => {
      const tr = document.createElement('tr');
      tr.dataset.id = row.product_id || row.id || '';
      tr.dataset.name = row.product_name || row.name || '';
      tr.dataset.price = row.price ?? '';
      tr.dataset.stock = row.stock ?? '';
      tr.innerHTML = `
        <td>${idx + 1}</td>
        <td>
          <div class="fw-semibold">${row.product_name || row.name || '-'}</div>
          <div class="text-muted small">${row.product_id || row.id || ''}</div>
        </td>
        <td>¥ ${row.price !== null && row.price !== undefined ? Number(row.price).toFixed(2) : '-'}</td>
        <td>${row.stock ?? '-'}</td>
        <td>
          <div class="small mb-1">v${row.row_version || 1}</div>
          <span class="badge text-bg-light">${row.updated_by_db || '-'}</span>
        </td>
        <td class="small text-muted">${row.updated_at ? new Date(row.updated_at).toLocaleString() : '-'}</td>
      `;
      tableBody.appendChild(tr);
    });
  }

  async function loadProducts() {
    const db = dbSelect.value;
    showStatus(`正在加载 ${db.toUpperCase()} 数据…`, 'secondary');
    try {
      const res = await fetch(`/products?db=${db}`, { headers });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '拉取失败');
      renderRows(data || []);
      metaBox.textContent = `${db.toUpperCase()} · ${data.length} 条记录`;
      clearStatus();
    } catch (error) {
      showStatus(error.message || '加载失败', 'danger');
    }
  }

  async function saveProduct() {
    const db = dbSelect.value;
    const payload = {
      product_id: (productId.value || '').trim() || null,
      product_name: (productName.value || '').trim(),
      price: Number(productPrice.value || 0),
      stock: Number(productStock.value || 0),
    };

    if (!payload.product_name) {
      showStatus('商品名称不能为空', 'warning');
      return;
    }

    if (Number.isNaN(payload.price)) {
      showStatus('价格格式不正确', 'warning');
      return;
    }

    if (Number.isNaN(payload.stock) || payload.stock < 0) {
      showStatus('库存需为非负整数', 'warning');
      return;
    }

    payload.stock = Math.trunc(payload.stock);

    showStatus('提交中，请稍候…', 'secondary');
    try {
      const res = await fetch(`/products?db=${db}`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || '保存失败');
      productId.value = data.product_id || data.id || payload.product_id || '';
      showToast(`已写入 ${db.toUpperCase()}，同步引擎会推送到其它数据库。`, 'success');
      clearStatus();
      await loadProducts();
    } catch (error) {
      showStatus(error.message || '保存失败', 'danger');
    }
  }

  function bindRowClick() {
    tableBody.addEventListener('click', (event) => {
      const tr = event.target.closest('tr');
      if (!tr || !tr.dataset.id) return;
      productId.value = tr.dataset.id;
      productName.value = tr.dataset.name;
      productPrice.value = tr.dataset.price ?? '';
      productStock.value = tr.dataset.stock ?? '';
      showStatus('已填充到表单，可直接更新或切换到其它库同步。', 'info');
    });
  }

  function init() {
    dbSelect?.addEventListener('change', loadProducts);
    refreshBtn?.addEventListener('click', loadProducts);
    submitBtn?.addEventListener('click', saveProduct);
    bindRowClick();
    loadProducts();
  }

  init();
})();
