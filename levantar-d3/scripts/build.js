/* Concatenates tokens, core and every component into dist/levantar-d3.js and copies the stylesheet.
   Usage: node scripts/build.js */
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..'), src = path.join(root, 'src');
const files = ['lv-tokens.js', 'lv-core.js'].map(f => path.join(src, f)).concat(fs.readdirSync(path.join(src, 'components')).filter(f => f.endsWith('.js')).sort().map(f => path.join(src, 'components', f)));
const out = '/* Levantar D3 components · built ' + new Date().toISOString().slice(0, 10) + ' · requires d3 v7 */\n' + files.map(f => `/* --- ${path.relative(root, f)} --- */\n` + fs.readFileSync(f, 'utf8')).join('\n');
fs.mkdirSync(path.join(root, 'dist'), { recursive: true });
fs.writeFileSync(path.join(root, 'dist', 'levantar-d3.js'), out);
fs.writeFileSync(path.join(root, 'dist', 'lv.css'), fs.readFileSync(path.join(src, 'lv.css'), 'utf8').replace(/\.\.\/fonts\//g, '../fonts/'));
console.log('dist/levantar-d3.js', (out.length / 1024).toFixed(0) + ' KB, ' + files.length + ' files');
