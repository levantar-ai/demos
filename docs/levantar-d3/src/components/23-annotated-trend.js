LV.define({
  name: 'annotatedTrend', group: 'agentic', title: 'Annotated trend',
  summary: 'A cost or usage line with the decisions that shaped it written on the chart: the model swap, the caching change, the day the prompt doubled. Costs that grow faster than value are a story, and this tells it.',
  useCases: ['Daily model spend through an adapter layer that routes to the right model at the right cost', 'Explaining a cost spike in under an hour, the thing only one in five organisations can do', 'Token usage per feature in an Application Build'],
  demo: () => {
    const days = d3.range(60).map(i => new Date(2026, 6, 1 + i));
    return { eyebrow: 'Cost', title: 'Daily model spend, support assistant', unit: '£', data: days.map((d, i) => ({ date: d, value: +(i < 18 ? 210 + i * 6 + Math.sin(i) * 12 : i < 34 ? 330 + (i - 18) * 14 + Math.cos(i) * 15 : i < 46 ? 190 + Math.sin(i) * 10 : 120 + Math.sin(i) * 8).toFixed(0) })), events: [{ date: days[18], label: 'Retrieval added, prompt doubles' }, { date: days[34], label: 'Routine calls moved to Haiku' }, { date: days[46], label: 'Prompt caching on' }], caption: 'Daily model spend for one assistant. Each annotation is a change the team made; the line is what it cost.' };
  },
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, h = 300, m = { t: 34, r: 60, b: 34, l: 48 }, data = o.data;
    const x = d3.scaleTime().domain(d3.extent(data, d => d.date)).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([0, d3.max(data, d => d.value) * 1.12]).nice().range([h - m.b, m.t]);
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g').attr('transform', `translate(${m.l},0)`), y, w - m.r - m.l, 5);
    svg.append('path').attr('d', d3.area().x(d => x(d.date)).y0(y(0)).y1(d => y(d.value)).curve(d3.curveMonotoneX)(data)).attr('fill', t.teal).attr('opacity', .08);
    svg.append('path').attr('d', d3.line().x(d => x(d.date)).y(d => y(d.value)).curve(d3.curveMonotoneX)(data)).attr('fill', 'none').attr('stroke', t.teal).attr('stroke-width', 2).attr('stroke-linejoin', 'round');
    const last = data[data.length - 1];
    svg.append('circle').attr('cx', x(last.date)).attr('cy', y(last.value)).attr('r', 4).attr('fill', t.teal).attr('stroke', t.surface).attr('stroke-width', 2);
    svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(last.date) + 8).attr('y', y(last.value) + 4).attr('font-size', 11.5).text((o.unit || '') + LV.fmt.int(last.value));
    const ev = svg.selectAll('g.ev').data(o.events || []).join('g').attr('transform', e => `translate(${x(e.date)},0)`);
    ev.append('line').attr('y1', m.t - 4).attr('y2', h - m.b).attr('stroke', t.ink).attr('stroke-width', 1);
    ev.append('circle').attr('cy', m.t - 4).attr('r', 3).attr('fill', t.ink);
    ev.append('text').attr('class', 'lv-lbl serif').attr('x', 6).attr('y', m.t - 12 + ((e, i) => 0)()).attr('font-size', 12).text(e => e.label).each(function (e, i) { const n = d3.select(this), room = w - m.r - x(e.date) - 8; if (LV.textWidth(e.label, '12px ' + t.serif) > room) n.attr('text-anchor', 'end').attr('x', -6); n.attr('y', m.t - 12 - (i % 2) * 0); });
    LV.axisX(svg.append('g').attr('transform', `translate(0,${h - m.b})`), d3.axisBottom(x).ticks(Math.min(8, Math.floor(w / 90))).tickFormat(LV.fmt.day).tickSize(4));
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickFormat(d => (o.unit || '') + LV.fmt.compact(d)).tickSize(0).tickPadding(8));
    const tip = LV.tooltip(f.body), cx = svg.append('line').attr('stroke', t.ruleStrong).attr('y1', m.t).attr('y2', h - m.b).style('display', 'none'), bis = d3.bisector(d => d.date).center;
    svg.append('rect').attr('class', 'lv-hit').attr('x', m.l).attr('y', m.t).attr('width', w - m.l - m.r).attr('height', h - m.t - m.b)
      .on('mousemove', ev2 => { const [px] = d3.pointer(ev2); const d = data[bis(data, x.invert(px))]; cx.style('display', null).attr('x1', x(d.date)).attr('x2', x(d.date)); tip.show(x(d.date), y(d.value), `<b>${LV.fmt.day(d.date)}</b><br>${(o.unit || '') + LV.fmt.int(d.value)}`); }).on('mouseleave', () => { cx.style('display', 'none'); tip.hide(); });
    f.table([{ key: 'date', label: 'Day', fmt: LV.fmt.day }, { key: 'value', label: 'Value', num: true, fmt: v => (o.unit || '') + LV.fmt.int(v) }], data);
  }
});
