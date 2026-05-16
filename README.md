# Levantar — Demos

A small monorepo of self-contained demos. Each demo lives in its own directory;
the static walkthroughs are published via GitHub Pages.

**Live:** https://levantar-ai.github.io/demos/

## Demos

| Demo | What it shows | Live walkthrough |
|------|---------------|------------------|
| [`claude-playwright-walkthrough/`](claude-playwright-walkthrough/) | Point Claude at a feature; it drives Playwright through the flow, captures a screenshot per step, and renders an interactive D3 walkthrough. The capture script is the single source of truth for both the screenshots and the narrative. | [open →](https://levantar-ai.github.io/demos/claude-playwright-walkthrough/) |

## Layout

```
demos/
  docs/                                 GitHub Pages root (served from main /docs)
    index.html                          landing page listing demos
    claude-playwright-walkthrough/      static, regenerated copy of the presentation
  claude-playwright-walkthrough/        the runnable demo project (see its README)
```

`docs/` holds only static, committed artifacts so the walkthroughs are viewable
without running anything. To regenerate a demo's published page, re-run its
capture step and copy `presentation/` into the matching `docs/` subdirectory.
