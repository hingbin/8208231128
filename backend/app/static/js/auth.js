(function () {
  const statusBox = document.getElementById('auth-status');
  const tokenBox = document.getElementById('auth-token');
  const tokenPanel = document.getElementById('auth-token-panel');
  const dashBtn = document.getElementById('go-dashboard');
  const params = new URLSearchParams(window.location.search);
  const nextTarget = params.get('next') || '/ui/conflicts';

  function showStatus(message, kind = 'info') {
    if (!statusBox) return;
    statusBox.className = `alert alert-${kind}`;
    statusBox.textContent = message;
    statusBox.removeAttribute('hidden');
  }

  function showToken(token) {
    if (!tokenBox || !tokenPanel) return;
    tokenBox.textContent = token || '';
    tokenPanel.classList.toggle('d-none', !token);
  }

  function storeToken(token) {
    try {
      localStorage.setItem('sync_admin_token', token);
    } catch (error) {
      console.warn('无法写入本地 token', error);
    }
  }

  function bindForm(formId, url, payloadKeys) {
    const form = document.getElementById(formId);
    if (!form) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      const payload = {};
      payloadKeys.forEach((key) => {
        payload[key] = (formData.get(key) || '').trim();
      });

      showStatus('请求处理中，请稍候…', 'secondary');
      showToken('');
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'Accept': 'application/json'},
          body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || '操作失败');
        }
        const bearer = `Bearer ${data.access_token}`;
        showStatus('登录成功，正在跳转…', 'success');
        showToken(bearer);
        storeToken(bearer);
        if (dashBtn) {
          dashBtn.classList.remove('d-none');
        }
        setTimeout(() => window.location.href = nextTarget, 300);
      } catch (error) {
        showToken('');
        showStatus(error.message || '请求失败，请重试', 'danger');
      }
    });
  }

  bindForm('login-form', '/auth/login', ['username', 'password']);
  bindForm('register-form', '/auth/register', ['username', 'password', 'registration_code']);

  if (dashBtn) {
    dashBtn.addEventListener('click', () => {
      window.location.href = '/ui/conflicts';
    });
  }

  async function tryAutoRedirect() {
    const bearer = localStorage.getItem('sync_admin_token');
    if (!bearer) return;
    try {
      const res = await fetch('/me', {headers: {Authorization: bearer}});
      if (!res.ok) throw new Error();
      window.location.href = nextTarget;
    } catch {
      localStorage.removeItem('sync_admin_token');
    }
  }

  tryAutoRedirect();
})();
