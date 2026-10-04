"use client";

import { useCallback, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "@/lib/auth-context";
import { api, type DatasetRequest, type RequestStatus } from "@/lib/api";
import { useRequestEvents } from "@/hooks/use-request-events";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LoginForm } from "@/components/LoginForm";
import { RequestDetailView } from "@/components/RequestDetail";
import { EpisodeBrowser } from "@/components/EpisodeBrowser";
import { ImportPanel } from "@/components/ImportPanel";
import { AnalyticsPanel } from "@/components/AnalyticsPanel";
import { UsersPanel } from "@/components/UsersPanel";
import { StatusBadge } from "@/components/status-badges";

const STATUSES: (RequestStatus | "")[] = [
  "",
  "submitted",
  "in_progress",
  "delivered",
  "accepted",
  "rejected",
];

function NewRequestForm({ onCreated }: { onCreated: () => void }) {
  const [taskName, setTaskName] = useState("");
  const [count, setCount] = useState(5);
  const [deadline, setDeadline] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.createRequest({
        task_name: taskName,
        episodes_requested: count,
        deadline,
        notes,
      });
      setTaskName("");
      setNotes("");
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="grid grid-cols-2 gap-2 rounded-xl border p-3 sm:grid-cols-3 lg:grid-cols-[1fr_auto_auto_1fr_auto]"
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-task">Task</Label>
        <Input
          id="new-task"
          value={taskName}
          onChange={(e) => setTaskName(e.target.value)}
          required
          placeholder="pick cup"
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-count">Episodes</Label>
        <Input
          id="new-count"
          type="number"
          min={1}
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
          required
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-deadline">Deadline</Label>
        <Input
          id="new-deadline"
          type="date"
          value={deadline}
          onChange={(e) => setDeadline(e.target.value)}
          required
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-notes">Notes</Label>
        <Input
          id="new-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="optional"
        />
      </div>
      <div className="flex items-end">
        <Button size="sm" type="submit" disabled={busy} className="w-full">
          {busy ? "…" : "Create request"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="col-span-full text-sm text-destructive">
          {error}
        </p>
      )}
    </form>
  );
}

