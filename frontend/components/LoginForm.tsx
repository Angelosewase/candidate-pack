"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";

const PRESETS = [
  { email: "client-a@example.com", label: "client-a" },
  { email: "ops1@example.com", label: "operator" },
  { email: "admin@example.com", label: "admin" },
];

export function LoginForm() {
  const { login } = useAuth();
  const [email, setEmail] = useState("ops1@example.com");
  const [password, setPassword] = useState("ops123");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  const input =
    "h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring";

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3 rounded-xl border p-6">
      <div>
        <h1 className="text-base font-medium">Dataset Request Desk</h1>
        <p className="text-sm text-muted-foreground">
          Sign in with a seed account (password <kbd>ops123</kbd> for the presets).
        </p>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <Button
            key={p.email}
            type="button"
            variant="secondary"
            size="xs"
            onClick={() => {
              setEmail(p.email);
              setPassword("ops123");
            }}
          >
            {p.label}
          </Button>
        ))}
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Email
        <input className={input} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Password
        <input
          className={input}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      </label>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" disabled={busy}>
        {busy ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
