LV.define({
  name: 'assumptionTree', group: 'value', title: 'Assumption tree',
  summary: 'What has to be true for an initiative to pay, drawn as a tree from the claim down to the testable assumptions, each marked true, untested or false. A verdict with the reasoning attached.',
  useCases: ['The core artefact of a Placement Assessment', 'Turning a vague business case into a list of things to measure', 'Explaining why a stop verdict is a stop verdict'],
  demo: () => ({
    eyebrow: 'Placement assessment', title: 'What has to be true', root: { name: 'Contract summaries save 400 legal hours a year', status: 'untested', children: [
      { name: 'Lawyers use it on most contracts', status: 'false', children: [{ name: 'It is in the review workflow', status: 'false' }, { name: 'Summaries are trusted', status: 'untested' }] },
      { name: 'A summary saves 40 minutes', status: 'untested', children: [{ name: 'Baseline time recorded', status: 'false' }, { name: 'Summaries are accurate enough', status: 'true' }] },
      { name: 'Run cost stays under £2 a contract', status: 'true', children: [{ name: 'Context fits one call', status: 'true' }] }
    ] },
    caption: 'Two of the three legs rest on assumptions nobody has tested. That, not the model, is why the verdict is fix.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const root = d3.hierarchy(o.root), leaves = root.leaves().length, depth = root.height + 1;
    const w = f.width, rowH = 34, h = Math.max(160, leaves * rowH + 40), labelW = Math.min(230, (w - 20) / depth - 40);
    const tree = d3.tree().size([h - 30, w - labelW - 40]);
    tree(root);
    const svg = LV.svg(f.body, w, h), g = svg.append('g').attr('transform', 'translate(20,15)');
    const col = { true: LV.palette.status.good, untested: t.ink3, false: t.ink }, gl = { true: 'check', untested: 'dot', false: 'cross' }, word = { true: 'holds', untested: 'untested', false: 'does not hold' };
    const labelEnd = d => d.y + 16 + Math.min(labelW, LV.textWidth(d.data.name, (d.depth === 0 ? '600 ' : '') + '11.5px ' + t.sans)) + 8;
    g.selectAll('path.l').data(root.links()).join('path').attr('class', 'l').attr('fill', 'none').attr('stroke', t.ruleStrong).attr('d', d => d3.linkHorizontal().x(p => p[0]).y(p => p[1])({ source: [labelEnd(d.source), d.source.x], target: [d.target.y - 12, d.target.x] }));
    const n = g.selectAll('g.n').data(root.descendants()).join('g').attr('class', 'n').attr('transform', d => `translate(${d.y},${d.x})`);
    n.append('circle').attr('r', 11).attr('fill', t.surface).attr('stroke', d => col[d.data.status]).attr('stroke-width', 1.5);
    n.append('g').attr('transform', 'translate(-8,-8)').each(function (d) { LV.glyphG(d3.select(this), gl[d.data.status], col[d.data.status], 16); });
    n.append('text').attr('class', 'lv-lbl').attr('x', 16).attr('y', 4).attr('font-size', 11.5).attr('font-weight', d => d.depth === 0 ? 600 : 400).attr('fill', d => d.depth === 0 ? t.ink : t.ink2).text(d => d.data.name).call(LV.wrap, labelW);
    n.filter(d => d.depth === 0).append('text').attr('class', 'lv-lbl eyebrow').attr('x', 16).attr('y', -12).text('the claim');
    f.legend([{ label: 'Holds', color: col.true, shape: 'ring' }, { label: 'Untested', color: col.untested, shape: 'ring' }, { label: 'Does not hold', color: col.false, shape: 'ring' }]);
    f.table([{ key: 'name', label: 'Assumption', fmt: (v, r) => '  '.repeat(r.depth) + v }, { key: 'status', label: 'Status', fmt: v => word[v] }], root.descendants().map(d => ({ name: d.data.name, status: d.data.status, depth: d.depth })));
  }
});
