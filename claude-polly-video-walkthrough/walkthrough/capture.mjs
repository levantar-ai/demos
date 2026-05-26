/**
 * Stage 1 of the video pipeline.
 *
 * For each step:
 *   1. Drive the app to the right state with Playwright.
 *   2. Apply `.demo-spotlight` to <body> and `.demo-highlight` to one or
 *      more `data-demo-id` targets so the captured frame dims everything
 *      except the focus element.
 *   3. Screenshot at 1920x1080. Clean frame — no title bar, no caption.
 *      Those are drawn on top in post by walkthrough/render-overlays.mjs.
 *
 * Output:
 *   presentation/shots/NN-name.png       (one frame per step)
 *   presentation/steps.json              (manifest: header + steps[])
 *
 * The `narration` field is what AWS Polly reads aloud AND what the
 * post-process draws into the caption bar. Keep it tight and
 * conversational — one to three short sentences per step.
 */
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, '..', 'presentation');
const SHOTS = join(ROOT, 'shots');
const MANIFEST = join(ROOT, 'steps.json');
const BASE = process.env.BASE_URL || 'http://localhost:5173';

const VIEWPORT = { width: 1920, height: 1080 };

const header = {
  title: 'Acme — Contact a human',
  purpose:
    'Claude + Playwright capture · AWS Polly narrates (Arthur, en-GB) · ffmpeg stitches',
};

const steps = [
  {
    name: 'home',
    caption: 'Landing page',
    narration:
      "Welcome to Acme — our deliberately boring demo product. A visitor lands on the home page, and the primary call to action is right up front: Get in touch.",
    highlight: ['[data-demo-id="cta-primary"]'],
    async run(page) {
      await page.goto(BASE, { waitUntil: 'networkidle' });
      await page.getByRole('heading', { name: /Talk to a human/i }).waitFor();
    },
  },
  {
    name: 'contact-open',
    caption: 'Contact form opened',
    narration:
      "Clicking Get in touch routes the visitor to a simple contact form. Three fields — name, email, and message — and a single submit button. Nothing clever.",
    highlight: ['[data-demo-id="contact-form"]'],
    async run(page) {
      await page.getByRole('button', { name: 'Get in touch' }).click();
      await page.waitForURL('**/contact');
      await page.getByLabel('Message').waitFor();
    },
  },
  {
    name: 'validation',
    caption: 'Inline validation',
    narration:
      "Submitting an empty form surfaces inline validation against each field. No malformed data ever reaches the back end — the user sees exactly what is missing.",
    highlight: [
      '[data-demo-id="err-name"]',
      '[data-demo-id="err-email"]',
      '[data-demo-id="err-message"]',
    ],
    async run(page) {
      await page.getByRole('button', { name: 'Send message' }).click();
      await page.getByText('Please tell us your name.').waitFor();
    },
  },
  {
    name: 'filled',
    caption: 'Form completed',
    narration:
      "Once the fields are filled in with valid input the inline errors disappear automatically, and the form is ready to send.",
    highlight: ['[data-demo-id="contact-form"]'],
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
    name: 'ready-to-send',
    caption: 'Ready to send',
    narration:
      "With every field valid, the Send message button is now armed. One click submits the message to the back end.",
    highlight: ['[data-demo-id="submit"]'],
    async run(page) {
      await page.getByRole('button', { name: 'Send message' }).hover();
    },
  },
  {
    name: 'success',
    caption: 'Submission confirmed',
    narration:
      "The POST to slash A P I slash contact succeeds, and the user lands on a confirmation page with a unique ticket identifier.",
    highlight: ['[data-demo-id="ticket-id"]'],
    async run(page) {
      await page.getByRole('button', { name: 'Send message' }).click();
      await page.waitForURL('**/success**');
      await page.getByRole('heading', { name: 'Message sent' }).waitFor();
    },
  },
  {
    name: 'admin',
    caption: 'Appears in submissions',
    narration:
      "And here is the end-to-end proof. The submission shows up in the back office list with a fresh timestamp — exactly the row Ada just created.",
    highlight: ['[data-demo-id="latest-row"]'],
    async run(page) {
      await page.goto(`${BASE}/admin`, { waitUntil: 'networkidle' });
      await page.getByText('ada@analytical-engine.org').waitFor();
    },
  },
];

async function applySpotlight(page, selectors) {
  await page.evaluate((sels) => {
    document.body.classList.add('demo-spotlight');
    document.querySelectorAll('.demo-highlight').forEach((el) => el.classList.remove('demo-highlight'));
    for (const sel of sels) {
      document.querySelectorAll(sel).forEach((el) => el.classList.add('demo-highlight'));
    }
  }, selectors);
}

async function clearSpotlight(page) {
  await page.evaluate(() => {
    document.body.classList.remove('demo-spotlight');
    document.querySelectorAll('.demo-highlight').forEach((el) => el.classList.remove('demo-highlight'));
  });
}

async function main() {
  await mkdir(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: VIEWPORT });

  const manifest = [];
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const n = i + 1;
    const file = `${String(n).padStart(2, '0')}-${step.name}.png`;
    process.stdout.write(`  step ${n}: ${step.caption} … `);

    await clearSpotlight(page).catch(() => {}); // page may not exist yet on first step
    await step.run(page);
    await applySpotlight(page, step.highlight);
    await page.waitForTimeout(400); // let pulse animation reach a bright frame
    await page.screenshot({ path: join(SHOTS, file), fullPage: false });

    manifest.push({
      n,
      name: step.name,
      file,
      caption: step.caption,
      narration: step.narration,
      audio: `audio/${String(n).padStart(2, '0')}-${step.name}.mp3`,
      titleOverlay: `overlays/${String(n).padStart(2, '0')}-title.png`,
      captionOverlay: `overlays/${String(n).padStart(2, '0')}-caption.png`,
    });
    console.log('captured', file);
  }

  await browser.close();
  await writeFile(
    MANIFEST,
    JSON.stringify(
      {
        title: header.title,
        purpose: header.purpose,
        viewport: VIEWPORT,
        voice: { id: 'Arthur', engine: 'neural', languageCode: 'en-GB' },
        steps: manifest,
      },
      null,
      2,
    ),
  );
  console.log(`\n✓ ${manifest.length} steps → presentation/steps.json`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
