"use client";

import { useEffect, useState } from "react";
import { api, type Role, type User } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function UsersPanel() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("client");

  async function load() {
    setError(null);
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users");
    }
  }

  /* eslint-disable react-hooks/set-state-in-effect -- fetch-on-mount for server state */
  useEffect(() => {
    load();
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createUser({ email, name, password, role });
      setEmail("");
      setName("");
      setPassword("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function toggleActive(u: User) {
    setError(null);
    try {
      await api.updateUser(u.id, { is_active: !u.is_active });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function setRoleFor(u: User, next: Role) {
    setError(null);
    try {
      await api.updateUser(u.id, { role: next });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  const input =
    "h-8 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring";

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={create} className="flex flex-wrap items-end gap-2 rounded-xl border p-3">
        <label className="flex flex-col gap-1 text-xs">
          Email
          <input className={input} value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Name
          <input className={input} value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Password
          <input className={input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <label className="flex flex-col gap-1 text-xs">
          Role
          <select className={input} value={role} onChange={(e) => setRole(e.target.value as Role)}>
            <option value="client">client</option>
            <option value="operator">operator</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <Button size="sm" type="submit">
          Create user
        </Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <ul className="flex flex-col gap-1.5">
        {users.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm">
            <span className="min-w-0 flex-1 truncate">
              {u.name} · {u.email} · {u.role} · {u.is_active ? "active" : "disabled"}
            </span>
            <select
              className={input}
              value={u.role}
              onChange={(e) => setRoleFor(u, e.target.value as Role)}
              aria-label={`role for ${u.email}`}
            >
              <option value="client">client</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
            <Button size="xs" variant="outline" onClick={() => toggleActive(u)}>
              {u.is_active ? "disable" : "enable"}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
