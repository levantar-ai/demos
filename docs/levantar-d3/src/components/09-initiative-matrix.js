LV.define({
  name: 'initiativeMatrix', group: 'value', title: 'Initiative matrix',
  summary: 'Every initiative on the roadmap placed by expected annual value against the strength of the evidence behind it, sized by budget and marked by verdict. The quadrants do the talking.',
  useCases: ['The one-page view of a Placement Assessment portfolio', 'Board pack: where the AI budget sits and how much of it is proven', 'Deciding which pilot gets instrumented next'],
  demo: () => ({
    eyebrow: 'Placement assessment', title: 'Eight initiatives by value and evidence', data: [
      { name: 'Support assistant', value: 410000, confidence: 0.85, budget: 95000, verdict: 'back' },
      { name: 'Invoice matching', value: 260000, confidence: 0.7, budget: 120000, verdict: 'back' },
      { name: 'Contract summaries', value: 210000, confidence: 0.35, budget: 84000, verdict: 'fix' },
      { name: 'Sales email drafting', value: 90000, confidence: 0.3, budget: 40000, verdict: 'fix' },
      { name: 'Meeting notes bot', value: 30000, confidence: 0.55, budget: 22000, verdict: 'stop' },
      { name: 'Chatbot on website', value: 45000, confidence: 0.15, budget: 130000, verdict: 'stop' },
      { name: 'Forecasting copilot', value: 320000, confidence: 0.2, budget: 210000, verdict: 'fix' },
      { name: 'HR policy Q&A', value: 20000, confidence: 0.6, budget: 15000, verdict: 'back' }
    ],
    caption: 'Bubble area is committed budget. Confidence is the evidence grade from the assessment, not a feeling.'
  }),
  render(el, o, width) {
    const t = LV.tokens, pv = LV.palette.verdict, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, h = Math.max(300, Math.min(420, w * 0.62)), m = { t: 18, r: 20, b: 44, l: 56 };
    const x = d3.scaleLinear().domain([0, 1]).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([0, d3.max(o.data, d => d.value) * 1.1]).nice().range([h - m.b, m.t]);
    const r = d3.scaleSqrt().domain([0, d3.max(o.data, d => d.budget)]).range([0, Math.min(34, w / 14)]);
    f.legend([{ label: 'Back', color: pv.back, shape: 'dot' }, { label: 'Fix', color: pv.fix, shape: 'dot' }, { label: 'Stop', color: pv.stop, shape: 'dot' }]);
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g'), y, w - m.r, 5).attr('transform', `translate(${m.l},0)`).selectAll('line').attr('x2', w - m.r - m.l);
    const midX = x(0.5), midY = y(y.domain()[1] / 2);
    svg.append('line').attr('x1', midX).attr('x2', midX).attr('y1', m.t).attr('y2', h - m.b).attr('stroke', t.ruleStrong);
    const q = [['Prove first', x(0.02), m.t + 12, 'start'], ['Back', x(0.98), m.t + 12, 'end'], ['Stop or simplify', x(0.02), h - m.b - 8, 'start'], ['Cheap wins', x(0.98), h - m.b - 8, 'end']];
    svg.selectAll('text.q').data(q).join('text').attr('class', 'lv-lbl eyebrow').attr('x', d => d[1]).attr('y', d => d[2]).attr('text-anchor', d => d[3]).attr('fill', t.ink3).text(d => d[0]);
    LV.axisX(svg.append('g').attr('transform', `translate(0,${h - m.b})`), d3.axisBottom(x).ticks(5).tickFormat(d3.format('.0%')).tickSize(4));
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickFormat(d => LV.fmt.gbp(d)).tickSize(0).tickPadding(8));
    svg.append('text').attr('class', 'lv-lbl muted').attr('x', w - m.r).attr('y', h - 6).attr('text-anchor', 'end').attr('font-size', 11).text('Evidence confidence →');
    svg.append('text').attr('class', 'lv-lbl muted').attr('transform', `translate(12,${m.t}) rotate(-90)`).attr('text-anchor', 'end').attr('font-size', 11).text('Expected annual value →');
    const pts = svg.selectAll('circle.p').data(o.data).join('circle').attr('class', 'p').attr('cx', d => x(d.confidence)).attr('cy', d => y(d.value)).attr('r', d => Math.max(5, r(d.budget))).attr('fill', d => pv[d.verdict]).attr('fill-opacity', .82).attr('stroke', t.surface).attr('stroke-width', 2);
    const top = o.data.slice().sort((a, b) => b.value - a.value).slice(0, 3);
    svg.selectAll('text.n').data(top).join('text').attr('class', 'lv-lbl strong').attr('x', d => x(d.confidence) + Math.max(5, r(d.budget)) + 5).attr('y', d => y(d.value) + 4).attr('font-size', 11).attr('text-anchor', d => x(d.confidence) > w * 0.72 ? 'end' : 'start').attr('dx', d => x(d.confidence) > w * 0.72 ? -(2 * Math.max(5, r(d.budget)) + 10) : 0).text(d => d.name);
    const tip = LV.tooltip(f.body), dl = d3.Delaunay.from(o.data, d => x(d.confidence), d => y(d.value));
    svg.append('rect').attr('class', 'lv-hit').attr('x', m.l).attr('y', m.t).attr('width', w - m.l - m.r).attr('height', h - m.t - m.b)
      .on('mousemove', ev => { const [px, py] = d3.pointer(ev); const i = dl.find(px, py); const d = o.data[i]; pts.attr('fill-opacity', (e, j) => j === i ? 1 : .55); tip.show(x(d.confidence), y(d.value), `<b>${LV.esc(d.name)}</b><br>${LV.fmt.gbp(d.value)} a year · ${Math.round(d.confidence * 100)}% confidence<br><span class="m">Budget ${LV.fmt.gbp(d.budget)} · verdict ${d.verdict}</span>`); })
      .on('mouseleave', () => { pts.attr('fill-opacity', .82); tip.hide(); });
    f.table([{ key: 'name', label: 'Initiative' }, { key: 'value', label: 'Annual value', num: true, fmt: LV.fmt.gbp }, { key: 'confidence', label: 'Confidence', num: true, fmt: v => Math.round(v * 100) + '%' }, { key: 'budget', label: 'Budget', num: true, fmt: LV.fmt.gbp }, { key: 'verdict', label: 'Verdict' }], o.data);
  }
});
