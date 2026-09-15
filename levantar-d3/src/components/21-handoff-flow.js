LV.define({
  name: 'handoffFlow', group: 'agentic', title: 'Handoff flow',
  summary: 'How work passes between agents, systems and the humans who sign, drawn left to right with ribbon width for volume. The human checkpoints are the dark nodes, because they are the point.',
  useCases: ['The architecture page of an agent system design', 'Showing where escalation goes and who owns it', 'Volume through each handoff after a month in production'],
  demo: () => ({
    eyebrow: 'Agent system design', title: 'Support handling, who does what and who signs', nodes: [{ id: 'inbox', label: 'Inbound requests', kind: 'system' }, { id: 'triage', label: 'Triage agent', kind: 'agent' }, { id: 'refund', label: 'Refund agent', kind: 'agent' }, { id: 'account', label: 'Account agent', kind: 'agent' }, { id: 'finance', label: 'Finance approval', kind: 'human' }, { id: 'support', label: 'Support desk', kind: 'human' }, { id: 'done', label: 'Resolved', kind: 'system' }],
    links: [{ source: 'inbox', target: 'triage', value: 1200 }, { source: 'triage', target: 'refund', value: 420 }, { source: 'triage', target: 'account', value: 560 }, { source: 'triage', target: 'support', value: 220 }, { source: 'refund', target: 'finance', value: 140 }, { source: 'refund', target: 'done', value: 280 }, { source: 'finance', target: 'done', value: 140 }, { source: 'account', target: 'done', value: 500 }, { source: 'account', target: 'support', value: 60 }, { source: 'support', target: 'done', value: 280 }],
    caption: 'One week of volume. Every route to resolved passes a rule; the two human nodes are where a person signs before work continues.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, h = 320, nodeW = 12, m = { t: 12, b: 12, l: 4, r: 120 };
    const byId = new Map(o.nodes.map(n => [n.id, { ...n, in: [], out: [], layer: 0 }]));
    const links = o.links.map(l => ({ ...l, s: byId.get(l.source), tg: byId.get(l.target) }));
    links.forEach(l => { l.s.out.push(l); l.tg.in.push(l); });
    // Longest-path layering.
    const nodes = Array.from(byId.values());
    let changed = true, guard = 0; while (changed && guard++ < 50) { changed = false; links.forEach(l => { if (l.tg.layer < l.s.layer + 1) { l.tg.layer = l.s.layer + 1; changed = true; } }); }
    const L = d3.max(nodes, n => n.layer); nodes.filter(n => !n.out.length).forEach(n => n.layer = L);
    const x = d3.scaleLinear().domain([0, L]).range([m.l, w - m.r]);
    const val = n => Math.max(d3.sum(n.in, l => l.value), d3.sum(n.out, l => l.value));
    const total = d3.max(d3.groups(nodes, n => n.layer), g => d3.sum(g[1], val));
    const ky = (h - m.t - m.b - 40) / total;
    d3.groups(nodes, n => n.layer).sort((a, b) => a[0] - b[0]).forEach(([layer, ns]) => { const tot = d3.sum(ns, val) * ky + (ns.length - 1) * 14; let y0 = m.t + (h - m.t - m.b - tot) / 2; ns.forEach(n => { n.y0 = y0; n.y1 = y0 + val(n) * ky; y0 = n.y1 + 14; }); });
    nodes.forEach(n => { let a = n.y0, b = n.y0; n.out.sort((p, q) => p.tg.y0 - q.tg.y0).forEach(l => { l.sy = a + l.value * ky / 2; a += l.value * ky; }); n.in.sort((p, q) => p.s.y0 - q.s.y0).forEach(l => { l.ty = b + l.value * ky / 2; b += l.value * ky; }); });
    const svg = LV.svg(f.body, w, h);
    const path = d3.linkHorizontal().x(d => d[0]).y(d => d[1]);
    const lk = svg.selectAll('path.l').data(links).join('path').attr('class', 'l').attr('d', l => path({ source: [x(l.s.layer) + nodeW, l.sy], target: [x(l.tg.layer), l.ty] })).attr('fill', 'none').attr('stroke', l => l.tg.kind === 'human' ? t.sand : t.tealLift).attr('stroke-opacity', .6).attr('stroke-width', l => Math.max(1.5, l.value * ky));
    const ng = svg.selectAll('g.n').data(nodes).join('g').attr('transform', n => `translate(${x(n.layer)},${n.y0})`);
    ng.append('rect').attr('width', nodeW).attr('height', n => Math.max(4, n.y1 - n.y0)).attr('rx', 2).attr('fill', n => n.kind === 'human' ? t.ink : n.kind === 'agent' ? t.teal : t.ink3);
    ng.append('text').attr('class', 'lv-lbl strong').attr('x', n => n.layer === L ? -6 : nodeW + 6).attr('y', n => (n.y1 - n.y0) / 2 + 4).attr('text-anchor', n => n.layer === L ? 'end' : 'start').attr('font-size', 11).text(n => n.label);
    ng.append('text').attr('class', 'lv-lbl muted lv-num').attr('x', n => n.layer === L ? -6 : nodeW + 6).attr('y', n => (n.y1 - n.y0) / 2 + 17).attr('text-anchor', n => n.layer === L ? 'end' : 'start').attr('font-size', 10).text(n => LV.fmt.int(val(n)));
    f.legend([{ label: 'Agent', color: t.teal }, { label: 'Human checkpoint', color: t.ink }, { label: 'System', color: t.ink3 }, { label: 'Handoff to a person', color: t.sand }]);
    const tip = LV.tooltip(f.body);
    lk.on('mousemove', (ev, l) => { const [px, py] = LV.pt(ev, f.body); lk.attr('stroke-opacity', m2 => m2 === l ? .9 : .35); tip.show(px, py, `<b>${LV.esc(l.s.label)} → ${LV.esc(l.tg.label)}</b><br>${LV.fmt.int(l.value)} items`); }).on('mouseleave', () => { lk.attr('stroke-opacity', .6); tip.hide(); });
    f.table([{ key: 'source', label: 'From', fmt: v => byId.get(v).label }, { key: 'target', label: 'To', fmt: v => byId.get(v).label }, { key: 'value', label: 'Items', num: true, fmt: LV.fmt.int }], o.links);
  }
});
