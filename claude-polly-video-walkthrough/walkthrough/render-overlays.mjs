/**
 * Post-process stage 1 of 2.
 *
 * For each step, render two transparent PNGs that will be composited
 * onto the captured frame by ffmpeg:
 *   - NN-title.png   the top bar (title · purpose · step counter)
 *   - NN-caption.png the bottom bar (narration prose)
 *
 * Both bars are rendered from the SAME inline HTML template so they
 * share padding, background, border, shadow, and typography. The page
 * is loaded headless in Playwright with a transparent body, and we
 * screenshot the .demo-bar element with `omitBackground: true`.
 *
 * Output: presentation/overlays/NN-{title,caption}.png
 */
import { chromium } from 'playwright';
import { mkdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const OVERLAYS = join(ROOT, 'overlays');

const BAR_WIDTH = 1500; // px; matches what render-video.mjs centers in 1920w

const SHARED_CSS = `
  :root {
    --bg: #0b1120;
    --border: #243352;
    --text: #e7edf7;
    --muted: #93a4c3;
    --hl: #fbbf24;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 24px;             /* breathing room so box-shadow isn't clipped */
    background: transparent;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--text);
  }
  .demo-bar {
    width: ${BAR_WIDTH}px;
    padding: 22px 32px;
    border-radius: 16px;
    background: rgb(11 17 32 / 92%);
    border: 1px solid var(--border);
    box-shadow: 0 14px 44px rgb(0 0 0 / 45%);
    line-height: 1.45;
  }
  .demo-bar .eyebrow {
    display: block;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--hl);
    margin-bottom: 8px;
    font-weight: 700;
  }
  /* Title bar layout */
  .title-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 32px;
  }
  .title-bar .title {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0;
  }
  .title-bar .purpose {
    display: block;
    font-size: 14px;
    color: var(--muted);
    margin-top: 6px;
    font-weight: 500;
  }
  .title-bar .step-counter {
    font-size: 13px;
    color: var(--muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    white-space: nowrap;
    font-weight: 600;
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: rgb(36 51 82 / 50%);
  }
  /* Caption bar layout */
  .caption-bar {
    text-align: center;
  }
  .caption-bar .narration {
    display: block;
    font-size: 22px;
    line-height: 1.5;
    font-weight: 500;
  }
`;

function titleHtml({ title, purpose, n, total }) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${SHARED_CSS}</style></head><body>
    <div class="demo-bar title-bar" id="bar">
      <div>
        <span class="eyebrow">Walkthrough</span>
        <p class="title">${escape(title)}</p>
        <span class="purpose">${escape(purpose)}</span>
      </div>
      <span class="step-counter">Step ${n} of ${total}</span>
    </div>
  </body></html>`;
}

function captionHtml({ caption, narration, n, total }) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${SHARED_CSS}</style></head><body>
    <div class="demo-bar caption-bar" id="bar">
      <span class="eyebrow">Step ${n} · ${escape(caption)}</span>
      <span class="narration">${escape(narration)}</span>
    </div>
  </body></html>`;
}

function escape(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

async function renderBar(page, html, outPath) {
  await page.setContent(html, { waitUntil: 'load' });
  const el = await page.$('#bar');
  await el.screenshot({ path: outPath, omitBackground: true });
}

async function main() {
  const manifest = JSON.parse(await readFile(join(ROOT, 'steps.json'), 'utf8'));
  await mkdir(OVERLAYS, { recursive: true });

  const browser = await chromium.launch();
  // Viewport just needs to be big enough to fit the bar + 24px padding.
  const page = await browser.newPage({
    viewport: { width: BAR_WIDTH + 64, height: 400 },
    deviceScaleFactor: 2,           // crisper text when composited at 1920w
  });

  const total = manifest.steps.length;
  for (const step of manifest.steps) {
    process.stdout.write(`  step ${step.n}: overlays … `);

    await renderBar(
      page,
      titleHtml({ title: manifest.title, purpose: manifest.purpose, n: step.n, total }),
      join(ROOT, step.titleOverlay),
    );
    await renderBar(
      page,
      captionHtml({ caption: step.caption, narration: step.narration, n: step.n, total }),
      join(ROOT, step.captionOverlay),
    );

    console.log('done');
  }

  await browser.close();
  console.log(`\n✓ ${total * 2} overlay PNGs → ${OVERLAYS}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
