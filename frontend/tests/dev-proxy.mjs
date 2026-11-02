import assert from 'node:assert/strict';
import { createServer as createBackend } from 'node:http';
import { once } from 'node:events';
import { after, before, test } from 'node:test';
import { createServer, loadConfigFromFile } from 'vite';

let backend;
let vite;
let origin;

before(async () => {
  backend = createBackend((request, response) => {
    response.setHeader('Content-Type', 'application/json');
    response.end(JSON.stringify({ path: request.url, method: request.method, csrf: request.headers['x-csrf-token'] ?? null }));
  });
  backend.listen(0, '127.0.0.1');
  await once(backend, 'listening');
  const target = `http://127.0.0.1:${backend.address().port}`;
  // Vite treats port 0 as its default, so reserve an actual ephemeral port.
  const reservation = createBackend();
  reservation.listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise((resolve, reject) => reservation.close(error => error ? reject(error) : resolve()));
  const loaded = await loadConfigFromFile({ command: 'serve', mode: 'test' });
  assert.ok(loaded?.config.server?.proxy, 'The real development proxy configuration must be present');
  // Replace only the destination; exercise the actual route matching and Vite proxy.
  const proxy = Object.fromEntries(Object.entries(loaded.config.server.proxy).map(([path, options]) => [
    path, typeof options === 'string' ? target : { ...options, target },
  ]));
  vite = await createServer({ ...loaded.config, configFile: false, logLevel: 'silent',
    server: { ...loaded.config.server, proxy, host: '127.0.0.1', port, strictPort: false },
  });
  await vite.listen();
  origin = `http://127.0.0.1:${vite.httpServer.address().port}`;
}, { timeout: 30_000 });

after(async () => {
  await vite?.close();
  if (backend) {
    backend.closeAllConnections();
    await new Promise((resolve, reject) => backend.close(error => error ? reject(error) : resolve()));
  }
}, { timeout: 30_000 });

for (const path of ['/athlete/profile', '/athlete/day?date=2026-11-02', '/healthkit/status', '/api/admin/usage',
  '/metrics/resting_hr?days=7', '/sleep?limit=42', '/legal/config']) {
  test(`development forwards ${path} to the API`, async () => {
    const response = await fetch(origin + path, { signal: AbortSignal.timeout(10_000) });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /application\/json/);
    assert.deepEqual(await response.json(), { path, method: 'GET', csrf: null });
  });
}

test('development feedback forwards POST and the CSRF header without serving the SPA', async () => {
  const response = await fetch(origin + '/api/feedback', { method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'synthetic-token' },
    body: JSON.stringify({ category: 'bug', message: 'Synthetic proxy contract' }), signal: AbortSignal.timeout(10_000),
  });
  assert.deepEqual(await response.json(), { path: '/api/feedback', method: 'POST', csrf: 'synthetic-token' });
});

for (const path of ['/app/biometrics', '/legal/privacy']) {
  test(`development keeps ${path} in the frontend`, async () => {
    const response = await fetch(origin + path, { signal: AbortSignal.timeout(10_000) });
    assert.equal(response.status, 200);
    assert.match(response.headers.get('content-type'), /text\/html/);
  });
}
