import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const EMPTY = { name: '', email: '', message: '' };

export default function Contact() {
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  function validate(values) {
    const e = {};
    if (!values.name.trim()) e.name = 'Please tell us your name.';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(values.email))
      e.email = 'A valid email address is required.';
    if (values.message.trim().length < 10)
      e.message = 'Give us at least a sentence (10+ characters).';
    return e;
  }

  function update(field) {
    return (ev) => {
      setForm((f) => ({ ...f, [field]: ev.target.value }));
      // Clear this field's error as soon as the user starts fixing it.
      setErrors((e) => (e[field] ? { ...e, [field]: undefined } : e));
    };
  }

  async function onSubmit(ev) {
    ev.preventDefault();
    const e = validate(form);
    setErrors(e);
    if (Object.keys(e).length) return;

    setSubmitting(true);
    const res = await fetch('/api/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    setSubmitting(false);
    if (res.ok) {
      const { id } = await res.json();
      navigate(`/success?id=${id}`);
    }
  }

  return (
    <section className="form-wrap">
      <h2>Get in touch</h2>
      <p className="sub">We typically reply within one business day.</p>

      <form className="card form" onSubmit={onSubmit} noValidate>
        <label>
          <span>Name</span>
          <input
            value={form.name}
            onChange={update('name')}
            placeholder="Ada Lovelace"
            className={errors.name ? 'invalid' : ''}
          />
          {errors.name && <em className="err">{errors.name}</em>}
        </label>

        <label>
          <span>Email</span>
          <input
            value={form.email}
            onChange={update('email')}
            placeholder="ada@example.com"
            className={errors.email ? 'invalid' : ''}
          />
          {errors.email && <em className="err">{errors.email}</em>}
        </label>

        <label>
          <span>Message</span>
          <textarea
            rows={4}
            value={form.message}
            onChange={update('message')}
            placeholder="How can we help?"
            className={errors.message ? 'invalid' : ''}
          />
          {errors.message && <em className="err">{errors.message}</em>}
        </label>

        <button className="btn primary" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send message'}
        </button>
      </form>
    </section>
  );
}
