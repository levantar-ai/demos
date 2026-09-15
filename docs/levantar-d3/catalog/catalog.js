/* Builds the catalogue page from the component registry. */
(function () {
  document.getElementById('logo').src = LV.logo;
  document.getElementById('logo2').src = LV.logo;
  const groups = [
    { id: 'metrics', title: 'Metric components', lede: 'Numbers first. A tile, a hero figure or a meter says one thing and says it plainly. These are the pieces a report or a dashboard leads with.' },
    { id: 'value', title: 'AI value diagnostics', lede: 'Where AI pays and what the evidence is. Placement, attribution, budget and the assumptions a business case rests on.' },
    { id: 'security', title: 'Security and evidence', lede: 'Where the estate is exposed, what to fix first, and the evidence of what a system actually did.' },
    { id: 'agentic', title: 'Agentic AI', lede: 'Readiness, handoffs, outcomes and cost for agents doing real work inside controls you set.' }
  ];
  const tiles = new Set(['statTile', 'verdictTile', 'unitEconomicsTile', 'evidenceLadder', 'rangeEstimate', 'paybackMeter']);
  const all = LV.list();
  const short = v => JSON.stringify(v, (k, val) => val instanceof Date ? val.toISOString().slice(0, 10) : val, 2);
  const snippet = def => {
    const d = def.demo();
    let json = short(d);
    if (json.length > 1400) {
      const lines = json.split('\n');
      json = lines.slice(0, 28).join('\n') + '\n  … ' + (lines.length - 28) + ' more lines\n}';
    }
    return `LV.render('${def.name}', document.querySelector('#target'), ${json});`;
  };
  const nav = document.getElementById('index'), root = document.getElementById('groups');
  let n = 0;
  groups.forEach(g => {
    const defs = all.filter(d => d.group === g.id);
    const navCol = document.createElement('div');
    navCol.innerHTML = `<h2>${g.title}</h2><ol>${defs.map((d, i) => `<li><a href="#${d.name}"><small>${String(n + i + 1).padStart(2, '0')}</small>${LV.esc(d.title)}</a></li>`).join('')}</ol>`;
    nav.appendChild(navCol);
    const sec = document.createElement('section');
    sec.className = 'group'; sec.id = 'group-' + g.id;
    sec.innerHTML = `<div class="tickrule"></div><div class="eyebrow"><span class="tickrule small"></span> ${g.title}</div><h2>${g.title}.</h2><p class="lede">${g.lede}</p>`;
    const host = document.createElement('div');
    if (g.id === 'metrics') host.className = 'metrics-grid';
    sec.appendChild(host);
    defs.forEach((def, i) => {
      n++;
      const art = document.createElement('article');
      art.className = 'comp'; art.id = def.name;
      if (g.id === 'metrics' && !tiles.has(def.name)) art.style.gridColumn = '1 / -1';
      art.innerHTML = `<div class="cnum">${String(n).padStart(2, '0')} · ${def.group}</div><h3>${LV.esc(def.title)}</h3><p class="sum">${LV.esc(def.summary)}</p><div class="demo${tiles.has(def.name) ? ' tile' : ''}"></div>` +
        `<div class="aside"><div><h4>Sample use cases</h4><ul>${def.useCases.map(u => `<li>${LV.esc(u)}</li>`).join('')}</ul></div><div><details><summary>Usage</summary><pre></pre></details></div></div>`;
      art.querySelector('pre').textContent = snippet(def);
      host.appendChild(art);
      LV.render(def.name, art.querySelector('.demo'));
    });
    root.appendChild(sec);
  });
})();
