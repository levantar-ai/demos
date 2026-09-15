LV.define({
  name: 'exposureHeatmap', group: 'security', title: 'Exposure heatmap',
  summary: 'Every AI system in the estate against every threat class, graded on one teal ramp from none to critical. Where the estate is exposed, in a single grid the security lead can point at.',
  useCases: ['The summary grid of an AI Security Review', 'Tracking the same grid quarter on quarter as fixes land', 'Scoping which systems a guardrail programme should cover first'],
  demo: () => ({
    eyebrow: 'AI security review', title: 'Exposure by system and threat class', columns: ['Prompt injection', 'Data exfiltration', 'Tool misuse', 'Excessive agency', 'Supply chain', 'Missing audit trail'],
    rows: [
      { system: 'Support assistant', values: [3, 2, 1, 1, 1, 0] },
      { system: 'Invoice matching agent', values: [2, 3, 4, 3, 1, 2] },
      { system: 'Contract summaries', values: [2, 4, 0, 0, 2, 3] },
      { system: 'Website chatbot', values: [4, 3, 0, 1, 2, 4] },
      { system: 'Internal MCP server', values: [1, 2, 3, 2, 3, 1] }
    ],
    levels: ['None', 'Low', 'Moderate', 'High', 'Critical'],
    caption: 'Grades from the review\'s evidence, not self-assessment. A blank cell is a threat class that does not apply.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, rowLabelW = Math.min(180, w * 0.3), cols = o.columns.length, cellH = 40, headH = 54, h = headH + o.rows.length * cellH + 40;
    const cellW = (w - rowLabelW) / cols, ramp = ['#f1f5f4', '#c4e2df', '#8fcbc7', '#2f8582', t.tealDeep];
    const svg = LV.svg(f.body, w, h);
    svg.selectAll('text.c').data(o.columns).join('text').attr('class', 'lv-lbl').attr('x', (d, i) => rowLabelW + i * cellW + cellW / 2).attr('y', 14).attr('text-anchor', 'middle').attr('font-size', 10.5).text(d => d).call(LV.wrap, cellW - 8);
    const rows = svg.selectAll('g.r').data(o.rows).join('g').attr('transform', (d, i) => `translate(0,${headH + i * cellH})`);
    rows.append('text').attr('class', 'lv-lbl strong').attr('x', 0).attr('y', cellH / 2 + 4).attr('font-size', 11.5).text(d => d.system);
    const cells = rows.selectAll('g.cell').data(d => d.values.map((v, i) => ({ v, i, system: d.system, threat: o.columns[i] }))).join('g').attr('transform', d => `translate(${rowLabelW + d.i * cellW},0)`);
    cells.append('rect').attr('x', 1).attr('y', 1).attr('width', cellW - 2).attr('height', cellH - 2).attr('rx', 2).attr('fill', d => d.v == null ? t.surface : ramp[d.v]).attr('stroke', d => d.v == null ? t.rule : 'none');
    cells.filter(d => d.v != null && d.v > 0).append('text').attr('x', cellW / 2).attr('y', cellH / 2 + 4).attr('text-anchor', 'middle').attr('font-size', 10.5).attr('font-weight', 600).attr('fill', d => d.v >= 3 ? t.paper : t.ink).text(d => o.levels[d.v]);
    const tip = LV.tooltip(f.body);
    cells.on('mousemove', (ev, d) => tip.show(rowLabelW + d.i * cellW + cellW / 2, headH + o.rows.indexOf(o.rows.find(r => r.system === d.system)) * cellH, `<b>${LV.esc(d.system)}</b><br>${LV.esc(d.threat)}: ${d.v == null ? 'not applicable' : o.levels[d.v]}`)).on('mouseleave', () => tip.hide());
    const lg = svg.append('g').attr('transform', `translate(${rowLabelW},${headH + o.rows.length * cellH + 14})`);
    lg.selectAll('rect').data(o.levels).join('rect').attr('x', (d, i) => i * 18).attr('width', 16).attr('height', 10).attr('rx', 2).attr('fill', (d, i) => ramp[i]).attr('stroke', (d, i) => i === 0 ? t.rule : 'none');
    lg.append('text').attr('class', 'lv-lbl muted').attr('x', o.levels.length * 18 + 6).attr('y', 9).attr('font-size', 10.5).text(o.levels[0] + ' → ' + o.levels[o.levels.length - 1]);
    f.table([{ key: 'system', label: 'System' }].concat(o.columns.map((c, i) => ({ key: 'v' + i, label: c }))), o.rows.map(r => Object.assign({ system: r.system }, ...r.values.map((v, i) => ({ ['v' + i]: v == null ? 'n/a' : o.levels[v] })))));
  }
});
