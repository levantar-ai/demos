LV.define({
  name: 'evidenceLadder', group: 'metrics', title: 'Evidence ladder',
  summary: 'How well a claim is evidenced, on four fixed rungs: claimed, self-reported, measured, audited. Most AI business cases sit on the first rung and this makes that visible.',
  useCases: ['Grading each benefit line in an existing business case', 'The how-we-measure page: what the survey figures actually are', 'Showing the client what would move a claim up a rung'],
  demo: () => ({ label: 'Support handling time down 20%', level: 1, next: 'Record the pre-deployment baseline and compare like-for-like weeks', levels: ['Claimed', 'Self-reported', 'Measured', 'Audited'] }),
  render(el, o, width) {
    const t = LV.tokens, levels = o.levels || ['Claimed', 'Self-reported', 'Measured', 'Audited'];
    const f = LV.frame(el, { title: o.label, caption: o.next ? 'To move up a rung: ' + o.next : null, table: false });
    const w = f.width, n = levels.length, gap = 4, segW = (w - gap * (n - 1)) / n, h = 62;
    const svg = LV.svg(f.body, w, h);
    const g = svg.selectAll('g.r').data(levels).join('g').attr('class', 'r').attr('transform', (d, i) => `translate(${i * (segW + gap)},0)`);
    g.append('rect').attr('x', 0).attr('y', 8).attr('width', segW).attr('height', 12).attr('rx', 3).attr('fill', (d, i) => i <= o.level ? LV.palette.ordinal[Math.min(4, i + 1)] : t.paperWarm).attr('stroke', (d, i) => i <= o.level ? 'none' : t.rule);
    g.append('text').attr('class', 'lv-lbl').attr('x', 0).attr('y', 40).attr('font-size', 11.5).attr('font-weight', (d, i) => i === o.level ? 600 : 400).attr('fill', (d, i) => i === o.level ? t.ink : t.ink3).text(d => d);
    g.filter((d, i) => i === o.level).append('text').attr('class', 'lv-lbl eyebrow').attr('x', 0).attr('y', 56).text('current rung');
  }
});
