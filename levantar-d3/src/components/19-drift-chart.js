LV.define({
  name: 'driftChart', group: 'security', title: 'Drift chart',
  summary: 'A quality metric over time with control limits fitted to the baseline window, and every point outside them flagged. Drift and silent regressions become visible the week they start, not the quarter they are noticed.',
  useCases: ['Eval pass rate after each prompt or model change', 'Answer accuracy on a fixed golden set, run nightly', 'Any metric a guardrails programme promises to watch'],
  demo: () => {
    const weeks = d3.range(20).map(i => new Date(2026, 3, 6 + i * 7)), base = 94.1;
    return { metric: 'Golden-set pass rate (%)', baselineWeeks: 8, data: weeks.map((d, i) => ({ date: d, value: +(base + (i < 8 ? Math.sin(i * 1.3) * 0.9 : i < 13 ? Math.sin(i) * 0.8 - 0.3 : -2.4 - (i - 13) * 0.6 + Math.cos(i) * 0.5)).toFixed(1) })), events: [{ date: weeks[13], label: 'Model upgraded' }], caption: 'Limits are three standard deviations from the eight-week baseline. The first flagged point is the week the model was upgraded without a re-run of the evals.' };
  },
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title || o.metric, caption: o.caption });
    const w = f.width, h = 290, m = { t: 22, r: 24, b: 34, l: 44 }, data = o.data, nb = o.baselineWeeks || 8;
    const base = data.slice(0, nb).map(d => d.value), mean = d3.mean(base), sd = d3.deviation(base) || 0.5, lo = mean - 3 * sd, hi = mean + 3 * sd;
    const x = d3.scaleTime().domain(d3.extent(data, d => d.date)).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([Math.min(lo, d3.min(data, d => d.value)) - 1, Math.max(hi, d3.max(data, d => d.value)) + 1]).nice().range([h - m.b, m.t]);
    const flagged = data.filter(d => d.value < lo || d.value > hi);
    f.legend([{ label: o.metric || 'Metric', color: t.teal, shape: 'line' }, { label: 'Control band, baseline ±3σ', color: t.tealWash }, { label: 'Outside limits', color: t.sandDeep, shape: 'dot' }]);
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g').attr('transform', `translate(${m.l},0)`), y, w - m.r - m.l, 5);
    svg.append('rect').attr('x', m.l).attr('y', y(hi)).attr('width', w - m.l - m.r).attr('height', y(lo) - y(hi)).attr('fill', t.tealWash);
    svg.append('line').attr('x1', m.l).attr('x2', w - m.r).attr('y1', y(mean)).attr('y2', y(mean)).attr('stroke', t.tealLift).attr('stroke-width', 1);
    svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', x(data[nb - 1].date) - m.l).attr('height', h - m.t - m.b).attr('fill', t.ink).attr('opacity', .03);
    svg.append('text').attr('class', 'lv-lbl eyebrow').attr('x', m.l + 6).attr('y', m.t + 16).attr('fill', t.ink3).text('baseline window');
    svg.append('path').attr('d', d3.line().x(d => x(d.date)).y(d => y(d.value))(data)).attr('fill', 'none').attr('stroke', t.teal).attr('stroke-width', 2).attr('stroke-linejoin', 'round');
    svg.selectAll('circle.p').data(data).join('circle').attr('cx', d => x(d.date)).attr('cy', d => y(d.value)).attr('r', 3.5).attr('fill', t.teal).attr('stroke', t.surface).attr('stroke-width', 2);
    const fg = svg.selectAll('g.f').data(flagged).join('g').attr('transform', d => `translate(${x(d.date)},${y(d.value)})`);
    fg.append('circle').attr('r', 6).attr('fill', t.sandDeep).attr('stroke', t.surface).attr('stroke-width', 2);
    fg.append('g').attr('transform', 'translate(-8,-26)').each(function () { LV.glyphG(d3.select(this), 'warn', t.sandDeep, 16); });
    (o.events || []).forEach(e => { svg.append('line').attr('x1', x(e.date)).attr('x2', x(e.date)).attr('y1', m.t).attr('y2', h - m.b).attr('stroke', t.ink).attr('stroke-width', 1); svg.append('text').attr('class', 'lv-lbl serif').attr('x', x(e.date) + 6).attr('y', h - m.b - 8).attr('font-size', 12).text(e.label); });
    if (flagged.length) svg.append('text').attr('class', 'lv-lbl strong').attr('x', w - m.r).attr('y', m.t + 4).attr('text-anchor', 'end').attr('font-size', 11.5).text(`Drift from ${LV.fmt.day(flagged[0].date)} · ${flagged.length} of ${data.length} points outside limits`);
    LV.axisX(svg.append('g').attr('transform', `translate(0,${h - m.b})`), d3.axisBottom(x).ticks(Math.min(8, Math.floor(w / 90))).tickFormat(LV.fmt.day).tickSize(4));
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickSize(0).tickPadding(8));
    const tip = LV.tooltip(f.body), bis = d3.bisector(d => d.date).center;
    svg.append('rect').attr('class', 'lv-hit').attr('x', m.l).attr('y', m.t).attr('width', w - m.l - m.r).attr('height', h - m.t - m.b)
      .on('mousemove', ev => { const [px] = d3.pointer(ev); const d = data[bis(data, x.invert(px))]; tip.show(x(d.date), y(d.value), `<b>Week of ${LV.fmt.day(d.date)}</b><br>${d.value}${(d.value < lo || d.value > hi) ? ' <span class="m">outside limits</span>' : ''}<br><span class="m">limits ${lo.toFixed(1)} to ${hi.toFixed(1)}</span>`); }).on('mouseleave', () => tip.hide());
    f.table([{ key: 'date', label: 'Week', fmt: LV.fmt.day }, { key: 'value', label: 'Value', num: true }, { key: 'flag', label: 'Status' }], data.map(d => ({ ...d, flag: d.value < lo || d.value > hi ? 'outside limits' : 'within limits' })));
  }
});
