LV.define({
  name: 'valueWaterfall', group: 'value', title: 'Value waterfall',
  summary: 'From the value a business case claims down to what is left after run cost, build, and the oversight nobody budgeted for. Teal adds, sand takes away, ink is the total.',
  useCases: ['The ROI Recovery Sprint headline: claimed versus net', 'Explaining why a pilot with a real effect still loses money', 'Cost modelling in an Application Build proposal'],
  demo: () => ({
    eyebrow: 'ROI recovery sprint', title: 'Claimed value to net value, document intake automation', steps: [
      { label: 'Claimed value', value: 520000, kind: 'total' },
      { label: 'Unevidenced claims', value: -180000 },
      { label: 'Model and platform run cost', value: -96000 },
      { label: 'Build amortised', value: -60000 },
      { label: 'Human review time', value: -48000 },
      { label: 'Net value', kind: 'total' }
    ],
    caption: 'Human review time is the line most business cases omit. It is measured here from the reviewers\' own time records.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, h = 320, m = { t: 26, r: 12, b: 64, l: 56 };
    let run = 0; const rows = o.steps.map(s => { if (s.kind === 'total') { if (s.value != null) run = s.value; return { ...s, y0: 0, y1: run, value: run }; } const y0 = run; run += s.value; return { ...s, y0, y1: run }; });
    const x = d3.scaleBand().domain(rows.map(d => d.label)).range([m.l, w - m.r]).paddingInner(0.35).paddingOuter(0.1);
    const y = d3.scaleLinear().domain([Math.min(0, d3.min(rows, d => Math.min(d.y0, d.y1))), d3.max(rows, d => Math.max(d.y0, d.y1)) * 1.08]).nice().range([h - m.b, m.t]);
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g').attr('transform', `translate(${m.l},0)`), y, w - m.r - m.l, 5);
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickFormat(d => LV.fmt.gbp(d)).tickSize(0).tickPadding(8));
    svg.append('line').attr('x1', m.l).attr('x2', w - m.r).attr('y1', y(0)).attr('y2', y(0)).attr('stroke', t.ruleStrong);
    const bw = Math.min(x.bandwidth(), 40), off = (x.bandwidth() - bw) / 2;
    const color = d => d.kind === 'total' ? t.ink : d.value >= 0 ? t.teal : t.sandDeep;
    svg.selectAll('path.b').data(rows).join('path').attr('class', 'b').attr('fill', color)
      .attr('d', d => { const top = Math.min(d.y0, d.y1), bot = Math.max(d.y0, d.y1); const dir = d.kind === 'total' || d.value >= 0 ? 'up' : 'down'; return LV.barPath(x(d.label) + off, y(bot), bw, Math.max(1, y(top) - y(bot)), 4, dir); });
    svg.selectAll('line.c').data(rows.slice(0, -1)).join('line').attr('class', 'c').attr('x1', d => x(d.label) + off + bw).attr('x2', (d, i) => x(rows[i + 1].label) + off).attr('y1', d => y(d.y1)).attr('y2', d => y(d.y1)).attr('stroke', t.ruleStrong);
    svg.selectAll('text.v').data(rows).join('text').attr('class', 'lv-lbl strong lv-num').attr('x', d => x(d.label) + off + bw / 2).attr('y', d => y(Math.max(d.y0, d.y1)) - 6).attr('text-anchor', 'middle').attr('font-size', 11.5).text(d => d.kind === 'total' ? LV.fmt.gbp(d.value) : LV.fmt.signed(d.value, LV.fmt.gbp));
    const lab = svg.append('g').attr('class', 'lv-axis').attr('transform', `translate(0,${h - m.b + 16})`);
    lab.selectAll('text').data(rows).join('text').attr('x', d => x(d.label) + x.bandwidth() / 2).attr('y', 0).attr('text-anchor', 'middle').attr('font-size', 10.5).text(d => d.label).call(LV.wrap, x.bandwidth() + 8);
    const tip = LV.tooltip(f.body);
    svg.selectAll('rect.h').data(rows).join('rect').attr('class', 'lv-hit').attr('x', d => x(d.label)).attr('y', m.t).attr('width', x.bandwidth()).attr('height', h - m.t - m.b)
      .on('mousemove', (ev, d) => tip.show(x(d.label) + x.bandwidth() / 2, y(Math.max(d.y0, d.y1)), `<b>${LV.esc(d.label)}</b><br>${d.kind === 'total' ? LV.fmt.gbpFull(d.value) : LV.fmt.signed(d.value, LV.fmt.gbpFull)}<br><span class="m">running total ${LV.fmt.gbpFull(d.y1)}</span>`)).on('mouseleave', () => tip.hide());
    f.table([{ key: 'label', label: 'Line' }, { key: 'value', label: 'Amount', num: true, fmt: (v, r) => r.kind === 'total' ? LV.fmt.gbpFull(v) : LV.fmt.signed(v, LV.fmt.gbpFull) }, { key: 'y1', label: 'Running total', num: true, fmt: LV.fmt.gbpFull }], rows);
  }
});
