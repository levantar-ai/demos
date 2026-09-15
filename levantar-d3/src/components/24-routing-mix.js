LV.define({
  name: 'routingMix', group: 'agentic', title: 'Routing mix',
  summary: 'For each task type, the share of requests the adapter layer sent to each model, and the resulting cost per thousand requests. The measurement decides the tool, and this is the measurement.',
  useCases: ['Showing a client that routine work runs on the cheap model and quality held', 'Comparing cloud and local routing after a month', 'The cost page of an Application Build review'],
  demo: () => ({
    eyebrow: 'Adapter layer', title: 'Which model handled which work', models: ['Claude Sonnet 4.5', 'Claude Haiku 4.5', 'Local Llama 3'],
    data: [
      { task: 'Classification', shares: [5, 25, 70], costPerK: 0.9 },
      { task: 'Extraction', shares: [20, 60, 20], costPerK: 3.1 },
      { task: 'Summarisation', shares: [55, 40, 5], costPerK: 7.4 },
      { task: 'Customer replies', shares: [80, 20, 0], costPerK: 11.2 },
      { task: 'Code review', shares: [100, 0, 0], costPerK: 18.6 }
    ], caption: 'Shares are of requests in August 2026. Cost per thousand is measured from the bill, not from list prices.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const cat = LV.palette.categorical, w = f.width, labelW = Math.min(170, w * 0.28), costW = 92, rowH = 44, h = o.data.length * rowH + 24;
    const x = d3.scaleLinear().domain([0, 100]).range([labelW, w - costW]);
    f.legend(o.models.map((mname, i) => ({ label: mname, color: cat[i] })));
    const svg = LV.svg(f.body, w, h);
    svg.append('text').attr('class', 'lv-lbl eyebrow').attr('x', w).attr('y', 10).attr('text-anchor', 'end').attr('fill', t.ink3).text('£ per 1,000');
    const rows = svg.selectAll('g.r').data(o.data).join('g').attr('transform', (d, i) => `translate(0,${18 + i * rowH})`);
    rows.append('text').attr('class', 'lv-lbl strong').attr('x', 0).attr('y', 18).attr('font-size', 11.5).text(d => d.task);
    const seg = rows.selectAll('g.s').data(d => { let acc = 0; return d.shares.map((v, i) => { const s = { v, i, x0: acc, x1: acc + v, task: d.task }; acc += v; return s; }).filter(s => s.v > 0); }).join('g');
    seg.append('rect').attr('x', s => x(s.x0) + (s.x0 > 0 ? 2 : 0)).attr('y', 6).attr('width', s => Math.max(0, x(s.x1) - x(s.x0) - (s.x0 > 0 ? 2 : 0))).attr('height', 16).attr('rx', 2).attr('fill', s => cat[s.i]);
    seg.filter(s => LV.textWidth(s.v + '%', '10.5px ' + t.sans) + 10 < x(s.x1) - x(s.x0)).append('text').attr('x', s => (x(s.x0) + x(s.x1)) / 2).attr('y', 18).attr('text-anchor', 'middle').attr('font-size', 10.5).attr('font-weight', 600).attr('fill', s => s.i === 1 || s.i === 3 ? t.ink : t.paper).text(s => s.v + '%');
    rows.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', w).attr('y', 18).attr('text-anchor', 'end').attr('font-size', 12).text(d => '£' + d.costPerK.toFixed(2));
    const tip = LV.tooltip(f.body);
    seg.on('mousemove', (ev, s) => { const [px, py] = LV.pt(ev, f.body); tip.show(px, py, `<b>${LV.esc(s.task)}</b><br>${LV.esc(o.models[s.i])}: ${s.v}%`); }).on('mouseleave', () => tip.hide());
    f.table([{ key: 'task', label: 'Task' }].concat(o.models.map((mname, i) => ({ key: 's' + i, label: mname, num: true, fmt: v => v + '%' }))).concat([{ key: 'costPerK', label: '£ per 1,000', num: true, fmt: v => '£' + v.toFixed(2) }]), o.data.map(d => Object.assign({ task: d.task, costPerK: d.costPerK }, ...d.shares.map((v, i) => ({ ['s' + i]: v })))));
  }
});
