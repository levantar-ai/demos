import { useEffect, useState } from 'react';

export default function Admin() {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    fetch('/api/submissions')
      .then((r) => r.json())
      .then((d) => setRows(d.submissions))
      .catch(() => setRows([]));
  }, []);

  return (
    <section className="admin">
      <div className="admin-head">
        <h2>Contact submissions</h2>
        <span className="pill">{rows ? rows.length : '—'} total</span>
      </div>

      {rows === null && <p className="sub">Loading…</p>}
      {rows && rows.length === 0 && (
        <p className="sub empty">No submissions yet. Send one from the contact form.</p>
      )}

      {rows && rows.length > 0 && (
        <table className="card">
          <thead>
            <tr>
              <th>#</th>
              <th>Name</th>
              <th>Email</th>
              <th>Message</th>
              <th>Received</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.id}</td>
                <td>{r.name}</td>
                <td className="mono">{r.email}</td>
                <td className="msg">{r.message}</td>
                <td className="mono dim">
                  {new Date(r.createdAt).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
