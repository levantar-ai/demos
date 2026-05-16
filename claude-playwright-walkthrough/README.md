# Claude + Playwright → interactive feature walkthrough

A tiny demo of one idea:

> **Point Claude at a feature. It drives Playwright through the flow, captures a
> screenshot per step, and renders an interactive D3 walkthrough — no screenshots
> taken by hand, no slide deck to maintain.**

The app itself (a contact form for a fake product, "Acme") is deliberately
boring. The interesting part is the pipeline around it.

## How it fits together

```
app/            Vite + React frontend, tiny Express API (in-memory store)
                Feature: Home → Contact form → validation → success → Submissions
walkthrough/
  capture.mjs   Playwright script. Each step declares its caption + sub AND
                the actions that produce its screenshot, then emits:
                  presentation/shots/NN-name.png   (one per step)
                  presentation/steps.json          (the manifest)
  serve.mjs     Zero-dep static server for the presentation
presentation/
  index.html    Generic D3 + GLightbox page. Renders steps.json. Knows
                nothing about this app — repoint it at any steps.json.
```

The key design choice: **`capture.mjs` is the single source of truth.** The same
array drives both the screenshots and the narrative text, so the visual and the
story can never drift. Claude edits that one file to add, reorder, or re-narrate
steps — the presentation regenerates itself.

## Run it

```bash
npm install
npx playwright install chromium     # one-time browser download

npm run dev                         # app on :5173, API on :8787
npm run capture                     # in another shell — drives the flow, writes shots
npm run present                     # walkthrough at http://localhost:4321
```

## Make it your own

Replace the `steps` array in `walkthrough/capture.mjs` with the flow you want to
document — any URL, any selectors. Everything downstream (manifest, D3 page,
lightbox) is generic and adapts automatically.
