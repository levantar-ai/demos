# Claude + Playwright + Polly → narrated MP4 walkthrough

A follow-on to `claude-playwright-walkthrough/`. The flow being captured is
identical — the same Acme contact form, the same six steps — but the output
is a single narrated MP4 instead of an interactive D3 page.

> **Per-step CSS spotlights highlight whichever element the narrator is
> talking about. Claude+Playwright captures the frames. AWS Polly (Arthur,
> en-GB, neural) narrates. ffmpeg stitches the result into one video.**

## How it fits together

```
app/            Vite + React frontend, tiny Express API (in-memory store)
                Pages annotated with data-demo-id="..." so the capture
                script can target any element by name.
                styles.css contains the .demo-spotlight / .demo-highlight
                overlay system (dim everything, pulse the focus).
walkthrough/
  capture.mjs         Playwright drives the flow. For each step:
                       - reaches the right state
                       - applies .demo-highlight to declared selectors
                       - takes a clean 1920x1080 still (no bars)
                      Writes presentation/shots/NN-name.png and
                      presentation/steps.json (the manifest).
  narrate.mjs         Reads the manifest, calls AWS Polly per step
                      (VoiceId=Arthur, Engine=neural, en-GB), writes
                      presentation/audio/NN-name.mp3.
  render-overlays.mjs Headless Playwright renders the title bar and
                      caption bar for each step as transparent PNGs
                      from a self-contained HTML template — the bars
                      never touch the app DOM.
  render-video.mjs    Per step, ffmpeg composites still + title PNG +
                      caption PNG with the narration MP3 as audio.
                      Concats all clips → presentation/walkthrough.mp4.
presentation/
  shots/         per-step PNGs (clean app frames, spotlight applied)
  overlays/      per-step title + caption PNGs (drawn in post)
  audio/         per-step MP3s
  clips/         per-step MP4s (intermediate)
  walkthrough.mp4   the final video
  steps.json     the contract between all four stages
```

`capture.mjs` is still the single source of truth — its `steps` array
declares the caption, the narration text Polly reads, *and* the CSS
selectors that get highlighted in that step. Edit one file; the
screenshots, the voice-over, and the highlight regions all stay in sync.

## Run it

```bash
npm install
npx playwright install chromium     # one-time browser download

# 1. App on :5173, API on :8787
npm run dev

# 2. In another shell — drive the flow and capture the highlighted stills
npm run capture

# 3. Narrate with Polly. Needs AWS creds; this repo uses aws-vault:
aws-vault exec personal_iphone -- npm run narrate

# 4. Render the title + caption bar PNGs (headless Playwright)
npm run overlays

# 5. Composite stills + overlays + audio into one MP4
npm run render
# → presentation/walkthrough.mp4
```

There's also a `npm run video` convenience that chains capture+narrate+overlays+render
(but you still need to wrap the whole thing in `aws-vault exec` to give Polly
credentials).

## Requirements

- `ffmpeg` and `ffprobe` on $PATH (used by `render-video.mjs`).
- AWS credentials with `polly:SynthesizeSpeech`. The default region is
  `eu-west-2`; override with `AWS_REGION=...` if needed.
- Voice Arthur is en-GB neural-only — already wired in `steps.json` and
  `narrate.mjs`. To swap voices, edit `voice` at the top of the manifest
  (after `capture` has run) or change the default in `capture.mjs`.

## Make it your own

Edit the `steps` array in `walkthrough/capture.mjs`:

```js
{
  name: 'my-step',
  caption: 'What the banner shows',
  narration: 'What Polly reads aloud, in plain prose.',
  highlight: ['[data-demo-id="some-element"]'],
  async run(page) { /* Playwright actions to reach this state */ },
}
```

Anything in the app that you want to be targetable just needs a
`data-demo-id="..."` attribute. Multiple selectors per step are supported
— all matching elements light up at once (see the validation step, which
highlights all three error messages simultaneously).
