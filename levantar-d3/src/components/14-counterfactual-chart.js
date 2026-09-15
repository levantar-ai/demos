LV.define({
  name: 'counterfactualChart', group: 'value', title: 'Counterfactual chart',
  summary: 'The metric as observed against what it would have done without AI, from a baseline fitted before go-live. The shaded gap is the attributable effect, with its uncertainty band shown rather than hidden.',
  useCases: ['Attributing a fall in handling time to the assistant, not to the headcount change the same quarter', 'The 39% problem: turning "some EBIT movement" into a sized effect', 'Evidence page in a Recovery Sprint report'],
  demo: () => {
    const months = LV.months(16, new Date(2025, 4, 1)), go = 8;
    return { golive: months[go], metric: 'Average handling time (min)', data: months.map((d, i) => { const base = 14.2 - i * 0.12 + Math.sin(i) * 0.25; const act = i < go ? base : base - Math.min(2.6, (i - go + 1) * 0.55) + Math.cos(i) * 0.15; return { date: d, actual: +act.toFixed(2), baseline: +base.toFixed(2), lo: +(base - 0.15 - (i >= go ? (i - go) * 0.09 : 0)).toFixed(2), hi: +(base + 0.15 + (i >= go ? (i - go) * 0.09 : 0)).toFixed(2) }; }), caption: 'Baseline is a linear trend fitted to the eight months before go-live, with its widening error band. Attribution is the gap, not the whole drop.' };
  },
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title || o.metric, caption: o.caption });
    const w = f.width, h = 300, m = { t: 22, r: 100, b: 34, l: 44 }, data = o.data;
    const x = d3.scaleTime().domain(d3.extent(data, d => d.date)).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([d3.min(data, d => Math.min(d.actual, d.lo)) * 0.9, d3.max(data, d => Math.max(d.actual, d.hi)) * 1.05]).nice().range([h - m.b, m.t]);
    f.legend([{ label: 'Observed', color: t.teal, shape: 'line' }, { label: 'Counterfactual baseline', color: t.ink3, shape: 'line' }, { label: 'Baseline uncertainty', color: t.paper3 }, { label: 'Attributed to AI', color: t.tealWash }]);
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g').attr('transform', `translate(${m.l},0)`), y, w - m.r - m.l, 5);
    const after = data.filter(d => d.date >= o.golive);
    svg.append('path').attr('d', d3.area().x(d => x(d.date)).y0(d => y(d.lo)).y1(d => y(d.hi)).curve(d3.curveMonotoneX)(data)).attr('fill', t.paper3).attr('opacity', .8);
    svg.append('path').attr('d', d3.area().x(d => x(d.date)).y0(d => y(d.actual)).y1(d => y(d.baseline)).curve(d3.curveMonotoneX)(after)).attr('fill', t.tealWash);
    svg.append('path').attr('d', d3.line().x(d => x(d.date)).y(d => y(d.baseline)).curve(d3.curveMonotoneX)(data)).attr('fill', 'none').attr('stroke', t.ink3).attr('stroke-width', 2).attr('stroke-dasharray', '5 4');
    svg.append('path').attr('d', d3.line().x(d => x(d.date)).y(d => y(d.actual)).curve(d3.curveMonotoneX)(data)).attr('fill', 'none').attr('stroke', t.teal).attr('stroke-width', 2).attr('stroke-linejoin', 'round');
    svg.append('line').attr('x1', x(o.golive)).attr('x2', x(o.golive)).attr('y1', m.t - 4).attr('y2', h - m.b).attr('stroke', t.ink).attr('stroke-width', 1);
    svg.append('text').attr('class', 'lv-lbl eyebrow').attr('x', x(o.golive) + 6).attr('y', m.t + 4).text('go-live');
    const last = data[data.length - 1], gap = last.baseline - last.actual;
    svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(last.date) + 8).attr('y', y((last.actual + last.baseline) / 2) + 4).attr('font-size', 11).text(LV.fmt.signed(-gap, v => v.toFixed(1)) + ' attributed');
    LV.axisX(svg.append('g').attr('transform', `translate(0,${h - m.b})`), d3.axisBottom(x).ticks(Math.min(8, Math.floor(w / 90))).tickFormat(LV.fmt.monthYear).tickSize(4));
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickSize(0).tickPadding(8));
    const tip = LV.tooltip(f.body), cx = svg.append('line').attr('stroke', t.ruleStrong).attr('y1', m.t).attr('y2', h - m.b).style('display', 'none'), bis = d3.bisector(d => d.date).center;
    svg.append('rect').attr('class', 'lv-hit').attr('x', m.l).attr('y', m.t).attr('width', w - m.l - m.r).attr('height', h - m.t - m.b)
      .on('mousemove', ev => { const [px] = d3.pointer(ev); const d = data[bis(data, x.invert(px))]; cx.style('display', null).attr('x1', x(d.date)).attr('x2', x(d.date)); tip.show(x(d.date), y(d.actual), `<b>${LV.fmt.monthYear(d.date)}</b><br>Observed ${d.actual}<br>Baseline ${d.baseline} <span class="m">(${d.lo} to ${d.hi})</span>${d.date >= o.golive ? `<br><span class="m">attributed ${LV.fmt.signed(-(d.baseline - d.actual), v => v.toFixed(2))}</span>` : ''}`); })
      .on('mouseleave', () => { cx.style('display', 'none'); tip.hide(); });
    f.table([{ key: 'date', label: 'Month', fmt: LV.fmt.monthYear }, { key: 'actual', label: 'Observed', num: true }, { key: 'baseline', label: 'Baseline', num: true }, { key: 'lo', label: 'Low', num: true }, { key: 'hi', label: 'High', num: true }], data);
  }
});
