/* Renders index.html headless and screenshots the page and every component.
   Usage: node scripts/screenshot.js [outDir]   (needs playwright on NODE_PATH or installed locally) */
const { chromium } = require('playwright');
const path = require('path'), fs = require('fs');
(async () => {
  const out = process.argv[2] || path.join(__dirname, '..', 'shots');
  fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  p.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errors.push(m.type() + ': ' + m.text()); });
  p.on('pageerror', e => errors.push('pageerror: ' + e.message));
  await p.goto('file://' + path.resolve(__dirname, '..', 'index.html'), { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(300);
  await p.screenshot({ path: path.join(out, 'page.png'), fullPage: true });
  const ids = await p.$$eval('article.comp', a => a.map(x => x.id));
  for (const id of ids) {
    const el = await p.$('#' + id);
    await el.screenshot({ path: path.join(out, id + '.png') });
  }
  const fonts = await p.evaluate(() => Array.from(document.fonts).map(f => f.family + ' ' + f.status));
  await b.close();
  console.log('components:', ids.length);
  console.log('fonts:', fonts.join(' | '));
  console.log(errors.length ? 'ERRORS:\n' + errors.join('\n') : 'no console errors');
})();
