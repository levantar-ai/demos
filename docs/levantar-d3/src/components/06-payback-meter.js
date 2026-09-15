LV.define({
  name: 'paybackMeter', group: 'metrics', title: 'Payback meter',
  summary: 'Months to break even on a fixed horizon, with the point the money comes back marked. If payback lands beyond the horizon the track says so instead of pretending.',
  useCases: ['Build cost against measured monthly return for an application build', 'Comparing two initiatives on the same 24-month horizon', 'Showing a board that the pilot pays back inside the year, or does not'],
  demo: () => ({ label: 'Invoice matching agent', spend: 120000, monthlyReturn: 11500, horizonMonths: 24, note: 'Spend is the build plus the first quarter of run cost. Monthly return is measured, not forecast.' }),
  render(el, o, width) {
    const t = LV.tokens, f = LV.frame(el, { title: o.label, caption: o.note, table: false });
    const w = f.width, h = 92, H = o.horizonMonths || 24;
    const be = o.breakEvenMonth != null ? o.breakEvenMonth : o.spend / o.monthlyReturn;
    const beyond = be > H;
    const x = d3.scaleLinear().domain([0, H]).range([8, w - 8]);
    const svg = LV.svg(f.body, w, h), yC = 44;
    svg.append('rect').attr('x', x(0)).attr('y', yC - 6).attr('width', x(H) - x(0)).attr('height', 12).attr('rx', 4).attr('fill', t.paperWarm);
    svg.append('path').attr('d', LV.barPath(x(0), yC - 6, x(Math.min(be, H)) - x(0), 12, 4, 'right')).attr('fill', beyond ? t.sandDeep : t.teal);
    const ticks = d3.range(0, H + 1, H > 18 ? 6 : 3);
    svg.selectAll('text.tk').data(ticks).join('text').attr('class', 'lv-lbl muted lv-num').attr('x', d => x(d)).attr('y', yC + 26).attr('text-anchor', d => d === 0 ? 'start' : d === H ? 'end' : 'middle').attr('font-size', 10.5).text(d => d === 0 ? 'month 0' : d);
    if (!beyond) {
      svg.append('line').attr('x1', x(be)).attr('x2', x(be)).attr('y1', yC - 14).attr('y2', yC + 10).attr('stroke', t.ink).attr('stroke-width', 1.5);
      svg.append('text').attr('class', 'lv-lbl strong lv-num').attr('x', x(be)).attr('y', yC - 20).attr('text-anchor', x(be) > w * 0.8 ? 'end' : x(be) < w * 0.2 ? 'start' : 'middle').attr('font-size', 15).text(`Pays back in month ${Math.ceil(be)}`);
    } else {
      svg.append('text').attr('class', 'lv-lbl strong').attr('x', x(H)).attr('y', yC - 20).attr('text-anchor', 'end').attr('font-size', 15).text(`Not inside ${H} months`);
      svg.append('text').attr('class', 'lv-lbl muted').attr('x', x(H)).attr('y', yC - 5 + 32).attr('text-anchor', 'end').attr('font-size', 10.5).text(`at current return, month ${Math.ceil(be)}`);
    }
    svg.append('text').attr('class', 'lv-lbl').attr('x', 8).attr('y', h - 2).attr('font-size', 11.5).text(`${LV.fmt.gbp(o.spend)} spent · ${LV.fmt.gbp(o.monthlyReturn)} back per month`);
  }
});
