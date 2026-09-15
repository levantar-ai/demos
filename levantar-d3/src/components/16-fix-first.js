LV.define({
  name: 'fixFirst', group: 'security', title: 'Fix first',
  summary: 'Findings ranked by risk with effort shown beside each bar, and the cut line drawn. What to fix first is the output of a security review, so the chart is the recommendation.',
  useCases: ['The prioritised findings page of an AI Security Review', 'A sprint plan for the client\'s own engineers', 'Re-running after a quarter to show what moved below the line'],
  demo: () => ({
    eyebrow: 'AI security review', title: 'Findings ranked by risk', data: [
      { finding: 'Chatbot can be steered to reveal system prompt and internal URLs', system: 'Website chatbot', risk: 92, effort: 'low' },
      { finding: 'Invoice agent has write access to the ledger with no approval step', system: 'Invoice matching', risk: 88, effort: 'medium' },
      { finding: 'No record of which documents a summary was generated from', system: 'Contract summaries', risk: 71, effort: 'medium' },
      { finding: 'MCP server trusts tool descriptions from a third-party registry', system: 'Internal MCP server', risk: 64, effort: 'low' },
      { finding: 'Support assistant retrieves from a share containing HR files', system: 'Support assistant', risk: 58, effort: 'high' },
      { finding: 'Model version pinned nowhere, silent upgrades possible', system: 'All', risk: 41, effort: 'low' },
      { finding: 'Eval suite not run on prompt changes', system: 'Support assistant', risk: 33, effort: 'medium' }
    ], cut: 4, caption: 'Risk is likelihood times impact from the review scoring. The cut line is what fits the first sprint.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const data = o.data.slice().sort((a, b) => b.risk - a.risk), w = f.width, rowH = 46, labelW = Math.min(430, w * 0.46), cutGap = o.cut ? 18 : 0, h = data.length * rowH + cutGap + 8;
    const x = d3.scaleLinear().domain([0, 100]).range([labelW, w - 104]);
    const svg = LV.svg(f.body, w, h);
    const effortWord = { low: 'low effort', medium: 'medium effort', high: 'high effort' };
    const rows = svg.selectAll('g.r').data(data).join('g').attr('transform', (d, i) => `translate(0,${i * rowH + (o.cut && i >= o.cut ? cutGap : 0)})`);
    rows.append('text').attr('class', 'lv-lbl eyebrow').attr('x', 0).attr('y', 12).attr('fill', (d, i) => i < (o.cut || 0) ? t.teal : t.ink3).text((d, i) => String(i + 1).padStart(2, '0') + ' · ' + d.system);
    rows.append('text').attr('class', 'lv-lbl').attr('x', 0).attr('y', 28).attr('font-size', 11.5).attr('fill', t.ink).text(d => d.finding).each(function (d) { const n = d3.select(this); let s = d.finding; while (LV.textWidth(s + '…') > labelW - 12 && s.length > 8) s = s.slice(0, -2); if (s !== d.finding) n.text(s.trim() + '…'); });
    rows.append('rect').attr('x', x(0)).attr('y', 16).attr('width', x(100) - x(0)).attr('height', 12).attr('fill', t.paperWarm);
    rows.append('path').attr('d', d => LV.barPath(x(0), 16, x(d.risk) - x(0), 12, 4, 'right')).attr('fill', (d, i) => i < (o.cut || 0) ? t.teal : t.tealLift);
    rows.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', d => x(d.risk) + 6).attr('y', 26).attr('font-size', 11.5).text(d => d.risk);
    rows.append('text').attr('class', 'lv-lbl muted').attr('x', x(100) + 6).attr('y', 26).attr('font-size', 10.5).text(d => effortWord[d.effort]);
    if (o.cut) { const cy = o.cut * rowH + cutGap / 2; svg.append('line').attr('x1', 0).attr('x2', w).attr('y1', cy).attr('y2', cy).attr('stroke', t.ink).attr('stroke-width', 1); svg.append('text').attr('class', 'lv-lbl eyebrow').attr('x', w).attr('y', cy - 5).attr('text-anchor', 'end').attr('fill', t.ink).text('fix first, above this line'); }
    const tip = LV.tooltip(f.body);
    rows.on('mousemove', (ev, d) => { const [px, py] = LV.pt(ev, f.body); tip.show(px, py, `<b>${LV.esc(d.finding)}</b><br>${LV.esc(d.system)} · risk ${d.risk} · ${effortWord[d.effort]}`); }).on('mouseleave', () => tip.hide());
    f.table([{ key: 'finding', label: 'Finding' }, { key: 'system', label: 'System' }, { key: 'risk', label: 'Risk', num: true }, { key: 'effort', label: 'Effort' }], data);
  }
});
