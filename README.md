# Levantar — Demos

A small monorepo of self-contained demos. Each demo lives in its own directory;
the static walkthroughs are published via GitHub Pages.

**Live:** https://levantar-ai.github.io/demos/

## Demos

| Demo | What it shows | Live walkthrough |
|------|---------------|------------------|
| [`claude-playwright-walkthrough/`](claude-playwright-walkthrough/) | Point Claude at a feature; it drives Playwright through the flow, captures a screenshot per step, and renders an interactive D3 walkthrough. The capture script is the single source of truth for both the screenshots and the narrative. | [open →](https://levantar-ai.github.io/demos/claude-playwright-walkthrough/) |
| [`claude-polly-video-walkthrough/`](claude-polly-video-walkthrough/) | Same flow as the first demo, but the output is a single narrated MP4. Playwright captures clean frames with on-page CSS spotlights; AWS Polly (Arthur, en-GB) narrates each step; ffmpeg composites the title and caption bars in post and stitches the clips. | [open →](https://levantar-ai.github.io/demos/claude-polly-video-walkthrough/) |

## Layout

```
demos/
  docs/                                 GitHub Pages root (served from main /docs)
    index.html                          landing page listing demos
    claude-playwright-walkthrough/      static, regenerated copy of the presentation
    claude-polly-video-walkthrough/     index.html + walkthrough.mp4
  claude-playwright-walkthrough/        the runnable demo project (see its README)
  claude-polly-video-walkthrough/       runnable demo: Claude + Playwright + Polly → MP4
```

`docs/` holds only static, committed artifacts so the walkthroughs are viewable
without running anything. To regenerate a demo's published page, re-run its
capture step and copy `presentation/` into the matching `docs/` subdirectory.
