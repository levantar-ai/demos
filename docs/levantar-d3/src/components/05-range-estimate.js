LV.define({
  name: 'rangeEstimate', group: 'metrics', title: 'Range estimate',
  summary: 'A claimed figure shown with its honest range, low to high, and the line it has to clear. An effect you cannot size is an effect you cannot defend at budget time.',
  useCases: ['Annual value of an initiative against its run cost', 'Hours saved per week, as claimed versus as measured', 'Expected payback against the board\'s threshold'],
  demo: () => ({
    label: 'Annual value, document intake automation', low: 96000, central: 210000, high: 340000,
    threshold: { value: 150000, label: 'Run cost' }, fmt: v => LV.fmt.gbp(v),
    note: 'Central case is the team\'s estimate. Low case uses the measured throughput from the six-week pilot.'
  }),
  render(el, o, width) {
    const t = LV.tokens, fmt = o.fmt || LV.fmt.compact, f = LV.frame(el, { title: o.label, caption: o.note });
    const w = f.width, h = 96;
    const svg = LV.svg(f.body, w, h);
    const lo = Math.min(o.low, o.threshold ? o.threshold.value : o.low), hi = Math.max(o.high, o.threshold ? o.threshold.value : o.high);
    const x = d3.scaleLinear().domain([lo, hi]).nice().range([12, w - 12]);
    const yC = 48;
    svg.append('line').attr('x1', x.range()[0]).attr('x2', x.range()[1]).attr('y1', yC).attr('y2', yC).attr('stroke', t.rule);
    svg.append('rect').attr('x', x(o.low)).attr('y', yC - 6).attr('width', x(o.high) - x(o.low)).attr('height', 12).attr('rx', 4).attr('fill', t.tealLift).attr('opacity', .55);
    svg.append('circle').attr('cx', x(o.central)).attr('cy', yC).attr('r', 7).attr('fill', t.teal).attr('stroke', t.surface).attr('stroke-width', 2);
    svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(o.central)).attr('y', yC - 16).attr('text-anchor', 'middle').attr('font-size', 18).attr('letter-spacing', '-0.02em').text(fmt(o.central));
    svg.append('text').attr('class', 'lv-lbl muted').attr('x', x(o.low)).attr('y', yC + 26).attr('text-anchor', x(o.low) < 40 ? 'start' : 'middle').attr('font-size', 11).text('low ' + fmt(o.low));
    svg.append('text').attr('class', 'lv-lbl muted').attr('x', x(o.high)).attr('y', yC + 26).attr('text-anchor', x(o.high) > w - 40 ? 'end' : 'middle').attr('font-size', 11).text('high ' + fmt(o.high));
    if (o.threshold) {
      const tx = x(o.threshold.value);
      svg.append('line').attr('x1', tx).attr('x2', tx).attr('y1', yC - 22).attr('y2', yC + 12).attr('stroke', t.ink).attr('stroke-width', 1.5);
      svg.append('text').attr('class', 'lv-lbl strong').attr('x', tx).attr('y', yC + 42).attr('text-anchor', 'middle').attr('font-size', 11).text(o.threshold.label + ' ' + fmt(o.threshold.value));
    }
    f.table([{ key: 'k', label: 'Case' }, { key: 'v', label: 'Value', num: true, fmt }], [{ k: 'Low', v: o.low }, { k: 'Central', v: o.central }, { k: 'High', v: o.high }].concat(o.threshold ? [{ k: o.threshold.label, v: o.threshold.value }] : []));
  }
});
