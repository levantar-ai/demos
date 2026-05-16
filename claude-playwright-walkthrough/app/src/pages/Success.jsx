import { Link, useSearchParams } from 'react-router-dom';

export default function Success() {
  const [params] = useSearchParams();
  const id = params.get('id');
  return (
    <section className="centered">
      <div className="check">✓</div>
      <h2>Message sent</h2>
      <p className="sub">
        Thanks — we&rsquo;ve logged your message
        {id && <> as <code>#{id}</code></>}. Our team will be in touch shortly.
      </p>
      <div className="cta-row">
        <Link className="btn primary" to="/admin">See it in submissions</Link>
        <Link className="btn ghost" to="/">Back home</Link>
      </div>
    </section>
  );
}
