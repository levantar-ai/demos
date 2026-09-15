LV.define({
  name: 'gapMeter', group: 'metrics', title: 'Gap meter',
  summary: 'Ordered stages on identical 0 to 100 tracks so a cliff reads as a funnel. The homepage 88 / 39 / 6 block, generalised for any adoption-to-value story.',
  useCases: ['Adopting, attributing profit, real value: the Levantar value gap', 'Client estate: pilots started, in production, with a measured return', 'Agent use-cases: proposed, readiness verdict given, trusted with real work'],
  demo: () => ({
    eyebrow: 'Value diagnostics', title: 'The AI value gap', stages: [
      { label: 'Adopting AI', value: 88, note: 'regular use in at least one function' },
      { label: 'Any profit impact', value: 39, note: 'can attribute some EBIT movement' },
      { label: 'Real value', value: 6, note: 'significant value and 5%+ EBIT impact', approx: true }
    ],
    footnote: 'Real value = significant value from AI plus 5%+ EBIT impact attributable to it.',
    caption: 'Source: McKinsey, State of AI 2025.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, rowH = 58, labelW = Math.min(180, w * 0.34), numW = 64, h = rowH * o.stages.length + (o.footnote ? 26 : 6);
    const svg = LV.svg(f.body, w, h);
    const x = d3.scaleLinear().domain([0, 100]).range([labelW + numW, w - 8]);
    const ramp = LV.palette.ordinal;
    const rows = svg.selectAll('g.row').data(o.stages).join('g').attr('class', 'row').attr('transform', (d, i) => `translate(0,${i * rowH})`);
    rows.append('text').attr('class', 'lv-lbl strong').attr('x', 0).attr('y', 22).text(d => d.label);
    rows.append('text').attr('class', 'lv-lbl muted').attr('x', 0).attr('y', 39).attr('font-size', 11).text(d => d.note || '');
    rows.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', labelW + numW - 14).attr('y', 24).attr('text-anchor', 'end').attr('font-size', 20).attr('letter-spacing', '-0.02em').text(d => (d.approx ? '~' : '') + d.value + '%');
    rows.append('rect').attr('x', x(0)).attr('y', 16).attr('width', x(100) - x(0)).attr('height', 10).attr('fill', t.paperWarm);
    rows.append('path').attr('d', d => LV.barPath(x(0), 16, Math.max(0, x(d.value) - x(0)), 10, 4, 'right')).attr('fill', (d, i) => ramp[Math.min(ramp.length - 1, Math.round(i * (ramp.length - 1) / Math.max(1, o.stages.length - 1)))]);
    rows.append('text').attr('class', 'lv-lbl muted').attr('x', x(0)).attr('y', 40).attr('font-size', 10).text('0');
    rows.append('text').attr('class', 'lv-lbl muted').attr('x', x(100)).attr('y', 40).attr('font-size', 10).attr('text-anchor', 'end').text('100');
    if (o.footnote) svg.append('text').attr('class', 'lv-lbl serif').attr('x', 0).attr('y', h - 6).attr('font-size', 12).text(o.footnote);
    f.table([{ key: 'label', label: 'Stage' }, { key: 'value', label: 'Share', num: true, fmt: (v, r) => (r.approx ? '~' : '') + v + '%' }, { key: 'note', label: 'What it means' }], o.stages);
  }
});