function Dashboard() {
  const { user, logout } = useAuth();
  const [requests, setRequests] = useState<DatasetRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tab, setTab] = useState("requests");
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const isStaff = user?.role === "operator" || user?.role === "admin";
  const isAdmin = user?.role === "admin";
  const { lastEvent, connected } = useRequestEvents(!!user && isStaff);

  const load = useCallback(async () => {
    setError(null);
    try {
      const page = await api.listRequests({
        status: statusFilter || undefined,
        limit: 100,
      });
      setRequests(page.items);
      if (page.items.length > 0 && selectedId === null) {
        // Keep selection stable; don't auto-select.
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load requests");
    }
  }, [statusFilter, selectedId]);

  /* eslint-disable react-hooks/set-state-in-effect -- initial server-state fetch after login; not derived render state */
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  // Live updates: any committed change re-fetches the list.
  /* eslint-disable react-hooks/set-state-in-effect -- SSE subscription update from an external system */
  useEffect(() => {
    if (!lastEvent) return;
    setFlash(`Request #${lastEvent.request_id} → ${lastEvent.status} (live)`);
    load();
    const t = setTimeout(() => setFlash(null), 5000);
    return () => clearTimeout(t);
  }, [lastEvent, load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  if (!user) return null;

  const tabs = [
    "requests",
    ...(isStaff ? ["episodes", "import", "analytics"] : []),
    ...(isAdmin ? ["users"] : []),
  ];

  const input =
    "h-8 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring";

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-6xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center gap-2">
        <div className="mr-auto">
          <h1 className="text-base font-medium">Dataset Request Desk</h1>
          <p className="text-sm text-muted-foreground">
            {user.name} · {user.role}
            {isStaff && (
              <span className={connected ? "text-green-600" : "text-muted-foreground"}>
                {" "}· {connected ? "● live" : "○ reconnecting…"}
              </span>
            )}
          </p>
        </div>
        <nav className="flex gap-1.5">
          {tabs.map((t) => (
            <Button
              key={t}
              size="sm"
              variant={tab === t ? "default" : "outline"}
              onClick={() => setTab(t)}
            >
              {t}
            </Button>
          ))}
        </nav>
        <Button size="sm" variant="ghost" onClick={logout}>
          Sign out
        </Button>
      </header>

      {flash && (
        <p className="rounded-lg border border-green-600/30 bg-green-50 px-3 py-1.5 text-sm text-green-800 dark:bg-green-950 dark:text-green-200">
          {flash}
        </p>
      )}

      {tab === "requests" && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className="flex flex-col gap-3">
            {user.role === "client" && <NewRequestForm onCreated={load} />}
            <div className="flex items-center gap-2">
              <select
                className={input}
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setSelectedId(null);
                }}
                aria-label="Filter by status"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s === "" ? "all statuses" : s.replace("_", " ")}
                  </option>
                ))}
              </select>
              <Button size="sm" variant="outline" onClick={load}>
                Refresh
              </Button>
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <ScrollArea className="max-h-[32rem] rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-14">ID</TableHead>
                    <TableHead>Task</TableHead>
                    {isStaff && <TableHead>Client</TableHead>}
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Progress</TableHead>
                    <TableHead>Deadline</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {requests.map((r) => (
                    <TableRow
                      key={r.id}
                      data-state={selectedId === r.id ? "selected" : undefined}
                      onClick={() => setSelectedId(r.id)}
                      className="cursor-pointer"
                    >
                      <TableCell className="font-mono text-xs">
                        #{r.id}
                      </TableCell>
                      <TableCell className="max-w-44 truncate font-medium">
                        {r.task_name}
                      </TableCell>
                      {isStaff && (
                        <TableCell className="max-w-36 truncate text-muted-foreground">
                          {r.client.name}
                        </TableCell>
                      )}
                      <TableCell>
                        <StatusBadge status={r.status} />
                      </TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {r.assigned_count}/{r.episodes_requested}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {r.deadline}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {requests.length === 0 && !error && (
                <p className="p-4 text-sm text-muted-foreground">
                  No requests match the current filter.
                </p>
              )}
            </ScrollArea>
          </div>
          <div className="rounded-xl border p-4">
            {selectedId === null ? (
              <p className="text-sm text-muted-foreground">Select a request to see details.</p>
            ) : (
              <RequestDetailView
                key={selectedId}
                requestId={selectedId}
                onChanged={load}
                canAssign={isStaff}
              />
            )}
          </div>
        </div>
      )}

      {tab === "episodes" && isStaff && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <div className="rounded-xl border p-4">
            <h2 className="mb-3 text-sm font-medium">Episode browser</h2>
            <EpisodeBrowser
              requestId={selectedId}
              onAssigned={load}
            />
          </div>
          <div className="rounded-xl border p-4">
            {selectedId === null ? (
              <p className="text-sm text-muted-foreground">
                Pick a request in the Requests tab first (selection is shared).
              </p>
            ) : (
              <RequestDetailView
                key={selectedId}
                requestId={selectedId}
                onChanged={load}
                canAssign={isStaff}
              />
            )}
          </div>
        </div>
      )}

      {tab === "import" && isStaff && (
        <div className="max-w-2xl rounded-xl border p-4">
          <h2 className="mb-3 text-sm font-medium">Import episodes</h2>
          <ImportPanel />
        </div>
      )}

      {tab === "analytics" && isStaff && (
        <div className="max-w-3xl rounded-xl border p-4">
          <h2 className="mb-3 text-sm font-medium">Analytics</h2>
          <AnalyticsPanel />
        </div>
      )}

      {tab === "users" && isAdmin && (
        <div className="rounded-xl border p-4">
          <h2 className="mb-3 text-sm font-medium">Users</h2>
          <UsersPanel />
        </div>
      )}
    </div>
  );
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }
  if (!user) {
    return (
      <div className="flex min-h-svh items-center justify-center p-6">
        <LoginForm />
      </div>
    );
  }
  return <Dashboard />;
}

export default function Page() {
  return (
    <AuthProvider>
      <Home />
    </AuthProvider>
  );
}
