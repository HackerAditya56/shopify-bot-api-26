// worker_server.mjs — run a Cloudflare Worker (Service Worker format) locally via Node HTTP.
// Usage: node worker_server.mjs <worker.js> [port]
import { readFileSync } from 'node:fs';
import { createServer } from 'node:http';

const [workerPath, portStr] = process.argv.slice(2);
const port = parseInt(portStr || '8787', 10);
if (!workerPath) {
  console.error('usage: node worker_server.mjs <worker.js> [port]');
  process.exit(1);
}

const source = readFileSync(workerPath, 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const worker = mod.default;

createServer(async (req, res) => {
  let body = '';
  for await (const chunk of req) body += chunk;
  const url = `http://127.0.0.1:${port}${req.url}`;
  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) {
    if (v) headers[k] = Array.isArray(v) ? v.join(', ') : v;
  }
  const request = new Request(url, { method: req.method, headers, body: body || undefined });
  try {
    const response = await worker.fetch(request);
    const text = await response.text();
    res.writeHead(response.status, Object.fromEntries(response.headers.entries()));
    res.end(text);
  } catch (e) {
    res.writeHead(500, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: String(e) }));
  }
}).listen(port, () => console.log(`[worker] ${workerPath} listening on http://127.0.0.1:${port}`));
