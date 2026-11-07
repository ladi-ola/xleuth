import { FormEvent, useRef, useState } from "react";
import { ArrowUpRight } from "./Primitives";
import { secureUrl } from "@/lib/api/urls";

const API_URL = secureUrl(import.meta.env.VITE_BACKEND_API_URL || "http://localhost:8000");
const TIMEOUT_MS = 45_000;

export async function joinWaitlist(
  name: string,
  email: string,
  website: string,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_URL}/waitlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, website }),
    signal,
  });
  if (response.ok) return;
  if (response.status === 429) throw new Error("Too many attempts. Please try again shortly.");
  if (response.status === 422) throw new Error("Check your details and try again.");
  throw new Error("The waitlist is unavailable. Please try again later.");
}

export function FigmaWaitlistForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [website, setWebsite] = useState("");
  const [error, setError] = useState("");
  const [invalidField, setInvalidField] = useState<"name" | "email" | null>(null);
  const [formState, setFormState] = useState<"default" | "loading" | "success">("default");
  const inFlight = useRef(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const normalizedName = name.trim().replace(/\s+/g, " ");
    const normalizedEmail = email.trim().toLowerCase();
    if (!normalizedName || normalizedName.length > 100 || /[<>]/.test(normalizedName)) {
      setInvalidField("name");
      setError("Please enter your name (up to 100 characters).");
      nameRef.current?.focus();
      return;
    }
    if (normalizedEmail.length > 255 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setInvalidField("email");
      setError("Enter a valid email address.");
      emailRef.current?.focus();
      return;
    }

    setError("");
    setInvalidField(null);
    setFormState("loading");
    inFlight.current = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      await joinWaitlist(normalizedName, normalizedEmail, website, controller.signal);
      setFormState("success");
    } catch (cause) {
      setFormState("default");
      setError(controller.signal.aborted
        ? "The request took too long. Please try again; your email won't be added twice."
        : cause instanceof Error && !cause.message.includes("fetch")
          ? cause.message
          : "Could not connect. Please try again later.");
    } finally {
      window.clearTimeout(timeout);
      inFlight.current = false;
    }
  }

  if (formState === "success") return (
    <div className="success-state" role="status">
      <span>✓</span><h3>You're on the list.</h3>
      <p>Thanks, {name.trim()}. We’ll keep you posted on Xleuth mainnet access.</p>
      <button className="text-button" type="button" onClick={() => { setName(""); setEmail(""); setWebsite(""); setFormState("default"); }}>Add another email</button>
    </div>
  );

  return (
    <form onSubmit={submit} noValidate>
      <div className="field"><label htmlFor="figma-waitlist-name">Name</label><input ref={nameRef} id="figma-waitlist-name" name="name" autoComplete="name" value={name} onChange={event => setName(event.target.value)} placeholder="Your name" aria-invalid={invalidField === "name"} aria-describedby={invalidField === "name" ? "figma-form-error" : undefined} /></div>
      <div className="field"><label htmlFor="figma-waitlist-email">Email</label><input ref={emailRef} id="figma-waitlist-email" name="email" type="email" inputMode="email" autoComplete="email" spellCheck={false} value={email} onChange={event => setEmail(event.target.value)} placeholder="you@company.com" aria-invalid={invalidField === "email"} aria-describedby={invalidField === "email" ? "figma-form-error" : undefined} /></div>
      <div className="figma-honeypot" aria-hidden="true"><label htmlFor="figma-waitlist-website">Website</label><input id="figma-waitlist-website" name="website" tabIndex={-1} autoComplete="off" value={website} onChange={event => setWebsite(event.target.value)} /></div>
      {error && <p className="form-error" id="figma-form-error" role="alert">{error}</p>}
      <button className="button button-primary submit-button" type="submit" disabled={formState === "loading"}>{formState === "loading" ? <><span className="spinner" aria-hidden="true" /> Joining…</> : <>Join waitlist <ArrowUpRight /></>}</button>
      <p className="consent">By joining, you agree to receive product updates from Xleuth. Unsubscribe anytime.</p>
    </form>
  );
}
