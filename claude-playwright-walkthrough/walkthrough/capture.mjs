/**
 * The whole point of this repo.
 *
 * Each step below declares its narrative (caption + sub) AND the Playwright
 * actions that produce its screenshot. Running this script emits:
 *   - presentation/shots/NN-name.png   (one screenshot per step)
 *   - presentation/steps.json          (the manifest the D3 page renders)
 *
 * Because the same array is the source of both the screenshots and the
 * walkthrough text, the visual and the narrative can never drift apart.
 * Claude edits this file to add/reorder steps; the presentation updates itself.
 */
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SHOTS = join(__dirname, '..', 'presentation', 'shots');
const MANIFEST = join(__dirname, '..', 'presentation', 'steps.json');
const BASE = process.env.BASE_URL || 'http://localhost:5173';

const steps = [
  {
    name: 'home',
    caption: 'Landing page',
    sub: 'The feature entry point — a visitor arrives at Acme.',
    async run(page) {
      await page.goto(BASE, { waitUntil: 'networkidle' });
      await page.getByRole('heading', { name: /Talk to a human/i }).waitFor();
    },
  },
  {
    name: 'contact-open',
    caption: 'Contact form opened',
    sub: 'Clicking “Get in touch” routes to the contact form.',
    async run(page) {
      await page.getByRole('button', { name: 'Get in touch' }).click();
      await page.waitForURL('**/contact');
      await page.getByLabel('Message').waitFor();
    },
  },
  {
    name: 'validation',
    caption: 'Inline validation',
    sub: 'Submitting empty surfaces field-level errors — no bad data reaches the API.',
    async run(page) {
      await page.getByRole('button', { name: 'Send message' }).click();
      await page.getByText('Please tell us your name.').waitFor();
    },
  },
  {
    name: 'filled',
    caption: 'Form completed',
    sub: 'A valid enquiry filled in and ready to send.',
    async run(page) {
      await page.getByLabel('Name').fill('Ada Lovelace');
      await page.getByLabel('Email').fill('ada@analytical-engine.org');
      await page
        .getByLabel('Message')
        .fill('Loved the demo — can you walk me through the Playwright capture pipeline?');
      await page.getByText('Please tell us your name.').waitFor({ state: 'detached' });
    },
  },
  {
    name: 'success',
    caption: 'Submission confirmed',
    sub: 'POST /api/contact succeeds; the user lands on a confirmation with a ticket id.',
    async run(page) {
      await page.getByRole('button', { name: 'Send message' }).click();
      await page.waitForURL('**/success**');
      await page.getByRole('heading', { name: 'Message sent' }).waitFor();
    },
  },
  {
    name: 'admin',
    caption: 'Appears in submissions',
    sub: 'The backend admin list shows the new submission — end-to-end proof.',
    async run(page) {
      await page.goto(`${BASE}/admin`, { waitUntil: 'networkidle' });
      await page.getByText('ada@analytical-engine.org').waitFor();
    },
  },
];

async function main() {
  await mkdir(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  const manifest = [];
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const n = i + 1;
    const file = `${String(n).padStart(2, '0')}-${step.name}.png`;
    process.stdout.write(`  step ${n}: ${step.caption} … `);
    await step.run(page);
    await page.waitForTimeout(250); // let transitions settle
    await page.screenshot({ path: join(SHOTS, file) });
    manifest.push({ n, file, caption: step.caption, sub: step.sub });
    console.log('captured', file);
  }

  await browser.close();
  await writeFile(MANIFEST, JSON.stringify({ title: 'Acme — Contact a human', steps: manifest }, null, 2));
  console.log(`\n✓ ${manifest.length} steps → presentation/steps.json`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
