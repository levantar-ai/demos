LV.define({
  name: 'verdictTile', group: 'metrics', title: 'Verdict tile',
  summary: 'Back, fix or stop, with the reasoning attached rather than the conclusion alone. Icon and word together, so the verdict never rests on colour.',
  useCases: ['One tile per initiative in a Placement Assessment summary', 'The ROI Recovery Sprint roadmap: what to back, fix or stop', 'An agent use-case readiness verdict'],
  demo: () => ({
    verdict: 'fix', initiative: 'Contract summarisation assistant',
    why: 'Saves the legal team real hours, but nobody can size it because the baseline was never recorded. Instrument first, then decide the budget.',
    evidence: { measured: 2, claimed: 5 }, confidence: 'medium', budget: 84000
  }),
  render(el, o) {
    const p = LV.palette.verdict, v = o.verdict, color = p[v] || p.untested;
    const word = { back: 'Back it', fix: 'Fix it', stop: 'Stop funding', untested: 'Not yet assessed' }[v] || v;
    const glyph = { back: 'check', fix: 'tilde', stop: 'cross', untested: 'dot' }[v] || 'dot';
    const div = document.createElement('div');
    div.className = 'lv-verdict ' + v;
    div.innerHTML = `<div class="tag">Verdict</div><div class="word">${LV.glyphSvg(glyph, color, 26)}${LV.esc(word)}</div>` +
      `<div class="name">${LV.esc(o.initiative)}</div>${o.why ? `<div class="why">${LV.esc(o.why)}</div>` : ''}` +
      `<div class="meta">${o.evidence ? `<span><b>${o.evidence.measured}</b> of <b>${o.evidence.claimed}</b> claims measured</span>` : ''}${o.confidence ? `<span>Confidence <b>${LV.esc(o.confidence)}</b></span>` : ''}${o.budget != null ? `<span>Budget <b>${LV.fmt.gbp(o.budget)}</b></span>` : ''}</div>`;
    el.appendChild(div);
  }
});
