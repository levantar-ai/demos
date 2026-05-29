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
// MANIFEST may be overridden to render overlays for a localized variant.
// Overlay output paths come from each step, so per-language manifests point
// step.{title,caption}Overlay at their own subdir.
const MANIFEST = process.env.MANIFEST
  ? (process.env.MANIFEST.startsWith('/') ? process.env.MANIFEST : join(ROOT, process.env.MANIFEST))
  : join(ROOT, 'steps.json');

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
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, "Droid Sans Fallback", sans-serif;
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
  /* Right-hand group: language flag (demo) + step counter */
  .title-bar .right {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .title-bar .lang {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .title-bar .lang .code {
    font-size: 12px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    font-weight: 700;
  }
  .title-bar .flag {
    display: block;
    width: 50px;
    height: 34px;
    border-radius: 5px;
    overflow: hidden;
    border: 1px solid rgb(255 255 255 / 22%);
    box-shadow: 0 2px 10px rgb(0 0 0 / 40%);
  }
  .title-bar .flag svg { display: block; width: 100%; height: 100%; }
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

// Inline SVG flags — deterministic and crisp at 2x, no emoji-font dependency.
// Each is drawn in a 60x40 box (Union Jack uses its own 60x30 then scales).
const FLAGS = {
  fr: '<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#fff"/><rect width="20" height="40" fill="#0055A4"/><rect x="40" width="20" height="40" fill="#EF4135"/></svg>',
  es: '<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#AA151B"/><rect y="10" width="60" height="20" fill="#F1BF00"/></svg>',
  ja: '<svg viewBox="0 0 60 40"><rect width="60" height="40" fill="#fff"/><circle cx="30" cy="20" r="12" fill="#BC002D"/></svg>',
  gb: '<svg viewBox="0 0 60 30"><clipPath id="s"><rect width="60" height="30"/></clipPath><g clip-path="url(#s)"><rect width="60" height="30" fill="#012169"/><path d="M0,0 60,30 M60,0 0,30" stroke="#fff" stroke-width="6"/><clipPath id="t"><path d="M30,15 30,0 60,0 z M30,15 60,15 60,30 z M30,15 30,30 0,30 z M30,15 0,15 0,0 z"/></clipPath><path d="M0,0 60,30 M60,0 0,30" clip-path="url(#t)" stroke="#C8102E" stroke-width="4"/><path d="M30,0 v30 M0,15 h60" stroke="#fff" stroke-width="10"/><path d="M30,0 v30 M0,15 h60" stroke="#C8102E" stroke-width="6"/></g></svg>',
};

// Map a manifest language to its demonstration flag. English (the base
// manifest has no `lang`) uses the Union Jack to match the British voice.
const FLAG_BY_LANG = { en: 'gb', fr: 'fr', es: 'es', ja: 'ja' };

function titleHtml({ title, purpose, n, total, labels, flagKey, langCode }) {
  const flag = FLAGS[flagKey]
    ? `<span class="lang"><span class="flag">${FLAGS[flagKey]}</span><span class="code">${escape(langCode)}</span></span>`
    : '';
  return `<!doctype html><html><head><meta charset="utf-8"><style>${SHARED_CSS}</style></head><body>
    <div class="demo-bar title-bar" id="bar">
      <div>
        <span class="eyebrow">${escape(labels.walkthrough)}</span>
        <p class="title">${escape(title)}</p>
        <span class="purpose">${escape(purpose)}</span>
      </div>
      <div class="right">
        ${flag}
        <span class="step-counter">${escape(labels.step)} ${n} ${escape(labels.of)} ${total}</span>
      </div>
    </div>
  </body></html>`;
}

function captionHtml({ caption, narration, n, labels }) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${SHARED_CSS}</style></head><body>
    <div class="demo-bar caption-bar" id="bar">
      <span class="eyebrow">${escape(labels.step)} ${n} · ${escape(caption)}</span>
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
  const manifest = JSON.parse(await readFile(MANIFEST, 'utf8'));

  const browser = await chromium.launch();
  // Viewport just needs to be big enough to fit the bar + 24px padding.
  const page = await browser.newPage({
    viewport: { width: BAR_WIDTH + 64, height: 400 },
    deviceScaleFactor: 2,           // crisper text when composited at 1920w
  });

  // Localizable UI labels; English defaults keep the original pipeline intact.
  const labels = { walkthrough: 'Walkthrough', step: 'Step', of: 'of', ...(manifest.labels || {}) };

  // Demonstration flag for the title bar: explicit manifest.flag wins, else
  // derived from the language (English base → Union Jack for the British voice).
  const lang = manifest.lang || 'en';
  const flagKey = manifest.flag || FLAG_BY_LANG[lang] || null;
  const langCode = lang === 'en' ? 'EN' : lang.toUpperCase();

  const total = manifest.steps.length;
  for (const step of manifest.steps) {
    process.stdout.write(`  step ${step.n}: overlays … `);

    const titlePath = join(ROOT, step.titleOverlay);
    const captionPath = join(ROOT, step.captionOverlay);
    await mkdir(dirname(titlePath), { recursive: true });
    await mkdir(dirname(captionPath), { recursive: true });

    await renderBar(
      page,
      titleHtml({ title: manifest.title, purpose: manifest.purpose, n: step.n, total, labels, flagKey, langCode }),
      titlePath,
    );
    await renderBar(
      page,
      captionHtml({ caption: step.caption, narration: step.narration, n: step.n, labels }),
      captionPath,
    );

    console.log('done');
  }

  await browser.close();
  console.log(`\n✓ ${total * 2} overlay PNGs → ${dirname(join(ROOT, manifest.steps[0].titleOverlay))}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
