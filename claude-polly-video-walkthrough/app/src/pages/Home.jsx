import { useNavigate } from 'react-router-dom';

export default function Home() {
  const navigate = useNavigate();
  return (
    <section className="hero">
      <p className="eyebrow">Customer support, minus the friction</p>
      <h1>
        Talk to a human.<br />
        <span className="accent">We answer fast.</span>
      </h1>
      <p className="lede">
        Acme is a tiny demo product. The point isn&rsquo;t the product — it&rsquo;s
        that everything you click through here was screenshotted automatically by
        Claude driving Playwright, then narrated by AWS Polly and stitched into a
        video.
      </p>
      <div className="cta-row">
        <button
          className="btn primary"
          data-demo-id="cta-primary"
          onClick={() => navigate('/contact')}
        >
          Get in touch
        </button>
        <button className="btn ghost" onClick={() => navigate('/admin')}>
          View submissions
        </button>
      </div>
      <div className="stat-strip">
        <div><strong>1</strong><span>app</span></div>
        <div><strong>6</strong><span>captured steps</span></div>
        <div><strong>0</strong><span>screenshots taken by hand</span></div>
      </div>
    </section>
  );
}
