export async function api(path, options = {}, csrf = '') {
  const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) };
  if (csrf && options.method && !['GET', 'HEAD'].includes(options.method)) headers['X-CSRF-Token'] = csrf;
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Anfrage fehlgeschlagen (' + response.status + ')');
  }
  return body;
}
