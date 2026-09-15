/* Levantar D3 · tokens. Colour and type from levantar-brand-template.html v1.0.
   Flame is action-only in the brand and never appears in a chart. */
window.LV = window.LV || {};
(function (LV) {
  LV.tokens = {
    paper: '#f7f5f0', paperWarm: '#efece4', paper3: '#e5e0d4', surface: '#ffffff',
    ink: '#0e1216', inkLede: '#2f3438', ink2: '#4a5158', ink3: '#798086',
    teal: '#0d5257', tealDeep: '#083a3e', tealLift: '#7fc5c2', tealWash: '#e4f0ef',
    flame: '#e05a2b',
    sand: '#c6bda9', sandDeep: '#8a7b5a',
    rule: '#dcd5c6', ruleStrong: '#c6bda9',
    sans: "'Inter Tight',Helvetica,Arial,sans-serif",
    serif: "'Source Serif 4',Georgia,serif",
    mono: "ui-monospace,'SF Mono','Cascadia Mono',Consolas,monospace"
  };
  const t = LV.tokens;
  LV.palette = {
    // Fixed order, never cycled. Adjacent pairs validated (worst CVD dE 37.5).
    // Scatter, bubble and other all-pairs forms use the first three only.
    categorical: [t.teal, t.tealLift, t.ink, t.sand],
    allPairs: [t.teal, t.tealLift, t.ink],
    // One hue, light to dark. Sequential may recede toward the surface.
    sequential: ['#eef5f4', '#c4e2df', '#8fcbc7', '#4f9f9b', '#1f7370', t.teal, t.tealDeep],
    // Ordinal steps clear 2:1 on white at the light end.
    ordinal: ['#6db5b1', '#3f918e', '#1f6f6c', t.teal, t.tealDeep],
    // Diverging: cool teal against warm sand with a neutral paper midpoint.
    diverging: { neg: t.sandDeep, mid: t.paperWarm, pos: t.teal },
    // Verdicts and status always ship with an icon and a label, never colour alone.
    verdict: { back: t.teal, fix: t.sandDeep, stop: t.ink, untested: t.ink3 },
    status: { good: t.teal, warning: t.sandDeep, critical: t.ink, none: t.ink3 }
  };
  LV.fmt = {
    compact(n, unit) {
      if (n == null || isNaN(n)) return '–';
      const a = Math.abs(n);
      let s;
      if (a >= 1e9) s = (n / 1e9).toFixed(a >= 1e10 ? 0 : 1) + 'B';
      else if (a >= 1e6) s = (n / 1e6).toFixed(a >= 1e7 ? 0 : 1) + 'M';
      else if (a >= 1e4) s = (n / 1e3).toFixed(0) + 'K';
      else if (a >= 1e3) s = (n / 1e3).toFixed(1) + 'K';
      else s = Number.isInteger(n) ? String(n) : n.toFixed(1);
      return (unit || '') + s.replace('.0', '');
    },
    gbp(n) { return (n < 0 ? '−£' : '£') + LV.fmt.compact(Math.abs(n)); },
    gbpFull(n) { return (n < 0 ? '−£' : '£') + Math.abs(Math.round(n)).toLocaleString('en-GB'); },
    pct(n, d) { return (d == null ? Math.round(n) : n.toFixed(d)) + '%'; },
    signed(n, f) { const s = (f || String)(Math.abs(n)); return n > 0 ? '+' + s : n < 0 ? '−' + s : s; },
    int(n) { return Math.round(n).toLocaleString('en-GB'); },
    month(d) { return d.toLocaleDateString('en-GB', { month: 'short' }); },
    monthYear(d) { return d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }); },
    day(d) { return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }); }
  };
})(window.LV);
