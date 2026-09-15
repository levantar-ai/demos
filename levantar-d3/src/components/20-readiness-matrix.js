LV.define({
  name: 'readinessMatrix', group: 'agentic', title: 'Readiness matrix',
  summary: 'Candidate agent use-cases against the gates that have to be open before anyone would trust one: access, evidence, ownership, controls, value. Each cell is met, partial or a gap, with a verdict on the right.',
  useCases: ['The output of an Agent Readiness Session', 'Tracking gate closure across a quarter', 'The honest list of what should not be an agent'],
  demo: () => ({
    eyebrow: 'Agent readiness session', title: 'Five use-cases against five gates', gates: ['Access', 'Evidence', 'Ownership', 'Controls', 'Value'],
    rows: [
      { useCase: 'Refund handling under £200', cells: ['met', 'met', 'met', 'partial', 'met'], verdict: 'Ready' },
      { useCase: 'Supplier onboarding checks', cells: ['met', 'partial', 'gap', 'partial', 'met'], verdict: 'Not yet' },
      { useCase: 'Triage of inbound support', cells: ['met', 'met', 'met', 'met', 'partial'], verdict: 'Ready' },
      { useCase: 'Drafting board papers', cells: ['partial', 'gap', 'gap', 'gap', 'partial'], verdict: 'Not an agent' },
      { useCase: 'Monthly reconciliation', cells: ['gap', 'met', 'met', 'partial', 'met'], verdict: 'Not yet' }
    ], caption: 'Gaps are usually access, evidence and ownership rather than model capability.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, labelW = Math.min(220, w * 0.34), verdictW = 96, cellW = (w - labelW - verdictW) / o.gates.length, rowH = 40, headH = 26, h = headH + o.rows.length * rowH + 4;
    const col = { met: LV.palette.status.good, partial: t.sandDeep, gap: t.ink }, gl = { met: 'check', partial: 'tilde', gap: 'cross' };
    const svg = LV.svg(f.body, w, h);
    svg.selectAll('text.g').data(o.gates).join('text').attr('class', 'lv-lbl eyebrow').attr('x', (d, i) => labelW + i * cellW + cellW / 2).attr('y', 12).attr('text-anchor', 'middle').attr('fill', t.ink3).text(d => d);
    svg.append('text').attr('class', 'lv-lbl eyebrow').attr('x', w).attr('y', 12).attr('text-anchor', 'end').attr('fill', t.ink3).text('Verdict');
    const rows = svg.selectAll('g.r').data(o.rows).join('g').attr('transform', (d, i) => `translate(0,${headH + i * rowH})`);
    rows.append('line').attr('x1', 0).attr('x2', w).attr('y1', rowH).attr('y2', rowH).attr('stroke', t.rule);
    rows.append('text').attr('class', 'lv-lbl strong').attr('x', 0).attr('y', rowH / 2 + 4).attr('font-size', 11.5).text(d => d.useCase);
    const cells = rows.selectAll('g.c').data(d => d.cells.map((v, i) => ({ v, i, u: d.useCase, g: o.gates[i] }))).join('g').attr('transform', d => `translate(${labelW + d.i * cellW + cellW / 2},${rowH / 2})`);
    cells.append('circle').attr('r', 11).attr('fill', d => d.v === 'met' ? t.tealWash : d.v === 'partial' ? t.paperWarm : t.surface).attr('stroke', d => col[d.v]).attr('stroke-width', 1.5);
    cells.append('g').attr('transform', 'translate(-8,-8)').each(function (d) { LV.glyphG(d3.select(this), gl[d.v], col[d.v], 16); });
    rows.append('text').attr('class', 'lv-lbl strong').attr('x', w).attr('y', rowH / 2 + 4).attr('text-anchor', 'end').attr('font-size', 11.5).attr('fill', d => d.verdict === 'Ready' ? t.teal : t.ink).text(d => d.verdict);
    f.legend([{ label: 'Met', color: col.met, shape: 'ring' }, { label: 'Partial', color: col.partial, shape: 'ring' }, { label: 'Gap', color: col.gap, shape: 'ring' }]);
    const tip = LV.tooltip(f.body);
    cells.on('mousemove', (ev, d) => { const [px, py] = LV.pt(ev, f.body); tip.show(px, py, `<b>${LV.esc(d.u)}</b><br>${d.g}: ${d.v}`); }).on('mouseleave', () => tip.hide());
    f.table([{ key: 'useCase', label: 'Use-case' }].concat(o.gates.map((g, i) => ({ key: 'c' + i, label: g }))).concat([{ key: 'verdict', label: 'Verdict' }]), o.rows.map(r => Object.assign({ useCase: r.useCase, verdict: r.verdict }, ...r.cells.map((v, i) => ({ ['c' + i]: v })))));
  }
});
