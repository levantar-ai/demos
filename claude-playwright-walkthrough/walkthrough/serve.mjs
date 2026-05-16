/** Zero-dependency static server for the presentation/ folder. */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, extname, join, normalize } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const PORT = process.env.PRESENT_PORT || 4321;

const TYPES = {
  '.html': 'text/html', '.json': 'application/json', '.png': 'image/png',
  '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml',
};

createServer(async (req, res) => {
  try {
    const urlPath = decodeURIComponent(req.url.split('?')[0]);
    const rel = normalize(urlPath === '/' ? '/index.html' : urlPath).replace(/^(\.\.[/\\])+/, '');
    const file = join(ROOT, rel);
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not found');
  }
}).listen(PORT, () => console.log(`[present] http://localhost:${PORT}`));
