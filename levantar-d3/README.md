# Levantar D3 components

Twenty-four D3 chart and metric components in the Levantar brand, built for the
questions the company gets paid to answer. Where does AI genuinely pay, what is the
evidence, and is it safe to rely on.

Open `index.html` in a browser for the catalogue, or use the published copy at
https://levantar-ai.github.io/demos/levantar-d3/. Every component renders there with
demo data, sample use cases and the call that produced it. No build step and no server
are needed, the page works from the file system.

## Using a component

`dist/` is a build output and is not committed. Run `node scripts/build.js` once to
produce `dist/levantar-d3.js` and `dist/lv.css`, or load the files under `src/` directly
as `index.html` does.

```html
<link rel="stylesheet" href="dist/lv.css">
<script src="vendor/d3.v7.min.js"></script>
<script src="dist/levantar-d3.js"></script>
<div id="target"></div>
<script>
  LV.render('statTile', document.querySelector('#target'), {
    label: 'Cost per resolved ticket', value: 1.84, unit: '£', key: true,
    delta: { value: -22, vs: 'previous 30 days', upIsGood: false, fmt: v => v + '%' },
    trend: [2.9, 2.7, 2.8, 2.6, 2.4, 2.5, 2.3, 2.1, 2.2, 2.0, 1.9, 1.84]
  });
</script>
```

`LV.render(name, element, options)` mounts the component and re-renders it when the
element's width changes. Omit `options` to get the demo data. `LV.list()` returns every
registered component with its title, summary and use cases. The option shape for each
one is the `demo()` in its source file under `src/components/`.

The fonts in `fonts/` are the same files the website serves. `dist/lv.css` expects them
one directory up, so keep `dist/` and `fonts/` side by side or edit the two `@font-face`
paths.

## The components

| # | Name | Group | What it is for |
|---|------|-------|----------------|
| 01 | `statTile` | metrics | Brand stat card with delta and sparkline |
| 02 | `heroFigure` | metrics | The one number a page leads with |
| 03 | `gapMeter` | metrics | Ordered stages on identical tracks, the 88 / 39 / 6 block |
| 04 | `verdictTile` | metrics | Back, fix or stop with the reasoning attached |
| 05 | `rangeEstimate` | metrics | A claimed figure with its low to high range and the line it must clear |
| 06 | `paybackMeter` | metrics | Months to break even on a fixed horizon |
| 07 | `evidenceLadder` | metrics | Claimed, self-reported, measured, audited |
| 08 | `unitEconomicsTile` | metrics | Cost per outcome with its two inputs |
| 09 | `initiativeMatrix` | value | Value against evidence, sized by budget, marked by verdict |
| 10 | `valueWaterfall` | value | Claimed value down to net |
| 11 | `spendReturnLines` | value | Cumulative spend and return on one axis, break-even named |
| 12 | `assumptionTree` | value | What has to be true, each node holds, untested or does not hold |
| 13 | `budgetSlope` | value | Budget before and after review |
| 14 | `counterfactualChart` | value | Observed against the fitted baseline, the gap is the attribution |
| 15 | `exposureHeatmap` | security | Systems against threat classes on one teal ramp |
| 16 | `fixFirst` | security | Findings ranked by risk with effort and the cut line |
| 17 | `runTimeline` | security | One agent run on lanes, guardrail hits and approvals flagged |
| 18 | `guardrailFunnel` | security | Requests through each control with the count stopped |
| 19 | `driftChart` | security | A metric with control limits from the baseline window |
| 20 | `readinessMatrix` | agentic | Use-cases against the gates, met, partial or gap |
| 21 | `handoffFlow` | agentic | Work passing between agents, systems and human checkpoints |
| 22 | `runOutcomes` | agentic | Runs per week by outcome |
| 23 | `annotatedTrend` | agentic | A cost line with the decisions that shaped it |
| 24 | `routingMix` | agentic | Share of requests per model and cost per thousand |

## Design rules the components follow

The brand is the authority. Colour, type and motifs come from
`levantar-brand-template.html` v1.0 and the brand guide. On top of that, the charts
follow the data visualisation method in the `dataviz` skill.

- Teal is structure and the first series. Sand is the warm pole for costs and partial
  states. Ink is totals, gaps and human checkpoints. Flame is action-only in the brand
  and never appears in a chart.
- The categorical order is fixed, teal, light teal, ink, sand, and never cycled. The
  order was checked with the palette validator: worst adjacent-pair separation under
  colour-vision deficiency is dE 37.5, far above the target of 8. Scatter and bubble
  forms use the first three only, because sand against light teal fails the all-pairs
  check.
- The brand's low-chroma palette fails the validator's generic lightness and chroma
  bands by design, and light teal and sand sit below 3:1 on white. The mitigation the
  method requires is shipped on every chart: a legend for two or more series, direct
  labels where they matter, and a table view behind the Table button.
- Verdicts and status never rest on colour. Back, fix, stop, met, partial, gap, holds,
  untested, and guardrail hits each carry a glyph and a word.
- Sequential magnitude is one teal ramp, light to dark. There is no rainbow and no
  dual axis anywhere.
- Marks are thin. Bars are at most 24px with a rounded data end and a square baseline,
  lines are 2px, markers carry a 2px surface ring, stacked segments have a 2px surface
  gap, gridlines are solid hairlines.
- Hover adds detail and never gates it. Every value is in the table view.
- Inter Tight for everything, Source Serif 4 italic for captions and standfirsts,
  headings at weight 600, sentence case, uppercase only via letter-spaced CSS labels.

The catalogue is paper-only, like the brand documents. There is no dark mode.

## Checking a change

```bash
node scripts/build.js                       # rebuild dist/
node scripts/screenshot.js shots            # needs playwright; renders every component
./scripts/publish-docs.sh                   # copy the catalogue into docs/levantar-d3 for GitHub Pages
```

The screenshot script writes `page.png` and one image per component and reports console
errors and whether the fonts loaded. Look at the images before shipping. The validator
checks colour, not layout.
