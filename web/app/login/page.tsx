"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    setBusy(false);
    if (res.ok) {
      router.push("/");
      router.refresh();
    }
    else setError("Wrong password.");
  }

  return (
    <form className="card login" onSubmit={signIn}>
      <h1>Visa tracking</h1>
      <label>
        Office password
        <input type="password" value={password} autoFocus
               onChange={(e) => setPassword(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <button className="primary" disabled={busy || !password}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
