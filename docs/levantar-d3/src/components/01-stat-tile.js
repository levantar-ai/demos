LV.define({
  name: 'statTile', group: 'metrics', title: 'Stat tile',
  summary: 'The brand stat card with an optional delta against a named period and a twelve-point sparkline. One teal tile per row marks the key figure.',
  useCases: ['Headline figures at the top of an ROI Recovery Sprint report', 'Weekly agent estate summary: runs, escalations, cost', 'Any client dashboard where four numbers need to sit side by side'],
  demo: () => ({
    label: 'Cost per resolved ticket', value: 1.84, unit: '£', sub: 'Support assistant, last 30 days', key: true,
    delta: { value: -22, vs: 'previous 30 days', upIsGood: false, fmt: v => v + '%' },
    trend: [2.9, 2.7, 2.8, 2.6, 2.4, 2.5, 2.3, 2.1, 2.2, 2.0, 1.9, 1.84]
  }),
  render(el, o) {
    const t = LV.tokens, fmtV = o.fmt || (v => (o.unit || '') + (typeof v === 'number' ? (Number.isInteger(v) ? LV.fmt.int(v) : v.toFixed(2)) : v));
    const good = o.delta ? (o.delta.value === 0 ? 'flat' : ((o.delta.value > 0) === (o.delta.upIsGood !== false) ? 'good' : 'bad')) : '';
    const glyph = o.delta ? (o.delta.value > 0 ? 'arrowUp' : o.delta.value < 0 ? 'arrowDown' : 'tilde') : '';
    const div = document.createElement('div');
    div.className = 'lv-stat' + (o.key ? ' teal' : '');
    div.innerHTML = `<div class="label">${LV.esc(o.label)}</div><div class="row"><div><div class="num">${LV.esc(fmtV(o.value))}${o.suffix ? `<small>${LV.esc(o.suffix)}</small>` : ''}</div>` +
      (o.delta ? `<div class="delta ${good}">${LV.glyphSvg(glyph, 'currentColor', 13)}${LV.esc(LV.fmt.signed(o.delta.value, o.delta.fmt))} <span>vs ${LV.esc(o.delta.vs)}</span></div>` : '') +
      `</div><div class="spark"></div></div>${o.sub ? `<div class="sub">${LV.esc(o.sub)}</div>` : ''}`;
    el.appendChild(div);
    if (o.trend && o.trend.length > 1) {
      const w = 96, h = 34, x = d3.scaleLinear().domain([0, o.trend.length - 1]).range([2, w - 6]);
      const y = d3.scaleLinear().domain(d3.extent(o.trend)).nice().range([h - 6, 4]);
      const svg = d3.select(div.querySelector('.spark')).append('svg').attr('width', w).attr('height', h).attr('viewBox', `0 0 ${w} ${h}`).attr('aria-label', 'trend');
      svg.append('path').attr('d', d3.line().x((d, i) => x(i)).y(d => y(d)).curve(d3.curveMonotoneX)(o.trend)).attr('fill', 'none').attr('stroke', t.tealLift).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
      const last = o.trend.length - 1;
      svg.append('circle').attr('cx', x(last)).attr('cy', y(o.trend[last])).attr('r', 4).attr('fill', t.teal).attr('stroke', t.surface).attr('stroke-width', 2);
    }
  }
});
