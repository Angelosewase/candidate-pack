"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, type DatasetRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
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
import { StatusBadge } from "@/components/status-badges";

const STATUSES = [
  "",
  "submitted",
  "in_progress",
  "delivered",
  "accepted",
  "rejected",
];

function NewRequestForm({ onCreated }: { onCreated: (id: number) => void }) {
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
      const created = await api.createRequest({
        task_name: taskName,
        episodes_requested: count,
        deadline,
        notes,
      });
      onCreated(created.id);
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

export default function RequestsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [requests, setRequests] = useState<DatasetRequest[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const isStaff = user?.role === "operator" || user?.role === "admin";
  const { lastEvent } = useRequestEvents(!!user && isStaff);

  const load = useCallback(async () => {
    setError(null);
    try {
      const page = await api.listRequests({
        status: statusFilter || undefined,
        limit: 100,
      });
      setRequests(page.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load requests");
    }
  }, [statusFilter]);

  /* eslint-disable react-hooks/set-state-in-effect -- initial server-state fetch */
  useEffect(() => {
    if (user) load();
  }, [user, load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  /* eslint-disable react-hooks/set-state-in-effect -- SSE subscription update */
  useEffect(() => {
    if (!lastEvent) return;
    setFlash(`Request #${lastEvent.request_id} → ${lastEvent.status} (live)`);
    load();
    const t = setTimeout(() => setFlash(null), 5000);
    return () => clearTimeout(t);
  }, [lastEvent, load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  return (
    <div className="flex flex-col gap-4">
      {user?.role === "client" && (
        <NewRequestForm onCreated={(id) => router.push(`/requests/${id}`)} />
      )}

      {flash && (
        <p className="rounded-lg border border-green-600/30 bg-green-50 px-3 py-1.5 text-sm text-green-800 dark:bg-green-950 dark:text-green-200">
          {flash}
        </p>
      )}

      <div className="flex items-center gap-2">
        <select
          className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
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
              <TableRow key={r.id} className="cursor-pointer">
                <TableCell className="font-mono text-xs">
                  <Link href={`/requests/${r.id}`} className="hover:underline">
                    #{r.id}
                  </Link>
                </TableCell>
                <TableCell className="max-w-44 truncate font-medium">
                  <Link href={`/requests/${r.id}`} className="hover:underline">
                    {r.task_name}
                  </Link>
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
  );
}
