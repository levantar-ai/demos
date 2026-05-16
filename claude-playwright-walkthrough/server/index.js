import express from 'express';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const app = express();
app.use(express.json());

// In-memory store — resets on restart. Plenty for a demo.
const submissions = [];
let nextId = 1001;

app.post('/api/contact', (req, res) => {
  const { name, email, message } = req.body || {};
  if (!name || !email || !message) {
    return res.status(400).json({ error: 'name, email and message are required' });
  }
  const entry = {
    id: nextId++,
    name: String(name).trim(),
    email: String(email).trim(),
    message: String(message).trim(),
    createdAt: new Date().toISOString(),
  };
  submissions.unshift(entry);
  res.status(201).json({ id: entry.id });
});

app.get('/api/submissions', (_req, res) => {
  res.json({ submissions });
});

// Serve the built SPA if it exists (production single-server mode).
const dist = join(__dirname, '..', 'dist');
if (existsSync(dist)) {
  app.use(express.static(dist));
  app.get('*', (_req, res) => res.sendFile(join(dist, 'index.html')));
}

const PORT = process.env.PORT || 8787;
app.listen(PORT, () => console.log(`[server] API listening on http://localhost:${PORT}`));
