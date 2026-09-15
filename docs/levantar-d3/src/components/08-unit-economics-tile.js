LV.define({
  name: 'unitEconomicsTile', group: 'metrics', title: 'Unit economics tile',
  summary: 'Cost per outcome as the headline, with the two inputs that make it beside it and a sparkline of the ratio. The number that tells you whether cost is growing faster than value.',
  useCases: ['£ per resolved ticket for a support assistant', '£ per matched invoice for a finance agent', 'Tokens and dollars per accepted pull request for a coding agent'],
  demo: () => ({
    label: 'Cost per matched invoice', outcomeLabel: 'invoices matched', period: 'August 2026', cost: 4120, outcomes: 3160,
    history: [{ cost: 3900, outcomes: 1800 }, { cost: 4050, outcomes: 2100 }, { cost: 4300, outcomes: 2650 }, { cost: 4200, outcomes: 2900 }, { cost: 4180, outcomes: 3020 }, { cost: 4120, outcomes: 3160 }]
  }),
  render(el, o) {
    const t = LV.tokens, per = o.cost / o.outcomes;
    const div = document.createElement('div');
    div.className = 'lv-stat teal';
    div.innerHTML = `<div class="label">${LV.esc(o.label)}</div><div class="row"><div><div class="num">£${per.toFixed(2)}</div></div><div class="spark"></div></div>` +
      `<div class="sub" style="display:flex;gap:18px;margin-top:12px;font-variant-numeric:tabular-nums;"><span><b style="color:var(--ink);font-weight:600">${LV.fmt.gbpFull(o.cost)}</b> spent</span><span><b style="color:var(--ink);font-weight:600">${LV.fmt.int(o.outcomes)}</b> ${LV.esc(o.outcomeLabel)}</span><span>${LV.esc(o.period)}</span></div>`;
    el.appendChild(div);
    const hist = (o.history || []).map(d => d.cost / d.outcomes);
    if (hist.length > 1) {
      const w = 120, h = 40, x = d3.scaleLinear().domain([0, hist.length - 1]).range([2, w - 6]), y = d3.scaleLinear().domain(d3.extent(hist)).nice().range([h - 6, 4]);
      const svg = d3.select(div.querySelector('.spark')).append('svg').attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`);
      svg.append('path').attr('d', d3.line().x((d, i) => x(i)).y(d => y(d)).curve(d3.curveMonotoneX)(hist)).attr('fill', 'none').attr('stroke', t.tealLift).attr('stroke-width', 2).attr('stroke-linecap', 'round');
      svg.append('circle').attr('cx', x(hist.length - 1)).attr('cy', y(hist[hist.length - 1])).attr('r', 4).attr('fill', t.teal).attr('stroke', t.surface).attr('stroke-width', 2);
    }
  }
});
