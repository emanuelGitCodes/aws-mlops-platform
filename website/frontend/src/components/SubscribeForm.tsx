import { useState } from "react";

import { subscribe } from "../api";
import { ApiError } from "../types";

export function SubscribeForm() {
  const [email, setEmail] = useState("");
  const [signedUpAt, setSignedUpAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const result = await subscribe(email);
      // The backend answers with the first signup time, so a second signup
      // from one address shows the original date.
      setSignedUpAt(result.created_at);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "the signup failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="subscribe-panel">
      <h2>Follow the build</h2>
      <form onSubmit={submit}>
        <label className="email-field">
          <span className="sr-only">Email address</span>
          <input
            type="email"
            required
            value={email}
            placeholder="you@example.com"
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "Sending…" : "Subscribe for updates"}
        </button>
      </form>

      {error && <p className="form-note is-error" role="alert">{error}. Check the address, then try again.</p>}
      {signedUpAt && <p className="form-note">Subscribed. First recorded at {signedUpAt}.</p>}
    </section>
  );
}
