/**
 * Capture high-DPI images of the walkthrough page for social/blog use.
 * Self-contained: serves presentation/ then screenshots at 2x.
 *   - social-hero.png : header + first 3 steps, tight crop, very legible
 *   - social-full.png : the whole walkthrough at 2x
 */
import { chromium } from 'playwright';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, extname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const OUT = ROOT;
const TYPES = { '.html': 'text/html', '.json': 'application/json', '.png': 'image/png' };

const server = createServer(async (req, res) => {
  try {
    const p = decodeURIComponent(req.url.split('?')[0]);
    const file = join(ROOT, p === '/' ? 'index.html' : p);
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': TYPES[extname(file)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404).end('nf');
  }
});
await new Promise((r) => server.listen(0, r));
const port = server.address().port;
const url = `http://localhost:${port}/`;

const browser = await chromium.launch();

// Hero: tight, legible crop of the first three steps.
const heroPage = await browser.newPage({
  viewport: { width: 1000, height: 720 },
  deviceScaleFactor: 2,
});
await heroPage.goto(url, { waitUntil: 'networkidle' });
await heroPage.locator('svg image').first().waitFor();
await heroPage.waitForTimeout(400);
await heroPage.screenshot({ path: join(OUT, 'social-hero.png') });
console.log('✓ social-hero.png  (2000×1440)');

// Full: entire walkthrough at 2x.
const fullPage = await browser.newPage({
  viewport: { width: 1000, height: 900 },
  deviceScaleFactor: 2,
});
await fullPage.goto(url, { waitUntil: 'networkidle' });
await fullPage.locator('svg image').first().waitFor();
await fullPage.waitForTimeout(400);
await fullPage.screenshot({ path: join(OUT, 'social-full.png'), fullPage: true });
console.log('✓ social-full.png  (full page, 2x)');

await browser.close();
server.close();
