LV.define({
  name: 'runTimeline', group: 'security', title: 'Run timeline',
  summary: 'One agent run, second by second, on lanes for prompts, tool calls, guardrails and human approval. The audit trail as a picture: what the agent actually did and where it was stopped or asked.',
  useCases: ['Explaining an unexpected outcome to the people who own the process', 'Evidence that the approval step fired before the write', 'A guardrails and evaluation design workshop, walking through a real trace'],
  demo: () => ({
    eyebrow: 'Audit trail', title: 'Run 4f2a · refund request, 15 seconds end to end', lanes: ['Prompt', 'Tool call', 'Guardrail', 'Human'],
    events: [
      { t: 0, dur: 1.2, lane: 'Prompt', label: 'Customer asks for refund on order 8841' },
      { t: 1.4, dur: 0.8, lane: 'Tool call', label: 'get_order(8841)' },
      { t: 2.5, dur: 0.3, lane: 'Guardrail', label: 'Input check passed', status: 'pass' },
      { t: 3.0, dur: 1.1, lane: 'Tool call', label: 'get_policy(refunds)' },
      { t: 4.6, dur: 0.4, lane: 'Guardrail', label: 'Refund over £200 needs approval', status: 'hit' },
      { t: 5.2, dur: 6.5, lane: 'Human', label: 'Approval requested from finance', status: 'approved' },
      { t: 12.0, dur: 0.9, lane: 'Tool call', label: 'issue_refund(8841, £240)' },
      { t: 13.2, dur: 1.5, lane: 'Prompt', label: 'Reply drafted and sent' }
    ], caption: 'Guardrail hits and human approvals carry a glyph so they stand out in print as well as on screen.'
  }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { eyebrow: o.eyebrow, title: o.title, caption: o.caption });
    const w = f.width, laneH = 40, labelW = 76, m = { t: 8, b: 30 }, h = m.t + o.lanes.length * laneH + m.b;
    const tmax = d3.max(o.events, d => d.t + (d.dur || 0)) * 1.04;
    const x = d3.scaleLinear().domain([0, tmax]).range([labelW, w - 8]);
    const yl = d3.scaleBand().domain(o.lanes).range([m.t, m.t + o.lanes.length * laneH]);
    const svg = LV.svg(f.body, w, h);
    const lanes = svg.selectAll('g.lane').data(o.lanes).join('g').attr('transform', d => `translate(0,${yl(d)})`);
    lanes.append('line').attr('x1', labelW).attr('x2', w - 8).attr('y1', laneH / 2).attr('y2', laneH / 2).attr('stroke', t.rule);
    lanes.append('text').attr('class', 'lv-lbl eyebrow').attr('x', 0).attr('y', laneH / 2 + 3).attr('fill', t.ink3).text(d => d);
    const fill = d => d.lane === 'Human' ? t.ink : d.status === 'hit' ? t.sandDeep : d.lane === 'Tool call' ? t.teal : t.tealLift;
    const ev = svg.selectAll('g.e').data(o.events).join('g').attr('transform', d => `translate(${x(d.t)},${yl(d.lane) + laneH / 2})`);
    ev.append('rect').attr('x', 0).attr('y', -8).attr('width', d => Math.max(6, x(d.t + (d.dur || 0)) - x(d.t))).attr('height', 16).attr('rx', 3).attr('fill', fill);
    ev.filter(d => d.status === 'hit' || d.lane === 'Human').append('g').attr('transform', d => `translate(${Math.max(6, x(d.t + (d.dur || 0)) - x(d.t)) + 5},-8)`).each(function (d) { LV.glyphG(d3.select(this), d.lane === 'Human' ? 'human' : 'flag', fill(d), 16); });
    const barEnd = d => x(d.t) + Math.max(6, x(d.t + (d.dur || 0)) - x(d.t));
    const nextIn = d => { const later = o.events.filter(e => e.lane === d.lane && e.t > d.t).sort((a, b) => a.t - b.t)[0]; return later ? x(later.t) : w - 8; };
    const prevEnd = d => { const before = o.events.filter(e => e.lane === d.lane && e.t < d.t).sort((a, b) => b.t - a.t)[0]; return before ? barEnd(before) : labelW; };
    ev.append('text').attr('class', 'lv-lbl').attr('y', 4).attr('font-size', 10.5).attr('fill', t.ink2).each(function (d) {
      const n = d3.select(this), gl = (d.status === 'hit' || d.lane === 'Human') ? 18 : 0, font = '10.5px ' + t.sans, need = LV.textWidth(d.label, font);
      const roomR = nextIn(d) - barEnd(d) - 8 - gl, roomL = x(d.t) - prevEnd(d) - 10;
      let s = d.label, room = roomR, anchor = 'start', px = barEnd(d) - x(d.t) + 6 + gl;
      if (need > roomR && roomL > roomR) { room = roomL; anchor = 'end'; px = -6; }
      while (LV.textWidth(s + '…', font) > room && s.length > 6) s = s.slice(0, -2);
      if (s !== d.label) s = s.trim() + '…';
      if (room < 28) s = '';
      n.attr('x', px).attr('text-anchor', anchor).text(s);
    });
    LV.axisX(svg.append('g').attr('transform', `translate(0,${m.t + o.lanes.length * laneH + 6})`), d3.axisBottom(x).ticks(6).tickFormat(d => d + 's').tickSize(4));
    f.legend([{ label: 'Prompt or reply', color: t.tealLift }, { label: 'Tool call', color: t.teal }, { label: 'Guardrail hit', color: t.sandDeep }, { label: 'Human approval', color: t.ink }]);
    const tip = LV.tooltip(f.body);
    ev.on('mousemove', (ev2, d) => tip.show(x(d.t), yl(d.lane) + 10, `<b>${LV.esc(d.label)}</b><br>${d.lane} · ${d.t}s${d.dur ? ' for ' + d.dur + 's' : ''}${d.status ? ' · ' + d.status : ''}`)).on('mouseleave', () => tip.hide());
    f.table([{ key: 't', label: 'Start (s)', num: true }, { key: 'dur', label: 'Duration (s)', num: true }, { key: 'lane', label: 'Lane' }, { key: 'label', label: 'Event' }, { key: 'status', label: 'Status' }], o.events);
  }
});
