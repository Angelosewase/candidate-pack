"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Assignment, type RequestDetail, type RequestStatus } from "@/lib/api";
import { Button } from "@/components/ui/button";

const STATUS_LABEL: Record<RequestStatus, string> = {
  submitted: "submitted",
  in_progress: "in progress",
  delivered: "delivered",
  accepted: "accepted",
  rejected: "rejected",
};

export function RequestDetailView({
  requestId,
  onChanged,
  canAssign,
}: {
  requestId: number;
  onChanged: () => void;
  canAssign: boolean;
}) {
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [d, a] = await Promise.all([
        api.getRequest(requestId),
        api.listAssignments(requestId).catch(() => [] as Assignment[]),
      ]);
      setDetail(d);
      setAssignments(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load request");
    }
  }, [requestId]);

  /* eslint-disable react-hooks/set-state-in-effect -- fetch-on-mount for server state selected by prop */
  useEffect(() => {
    load();
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function transition(to_status: RequestStatus) {
    setBusy(to_status);
    setError(null);
    try {
      await api.transition(requestId, to_status, note || undefined);
      setNote("");
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transition failed");
      if (err instanceof ApiError && err.details) {
        setError(`${err.message}: ${JSON.stringify(err.details)}`);
      }
    } finally {
      setBusy(null);
    }
  }

  async function unassign(episode_id: string) {
    setBusy(`unassign:${episode_id}`);
    try {
      await api.unassign(requestId, episode_id);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unassign failed");
    } finally {
      setBusy(null);
    }
  }

  if (!detail) {
    return <p className="text-sm text-muted-foreground">{error ?? "Loading…"}</p>;
  }

  const input =
    "h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-base font-medium">
          #{detail.id} · {detail.task_name}
        </h2>
        <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">
          {STATUS_LABEL[detail.status]} · {detail.assigned_count}/{detail.episodes_requested} episodes
        </span>
      </div>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-muted-foreground">Client</dt>
        <dd>{detail.client.name}</dd>
        <dt className="text-muted-foreground">Deadline</dt>
        <dd>{detail.deadline}</dd>
        <dt className="text-muted-foreground">Notes</dt>
        <dd className="col-span-1 break-words">{detail.notes || "—"}</dd>
      </dl>

      {detail.allowed_transitions.length > 0 && (
        <div className="flex flex-col gap-2 rounded-xl border p-3">
          <p className="text-sm font-medium">Move to</p>
          <div className="flex flex-wrap gap-1.5">
            {detail.allowed_transitions.map((t) => (
              <Button
                key={t}
                size="sm"
                variant={t === "rejected" ? "destructive" : "default"}
                disabled={busy !== null}
                onClick={() => transition(t)}
              >
                {busy === t ? "…" : STATUS_LABEL[t]}
              </Button>
            ))}
          </div>
          {(detail.allowed_transitions.includes("rejected") ||
            detail.allowed_transitions.includes("delivered")) && (
            <input
              className={input}
              placeholder="Note (required when rejecting)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
        </div>
      )}

      <div>
        <h3 className="mb-1.5 text-sm font-medium">
          Assigned episodes ({assignments.length})
        </h3>
        {assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet.</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {assignments.map((a) => (
              <li
                key={a.episode.episode_id}
                className="flex items-center justify-between gap-2 rounded-lg border px-2.5 py-1.5 text-sm"
              >
                <span className="font-mono text-xs">{a.episode.episode_id}</span>
                <span className="text-muted-foreground">
                  {a.episode.robot_id} · {a.episode.quality}
                </span>
                {canAssign && (
                  <Button
                    size="xs"
                    variant="ghost"
                    disabled={busy !== null}
                    onClick={() => unassign(a.episode.episode_id)}
                  >
                    unassign
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-1.5 text-sm font-medium">History</h3>
        <ol className="flex flex-col gap-1 text-sm">
          {detail.events.map((e) => (
            <li key={e.id} className="text-muted-foreground">
              <span className="text-foreground">
                {e.from_status ?? "∅"} → {e.to_status}
              </span>{" "}
              by {e.actor.name} · {new Date(e.created_at).toLocaleString()}
              {e.note && <span className="block text-foreground">“{e.note}”</span>}
            </li>
          ))}
        </ol>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
