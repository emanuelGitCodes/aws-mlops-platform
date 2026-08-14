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
    <section>
      <h2>Keep in touch</h2>
      <form onSubmit={submit}>
        <label>
          <span>Email</span>
          <input
            type="email"
            required
            value={email}
            placeholder="you@example.com"
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <button type="submit" disabled={pending}>
          {pending ? "Sending…" : "Subscribe"}
        </button>
      </form>

      {error && <p role="alert">{error}</p>}
      {signedUpAt && <p>Signed up at {signedUpAt}</p>}
    </section>
  );
}
