LV.define({
  name: 'budgetSlope', group: 'value', title: 'Budget slope',
  summary: 'Each initiative\'s budget before and after review, joined by a line. Money that moves from stop to back is the whole point of a Recovery Sprint and this shows it in one glance.',
  useCases: ['The Recovery Sprint roadmap: what was reallocated', 'A quarterly re-run of the Placement Assessment', 'Board evidence that AI spend is being managed rather than accumulated'],
  demo: () => ({
    eyebrow: 'ROI recovery sprint', title: 'AI budget before and after review', data: [
      { name: 'Support assistant', before: 95000, after: 150000, verdict: 'back' },
      { name: 'Invoice matching', before: 120000, after: 135000, verdict: 'back' },
      { name: 'Forecasting copilot', before: 210000, after: 90000, verdict: 'fix' },
      { name: 'Contract summaries', before: 84000, after: 60000, verdict: 'fix' },
      { name: 'Website chatbot', before: 130000, after: 0, verdict: 'stop' },
      { name: 'Meeting notes bot', before: 22000, after: 0, verdict: 'stop' }
    ],
    left: 'Committed', right: 'After review', caption: 'Total budget falls from £661K to £435K and the two initiatives with measured returns get more.'
  }),
  render(el, o, width) {
    const t = LV.tokens, pv = LV.palette.verdict, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, h = Math.max(280, o.data.length * 42 + 60), lw = Math.min(190, w * 0.3), m = { t: 36, b: 20 };
    const x0 = lw + 10, x1 = w - lw - 10;
    const y = d3.scaleLinear().domain([0, d3.max(o.data, d => Math.max(d.before, d.after))]).nice().range([h - m.b, m.t]);
    f.legend([{ label: 'Back', color: pv.back, shape: 'line' }, { label: 'Fix', color: pv.fix, shape: 'line' }, { label: 'Stop', color: pv.stop, shape: 'line' }]);
    const svg = LV.svg(f.body, w, h);
    [[x0, o.left || 'Before'], [x1, o.right || 'After']].forEach(([x, l], i) => {
      svg.append('line').attr('x1', x).attr('x2', x).attr('y1', m.t - 6).attr('y2', h - m.b).attr('stroke', t.rule);
      svg.append('text').attr('class', 'lv-lbl eyebrow').attr('x', x).attr('y', m.t - 16).attr('text-anchor', i ? 'end' : 'start').text(l);
    });
    // Relax label positions to avoid overlap on each side.
    const relax = (arr, key) => { const s = arr.slice().sort((a, b) => a[key] - b[key]); for (let i = 1; i < s.length; i++) if (s[i][key] - s[i - 1][key] < 15) s[i][key] = s[i - 1][key] + 15; return arr; };
    const rows = o.data.map(d => ({ ...d, ly0: y(d.before), ly1: y(d.after) }));
    relax(rows, 'ly0'); relax(rows, 'ly1');
    svg.selectAll('line.s').data(rows).join('line').attr('class', 's').attr('x1', x0).attr('x2', x1).attr('y1', d => y(d.before)).attr('y2', d => y(d.after)).attr('stroke', d => pv[d.verdict]).attr('stroke-width', 2).attr('stroke-linecap', 'round');
    svg.selectAll('circle.a').data(rows).join('circle').attr('cx', x0).attr('cy', d => y(d.before)).attr('r', 4).attr('fill', d => pv[d.verdict]).attr('stroke', t.surface).attr('stroke-width', 2);
    svg.selectAll('circle.b').data(rows).join('circle').attr('cx', x1).attr('cy', d => y(d.after)).attr('r', 4).attr('fill', d => pv[d.verdict]).attr('stroke', t.surface).attr('stroke-width', 2);
    svg.selectAll('text.l').data(rows).join('text').attr('class', 'lv-lbl').attr('x', x0 - 10).attr('y', d => d.ly0 + 4).attr('text-anchor', 'end').attr('font-size', 11.5).html(d => `${LV.esc(d.name)} <tspan class="lv-num" font-weight="600">${LV.fmt.gbp(d.before)}</tspan>`);
    svg.selectAll('text.r').data(rows).join('text').attr('class', 'lv-lbl').attr('x', x1 + 10).attr('y', d => d.ly1 + 4).attr('font-size', 11.5).html(d => `<tspan class="lv-num" font-weight="600">${d.after === 0 ? 'stopped' : LV.fmt.gbp(d.after)}</tspan> ${LV.esc(d.name)}`);
    f.table([{ key: 'name', label: 'Initiative' }, { key: 'before', label: o.left || 'Before', num: true, fmt: LV.fmt.gbpFull }, { key: 'after', label: o.right || 'After', num: true, fmt: LV.fmt.gbpFull }, { key: 'verdict', label: 'Verdict' }], o.data);
  }
});
