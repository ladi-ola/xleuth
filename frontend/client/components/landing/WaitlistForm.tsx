import { FormEvent, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { secureUrl } from "@/lib/api/urls";

const API_URL = secureUrl(import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8000");
const SUCCESS = "Thanks for your interest in Xleuth.";
type Field = "name" | "email" | "consent";

export function WaitlistForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [status, setStatus] = useState<"idle" | "loading" | "success">("idle");
  const [error, setError] = useState("");
  const pending = useRef(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const consentRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const normalizedName = name.trim().replace(/\s+/g, " ");
    const normalizedEmail = email.trim().toLowerCase();
    const next: Partial<Record<Field, string>> = {};
    if (!normalizedName || normalizedName.length > 120 || /[<>]/.test(normalizedName)) next.name = "Enter a name of up to 120 characters without markup.";
    if (normalizedEmail.length > 255 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) next.email = "Enter a valid email address.";
    if (!consent) next.consent = "Consent is required to join the waitlist.";
    setErrors(next);
    if (Object.keys(next).length) {
      if (next.name) nameRef.current?.focus();
      else if (next.email) emailRef.current?.focus();
      else consentRef.current?.focus();
      return;
    }

    pending.current = true;
    setStatus("loading");
    setError("");
    try {
      const response = await fetch(`${API_URL}/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: normalizedName, email: normalizedEmail, consent, website }),
      });
      if (!response.ok) {
        if (response.status === 429) throw new Error("Too many attempts. Please try again shortly.");
        if (response.status === 422) throw new Error("Check your details and try again.");
        throw new Error("The waitlist is unavailable. Please try again later.");
      }
      setStatus("success");
      setName("");
      setEmail("");
    } catch (cause) {
      setStatus("idle");
      setError(cause instanceof Error && !cause.message.includes("fetch") ? cause.message : "Could not connect. Please try again later.");
    } finally {
      pending.current = false;
    }
  }

  if (status === "success") return <p role="status" className="landing-success">{SUCCESS}</p>;

  return (
    <form className="landing-form" onSubmit={submit} noValidate>
      <div className="landing-fields">
        <div>
          <label htmlFor="waitlist-name">Name</label>
          <input id="waitlist-name" name="name" ref={nameRef} autoComplete="name" value={name} maxLength={120} aria-invalid={!!errors.name} aria-describedby={errors.name ? "waitlist-name-error" : undefined} onChange={e => setName(e.target.value)} />
          {errors.name && <p className="landing-field-error" id="waitlist-name-error" aria-live="polite">{errors.name}</p>}
        </div>
        <div>
          <label htmlFor="waitlist-email">Email</label>
          <input id="waitlist-email" name="email" type="email" inputMode="email" spellCheck={false} ref={emailRef} autoComplete="email" value={email} maxLength={255} aria-invalid={!!errors.email} aria-describedby={errors.email ? "waitlist-email-error" : undefined} onChange={e => setEmail(e.target.value)} />
          {errors.email && <p className="landing-field-error" id="waitlist-email-error" aria-live="polite">{errors.email}</p>}
        </div>
      </div>
      <div className="landing-honeypot" aria-hidden="true">
        <label htmlFor="waitlist-website">Website</label>
        <input id="waitlist-website" name="website" tabIndex={-1} autoComplete="off" value={website} onChange={e => setWebsite(e.target.value)} />
      </div>
      <label className="landing-consent" htmlFor="waitlist-consent">
        <input id="waitlist-consent" name="consent" type="checkbox" ref={consentRef} checked={consent} aria-invalid={!!errors.consent} aria-describedby={errors.consent ? "waitlist-consent-error" : undefined} onChange={e => setConsent(e.target.checked)} />
        <span>By proceeding, you agree to our <Link to="/privacy">Privacy Policy</Link> and consent to the collection and use of your information as outlined.</span>
      </label>
      {errors.consent && <p className="landing-field-error" id="waitlist-consent-error" aria-live="polite">{errors.consent}</p>}
      <button className="landing-action landing-submit" type="submit" disabled={status === "loading"}>{status === "loading" ? <><span className="landing-spinner" aria-hidden="true" /> Join waitlist…</> : "Join waitlist"}</button>
      {error && <p className="landing-field-error" role="alert">{error}</p>}
    </form>
  );
}
