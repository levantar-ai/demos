LV.define({
  name: 'heroFigure', group: 'metrics', title: 'Hero figure',
  summary: 'The one number a page leads with, in the brand sans at display size, with a serif standfirst that says what it means and where it came from. Exactly one per view.',
  useCases: ['The ~6% real-value figure on the homepage and in the how-we-measure page', 'Opening a Placement Assessment with the single number the board asked about', 'A cover stat on a client PDF'],
  demo: () => ({
    eyebrow: 'The AI value gap', value: '~6', unit: '%',
    standfirst: 'of organisations report significant value from AI and can attribute five percent or more of EBIT to it. Adoption is near-universal. Measured return is rare.',
    source: 'McKinsey, State of AI 2025 · 1,993 respondents, 105 countries'
  }),
  render(el, o) {
    const div = document.createElement('div');
    div.className = 'lv-hero';
    div.innerHTML = `<div class="eyebrow"><span class="tick"></span>${LV.esc(o.eyebrow || '')}</div><div class="num">${LV.esc(o.value)}${o.unit ? `<small>${LV.esc(o.unit)}</small>` : ''}</div>` +
      (o.standfirst ? `<div class="stand">${LV.esc(o.standfirst)}</div>` : '') + (o.source ? `<div class="src">Source: ${LV.esc(o.source)}</div>` : '');
    el.appendChild(div);
  }
});
