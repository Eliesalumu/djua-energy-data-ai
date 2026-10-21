const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../apps/api/static/api-client.js'), 'utf8');

function client(fetch, base = 'https://backend.example') {
  const context = { URL, AbortController, setTimeout, clearTimeout, fetch, DJUA_API_BASE_URL: base, location: { origin: 'https://frontend.example' } };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.DjuaApi;
}

for (const status of [401, 503]) {
  test(`HTTP ${status}: one attempt, rejected before any success handling`, async () => {
    let calls = 0;
    const api = client(async () => { calls++; return { ok: false, status, text: async () => '<html>Proxy error</html>' }; });
    let success = false;
    await assert.rejects(async () => { await api.chat('Bonjour'); success = true; }, error => error.name === 'ApiError' && error.status === status);
    assert.equal(calls, 1);
    assert.equal(success, false);
  });
}

for (const body of ['', 'null', '{}', '[]', '<html>Not JSON</html>', '{"answer":""}']) {
  test(`invalid response: ${JSON.stringify(body)}`, async () => {
    const api = client(async () => ({ ok: true, status: 200, text: async () => body }));
    await assert.rejects(() => api.chat('Bonjour'), error => error.name === 'ApiError');
  });
}

test('valid fallback uses the configured backend and preserves warning', async () => {
  let target;
  const api = client(async url => { target = url; return { ok: true, status: 200, text: async () => JSON.stringify({ ok: true, answer: 'Etat local', used_llm: false, warning: { code: 'AI_NOT_CONFIGURED' } }) }; });
  const result = await api.chat('Bonjour');
  assert.equal(target, 'https://backend.example/ai/chat');
  assert.equal(result.warning.code, 'AI_NOT_CONFIGURED');
});

test('timeout and invalid configuration remain explicit errors', async () => {
  const api = client(async (url, options) => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject({ name: 'AbortError' }))));
  await assert.rejects(() => api.request('/ai/chat', { timeoutMs: 5 }), error => error.code === 'API_TIMEOUT');
  await assert.rejects(() => client(async () => {}, 'not a URL').chat('Bonjour'), error => error.code === 'API_CONFIGURATION_ERROR');
});
