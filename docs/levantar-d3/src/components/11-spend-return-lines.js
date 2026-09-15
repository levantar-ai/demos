LV.define({
  name: 'spendReturnLines', group: 'value', title: 'Spend and return',
  summary: 'Cumulative spend and cumulative measured return on one pound axis, with the gap between them shaded and the crossing point named. Costs that grow faster than value show up as a widening band.',
  useCases: ['Monthly tracking after an Application Build goes live', 'Recovery Sprint evidence that a project is past break-even, or never will be', 'Portfolio view with one chart per initiative as small multiples'],
  demo: () => {
    const months = LV.months(14, new Date(2025, 6, 1)); let s = 0, r = 0;
    return { eyebrow: 'Application build', title: 'Cumulative spend and measured return, invoice matching agent', data: months.map((d, i) => { s += i === 0 ? 62000 : 9000 + i * 250; r += i < 2 ? 0 : 12500 + i * 900; return { date: d, spend: s, return: r }; }), caption: 'Return is the measured monthly saving, not the forecast in the business case.' };
  },
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, h = 300, m = { t: 18, r: 90, b: 34, l: 56 }, data = o.data;
    const x = d3.scaleTime().domain(d3.extent(data, d => d.date)).range([m.l, w - m.r]);
    const y = d3.scaleLinear().domain([0, d3.max(data, d => Math.max(d.spend, d.return)) * 1.05]).nice().range([h - m.b, m.t]);
    f.legend([{ label: 'Cumulative spend', color: t.ink, shape: 'line' }, { label: 'Cumulative return', color: t.teal, shape: 'line' }, { label: 'Return behind spend', color: t.paper3 }, { label: 'Return ahead', color: t.tealWash }]);
    const svg = LV.svg(f.body, w, h);
    LV.grid(svg.append('g').attr('transform', `translate(${m.l},0)`), y, w - m.r - m.l, 5);
    const area = d3.area().x(d => x(d.date)).y0(d => y(Math.min(d.spend, d.return))).y1(d => y(Math.max(d.spend, d.return))).curve(d3.curveMonotoneX);
    const clipId = 'lvsr' + Math.random().toString(36).slice(2, 7);
    const defs = svg.append('defs');
    const line = k => d3.line().x(d => x(d.date)).y(d => y(d[k])).curve(d3.curveMonotoneX);
    defs.append('clipPath').attr('id', clipId + 'a').append('path').attr('d', d3.area().x(d => x(d.date)).y0(d => y(d.return)).y1(m.t).curve(d3.curveMonotoneX)(data));
    defs.append('clipPath').attr('id', clipId + 'b').append('path').attr('d', d3.area().x(d => x(d.date)).y0(d => y(d.spend)).y1(m.t).curve(d3.curveMonotoneX)(data));
    svg.append('path').attr('d', area(data)).attr('fill', t.paper3).attr('clip-path', `url(#${clipId}a)`);
    svg.append('path').attr('d', area(data)).attr('fill', t.tealWash).attr('clip-path', `url(#${clipId}b)`);
    svg.append('path').attr('d', line('spend')(data)).attr('fill', 'none').attr('stroke', t.ink).attr('stroke-width', 2).attr('stroke-linejoin', 'round');
    svg.append('path').attr('d', line('return')(data)).attr('fill', 'none').attr('stroke', t.teal).attr('stroke-width', 2).attr('stroke-linejoin', 'round');
    LV.axisX(svg.append('g').attr('transform', `translate(0,${h - m.b})`), d3.axisBottom(x).ticks(Math.min(7, Math.floor(w / 90))).tickFormat(LV.fmt.monthYear).tickSize(4));
    LV.axisY(svg.append('g').attr('transform', `translate(${m.l},0)`), d3.axisLeft(y).ticks(5).tickFormat(d => LV.fmt.gbp(d)).tickSize(0).tickPadding(8));
    const last = data[data.length - 1];
    svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(last.date) + 8).attr('y', y(last.spend) + 4).attr('font-size', 11).text('spend ' + LV.fmt.gbp(last.spend));
    svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(last.date) + 8).attr('y', y(last.return) + (Math.abs(y(last.return) - y(last.spend)) < 14 ? (last.return > last.spend ? -10 : 14) : 4)).attr('font-size', 11).text('return ' + LV.fmt.gbp(last.return));
    let cross = null;
    for (let i = 1; i < data.length; i++) if ((data[i - 1].return - data[i - 1].spend) < 0 && (data[i].return - data[i].spend) >= 0) { cross = data[i]; break; }
    if (cross) {
      svg.append('circle').attr('cx', x(cross.date)).attr('cy', y(cross.spend)).attr('r', 5).attr('fill', t.teal).attr('stroke', t.surface).attr('stroke-width', 2);
      svg.append('text').attr('class', 'lv-lbl serif').attr('x', x(cross.date) - 10).attr('y', y(cross.spend) - 12).attr('text-anchor', 'end').attr('font-size', 12).text('Break-even ' + LV.fmt.monthYear(cross.date));
    }
    const tip = LV.tooltip(f.body), cx = svg.append('line').attr('stroke', t.ruleStrong).attr('y1', m.t).attr('y2', h - m.b).style('display', 'none');
    const bis = d3.bisector(d => d.date).center;
    svg.append('rect').attr('class', 'lv-hit').attr('x', m.l).attr('y', m.t).attr('width', w - m.l - m.r).attr('height', h - m.t - m.b)
      .on('mousemove', ev => { const [px] = d3.pointer(ev); const d = data[bis(data, x.invert(px))]; cx.style('display', null).attr('x1', x(d.date)).attr('x2', x(d.date)); tip.show(x(d.date), y(Math.max(d.spend, d.return)), `<b>${LV.fmt.monthYear(d.date)}</b><br>Spend ${LV.fmt.gbpFull(d.spend)}<br>Return ${LV.fmt.gbpFull(d.return)}<br><span class="m">net ${LV.fmt.signed(d.return - d.spend, LV.fmt.gbpFull)}</span>`); })
      .on('mouseleave', () => { cx.style('display', 'none'); tip.hide(); });
    f.table([{ key: 'date', label: 'Month', fmt: LV.fmt.monthYear }, { key: 'spend', label: 'Cumulative spend', num: true, fmt: LV.fmt.gbpFull }, { key: 'return', label: 'Cumulative return', num: true, fmt: LV.fmt.gbpFull }], data);
  }
});
