LV.define({
  name: 'runOutcomes', group: 'agentic', title: 'Run outcomes',
  summary: 'Agent runs per week split into completed, escalated to a person, stopped by a guardrail and failed. Stacked columns with surface gaps, the last column labelled. The escalation share is the trust signal.',
  useCases: ['The weekly agent estate report', 'Watching the escalation share fall as controls are tuned', 'Evidence for an Agent Readiness Session that a use-case is now trusted'],
  demo: () => ({
    eyebrow: 'Agent estate', title: 'Runs per week by outcome', data: d3.range(10).map(i => ({ week: new Date(2026, 6, 6 + i * 7), completed: 640 + i * 55 + Math.round(Math.sin(i) * 30), escalated: Math.max(40, 180 - i * 14), blocked: 28 + Math.round(Math.cos(i) * 8), failed: Math.max(4, 22 - i * 2) })),
    caption: 'Escalations fell from 21% of runs to 6% over ten weeks as the refund rule was tuned. Failures are runs that ended without a defined outcome.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const keys = ['completed', 'escalated', 'blocked', 'failed'], names = { completed: 'Completed', escalated: 'Escalated to a person', blocked: 'Stopped by guardrail', failed: 'Failed' };
    const color = { completed: t.teal, escalated: t.tealLift, blocked: t.sand, failed: t.ink };
    const w = f.width, h = 300, m = { t: 26, r: 12, b: 34, l: 48 }, data = o.data;
    const x = d3.scaleBand().domain(data.map(d => +d.week)).range([m.l, w - m.r]).paddingInner(0.35).paddingOuter(0.15);
    const series = d3.stack().keys(keys)(data);
    const y = d3.scaleLinear().domain([0, d3.max(series[series.length - 1], d => d[1]) * 1.08]).nice().range([h - m.b, m.t]);
    f.legend(keys.map(k => ({ label: names[k], color: color[k] })));
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g').attr('transform', `translate(${m.l},0)`), y, w - m.r - m.l, 5);
    const bw = Math.min(24, x.bandwidth()), off = (x.bandwidth() - bw) / 2;
    svg.selectAll('g.s').data(series).join('g').attr('fill', s => color[s.key]).selectAll('path').data(s => s.map(d => ({ ...d, key: s.key }))).join('path')
      .attr('d', (d, i) => { const top = y(d[1]), bot = y(d[0]) - (d.key === 'completed' ? 0 : 2); const isTop = d.key === keys[keys.length - 1]; return isTop ? LV.barPath(x(+d.data.week) + off, top, bw, Math.max(0, bot - top), 4, 'up') : `M${x(+d.data.week) + off},${top}h${bw}v${Math.max(0, bot - top)}h${-bw}Z`; });
    const last = data[data.length - 1], tot = keys.reduce((s, k) => s + last[k], 0);
    svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(+last.week) + x.bandwidth() / 2).attr('y', y(tot) - 8).attr('text-anchor', 'middle').attr('font-size', 11.5).text(LV.fmt.int(tot) + ' runs');
    LV.axisX(svg.append('g').attr('transform', `translate(0,${h - m.b})`), d3.axisBottom(x).tickFormat(d => LV.fmt.day(new Date(d))).tickSize(4).tickValues(x.domain().filter((d, i) => i % Math.ceil(data.length / Math.floor(w / 80)) === 0)));
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickSize(0).tickPadding(8));
    const tip = LV.tooltip(f.body);
    svg.selectAll('rect.h').data(data).join('rect').attr('class', 'lv-hit').attr('x', d => x(+d.week)).attr('y', m.t).attr('width', x.bandwidth()).attr('height', h - m.t - m.b)
      .on('mousemove', (ev, d) => { const tt = keys.reduce((s, k) => s + d[k], 0); tip.show(x(+d.week) + x.bandwidth() / 2, y(tt), `<b>Week of ${LV.fmt.day(d.week)}</b><br>` + keys.map(k => `${names[k]} ${LV.fmt.int(d[k])} <span class="m">(${Math.round(d[k] / tt * 100)}%)</span>`).join('<br>')); }).on('mouseleave', () => tip.hide());
    f.table([{ key: 'week', label: 'Week', fmt: LV.fmt.day }].concat(keys.map(k => ({ key: k, label: names[k], num: true, fmt: LV.fmt.int }))), data);
  }
});
