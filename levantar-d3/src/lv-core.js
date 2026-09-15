/* Levantar D3 · core. Frame, tooltip, legend, table view, registry. Requires d3 v7. */
(function (LV) {
  const registry = new Map();
  LV.define = function (def) { registry.set(def.name, def); return def; };
  LV.registry = registry;
  LV.list = () => Array.from(registry.values());

  // Mount a component into an element. Re-renders on width change.
  LV.render = function (name, el, opts) {
    const def = registry.get(name);
    if (!def) throw new Error('LV: unknown component ' + name);
    if (typeof el === 'string') el = document.querySelector(el);
    let last = -1;
    const draw = () => {
      const w = el.getBoundingClientRect().width;
      if (!w || Math.abs(w - last) < 2) return;
      last = w;
      el.innerHTML = '';
      def.render(el, opts || def.demo(), w);
    };
    draw();
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => draw());
      ro.observe(el);
      el._lvResize = ro;
    }
    return { rerender: draw, def };
  };

  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  LV.esc = esc;

  // Figure frame. Returns {body, table(columns, rows), width}.
  LV.frame = function (el, o) {
    const fig = document.createElement('figure');
    fig.className = 'lv-fig';
    fig.style.margin = '0';
    let head = '<div class="lv-fig-head"><div>';
    if (o.eyebrow || o.figure) head += `<div class="lv-ft">${o.figure ? `<b>${esc(o.figure)}</b> &nbsp;·&nbsp; ` : ''}${esc(o.eyebrow || '')}</div>`;
    if (o.title) head += `<div class="lv-title">${esc(o.title)}</div>`;
    if (o.subtitle) head += `<div class="lv-sub">${esc(o.subtitle)}</div>`;
    head += '</div>';
    if (o.table !== false) head += '<button class="lv-toggle" type="button" aria-pressed="false">Table</button>';
    head += '</div>';
    fig.innerHTML = head + '<div class="lv-legend" hidden></div><div class="lv-body"></div><div class="lv-table" hidden></div>' + (o.caption ? `<figcaption class="lv-figcap">${esc(o.caption)}</figcaption>` : '');
    el.appendChild(fig);
    const body = fig.querySelector('.lv-body');
    const tableEl = fig.querySelector('.lv-table');
    const legendEl = fig.querySelector('.lv-legend');
    const btn = fig.querySelector('.lv-toggle');
    if (btn) btn.addEventListener('click', () => {
      const on = btn.getAttribute('aria-pressed') !== 'true';
      btn.setAttribute('aria-pressed', on);
      btn.textContent = on ? 'Chart' : 'Table';
      body.hidden = on; tableEl.hidden = !on; legendEl.hidden = on || !legendEl.childElementCount;
    });
    const pad = 42; // frame padding both sides
    return {
      fig, body, legendEl,
      width: Math.max(240, el.getBoundingClientRect().width - pad),
      table(columns, rows) {
        tableEl.innerHTML = '<table><thead><tr>' + columns.map(c => `<th class="${c.num ? 'num' : ''}">${esc(c.label)}</th>`).join('') + '</tr></thead><tbody>' +
          rows.map(r => '<tr>' + columns.map(c => `<td class="${c.num ? 'num' : ''}">${esc(c.fmt ? c.fmt(r[c.key], r) : r[c.key] == null ? '–' : r[c.key])}</td>`).join('') + '</tr>').join('') + '</tbody></table>';
      },
      legend(items) {
        legendEl.hidden = false;
        legendEl.innerHTML = items.map(i => `<span class="k"><span class="sw ${i.shape || ''}" style="${i.shape === 'ring' ? 'color:' + i.color : 'background:' + (i.color || 'transparent')}"></span>${esc(i.label)}</span>`).join('');
      }
    };
  };

  LV.svg = function (body, w, h) {
    return d3.select(body).append('svg').attr('viewBox', `0 0 ${w} ${h}`).attr('width', w).attr('height', h).attr('role', 'img');
  };

  // Tooltip anchored to the body element.
  LV.tooltip = function (body) {
    const tip = document.createElement('div');
    tip.className = 'lv-tip';
    body.appendChild(tip);
    return {
      show(x, y, html) {
        tip.innerHTML = html;
        tip.dataset.on = '1';
        const bw = body.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
        let lx = x + 12, ly = y - th - 10;
        if (lx + tw > bw) lx = x - tw - 12;
        if (ly < 0) ly = y + 14;
        tip.style.left = lx + 'px'; tip.style.top = ly + 'px';
      },
      hide() { tip.dataset.on = '0'; }
    };
  };
  // Pointer position relative to the body element.
  LV.pt = (ev, body) => { const r = body.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };

  LV.axisX = (g, axis) => { g.attr('class', 'lv-axis').call(axis); g.select('.domain').attr('stroke', LV.tokens.ruleStrong); g.selectAll('.tick line').attr('stroke', LV.tokens.ruleStrong); return g; };
  LV.axisY = (g, axis) => { g.attr('class', 'lv-axis').call(axis); g.select('.domain').remove(); g.selectAll('.tick line').remove(); return g; };
  LV.grid = (g, y, w, ticks) => {
    g.attr('class', 'lv-grid');
    g.selectAll('line').data(y.ticks(ticks || 5)).join('line').attr('x1', 0).attr('x2', w).attr('y1', d => y(d)).attr('y2', d => y(d)).attr('stroke', LV.tokens.rule);
    return g;
  };
  // Bar with a rounded data end and a square baseline (vertical: grows up; horizontal: grows right).
  LV.barPath = function (x, y, w, h, r, dir) {
    r = Math.min(r, w / 2, h / 2);
    if (h <= 0 || w <= 0) return '';
    if (dir === 'right') return `M${x},${y}H${x + w - r}a${r},${r} 0 0 1 ${r},${r}V${y + h - r}a${r},${r} 0 0 1 ${-r},${r}H${x}Z`;
    if (dir === 'left') return `M${x + w},${y}H${x + r}a${r},${r} 0 0 0 ${-r},${r}V${y + h - r}a${r},${r} 0 0 0 ${r},${r}H${x + w}Z`;
    if (dir === 'down') return `M${x},${y}H${x + w}V${y + h - r}a${r},${r} 0 0 1 ${-r},${r}H${x + r}a${r},${r} 0 0 1 ${-r},${-r}Z`;
    return `M${x},${y + h}V${y + r}a${r},${r} 0 0 1 ${r},${-r}H${x + w - r}a${r},${r} 0 0 1 ${r},${r}V${y + h}Z`;
  };
  // Status glyphs as SVG path data on a 0..20 box. Always paired with a label.
  LV.glyph = {
    check: 'M4 10.5l4 4 8-9',
    cross: 'M5 5l10 10M15 5L5 15',
    tilde: 'M4 11c2-4 4-4 6 0s4 4 6 0',
    dot: 'M10 10m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0',
    warn: 'M10 3l8 14H2zM10 8v4M10 15v.5',
    arrowUp: 'M10 16V4M5 9l5-5 5 5',
    arrowDown: 'M10 4v12M5 11l5 5 5-5',
    flag: 'M5 17V3h9l-2 3.5 2 3.5H5',
    human: 'M10 4a3 3 0 1 1 0 6a3 3 0 0 1 0-6zM4 17c0-3.3 2.7-5 6-5s6 1.7 6 5'
  };
  LV.glyphSvg = (name, color, size) => `<svg viewBox="0 0 20 20" width="${size || 16}" height="${size || 16}" aria-hidden="true"><path d="${LV.glyph[name]}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  LV.glyphG = (sel, name, color, size) => sel.append('path').attr('d', LV.glyph[name]).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round').attr('transform', `scale(${(size || 16) / 20})`);

  LV.hatch = function (svg, id, color) {
    const p = svg.append('defs').append('pattern').attr('id', id).attr('patternUnits', 'userSpaceOnUse').attr('width', 6).attr('height', 6).attr('patternTransform', 'rotate(45)');
    p.append('line').attr('x1', 0).attr('y1', 0).attr('x2', 0).attr('y2', 6).attr('stroke', color).attr('stroke-width', 1.5);
    return `url(#${id})`;
  };
  LV.textWidth = (() => {
    let ctx;
    return (s, font) => { if (!ctx) ctx = document.createElement('canvas').getContext('2d'); ctx.font = font || `11.5px ${LV.tokens.sans}`; return ctx.measureText(s).width; };
  })();
  LV.months = (n, from) => { const out = []; const d = from ? new Date(from) : new Date(2026, 0, 1); for (let i = 0; i < n; i++) out.push(new Date(d.getFullYear(), d.getMonth() + i, 1)); return out; };
  LV.wrap = function (text, width) {
    text.each(function () {
      const t = d3.select(this), words = t.text().split(/\s+/).reverse(), lh = 1.15, x = t.attr('x') || 0, y = t.attr('y') || 0, dy = parseFloat(t.attr('dy')) || 0;
      let word, line = [], n = 0, tspan = t.text(null).append('tspan').attr('x', x).attr('y', y).attr('dy', dy + 'em');
      while ((word = words.pop())) {
        line.push(word); tspan.text(line.join(' '));
        if (tspan.node().getComputedTextLength() > width && line.length > 1) { line.pop(); tspan.text(line.join(' ')); line = [word]; tspan = t.append('tspan').attr('x', x).attr('y', y).attr('dy', ++n * lh + dy + 'em').text(word); }
      }
    });
  };
})(window.LV);
