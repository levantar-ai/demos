LV.define({
  name: 'guardrailFunnel', group: 'security', title: 'Guardrail funnel',
  summary: 'Requests through each control in order, with the count stopped at every stage. Shows that the guardrails do something, and how much of the traffic they touch.',
  useCases: ['Weekly reporting on a guardrail and evaluation design engagement', 'Justifying the review step to a team who thinks it slows everything down', 'Spotting a stage that blocks nothing and may be misconfigured'],
  demo: () => ({
    eyebrow: 'Guardrails', title: 'Requests through each control, one week', stages: [{ label: 'Requests received', count: 18420 }, { label: 'Passed input guardrail', count: 17960 }, { label: 'Answered by the model', count: 17410 }, { label: 'Passed output guardrail', count: 17015 }, { label: 'Delivered without human review', count: 16380 }],
    caption: 'Numbers for the week to 12 September 2026. Stopped requests are logged with the rule that fired.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, rowH = 50, labelW = Math.min(230, w * 0.38), h = o.stages.length * rowH + 4, first = o.stages[0].count;
    const x = d3.scaleLinear().domain([0, first]).range([labelW, w - 110]);
    const ramp = LV.palette.ordinal, svg = LV.svg(f.body, w, h);
    const rows = svg.selectAll('g.r').data(o.stages).join('g').attr('transform', (d, i) => `translate(0,${i * rowH})`);
    rows.append('text').attr('class', 'lv-lbl').attr('x', 0).attr('y', 22).attr('font-size', 11.5).attr('fill', t.ink).text(d => d.label).call(LV.wrap, labelW - 14);
    rows.append('rect').attr('x', x(0)).attr('y', 12).attr('width', x(first) - x(0)).attr('height', 14).attr('fill', t.paperWarm);
    rows.append('path').attr('d', d => LV.barPath(x(0), 12, x(d.count) - x(0), 14, 4, 'right')).attr('fill', (d, i) => ramp[Math.min(ramp.length - 1, Math.round(i * (ramp.length - 1) / Math.max(1, o.stages.length - 1)))]);
    rows.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', d => x(d.count) + 8).attr('y', 24).attr('font-size', 12).text(d => LV.fmt.int(d.count));
    rows.append('text').attr('class', 'lv-lbl muted lv-num').attr('x', w).attr('y', 24).attr('text-anchor', 'end').attr('font-size', 11).text(d => LV.fmt.pct(d.count / first * 100, 1));
    rows.filter((d, i) => i > 0).append('text').attr('class', 'lv-lbl muted lv-num').attr('x', x(0)).attr('y', 4).attr('font-size', 10).attr('fill', t.sandDeep).text((d, i) => '−' + LV.fmt.int(o.stages[i].count - d.count) + ' stopped');
    f.table([{ key: 'label', label: 'Stage' }, { key: 'count', label: 'Requests', num: true, fmt: LV.fmt.int }, { key: 'share', label: 'Of received', num: true, fmt: v => LV.fmt.pct(v, 1) }], o.stages.map(s => ({ ...s, share: s.count / first * 100 })));
  }
});
