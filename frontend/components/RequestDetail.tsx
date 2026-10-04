"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  ApiError,
  type Assignment,
  type RequestDetail,
  type RequestStatus,
} from "@/lib/api";
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
import { ConfirmAction } from "@/components/ConfirmAction";
import { QualityBadge, StatusBadge } from "@/components/status-badges";

const TRANSITION_LABEL: Record<RequestStatus, string> = {
  submitted: "submitted",
  in_progress: "in progress",
  delivered: "delivered",
  accepted: "accepted",
  rejected: "rejected",
};

function formatDetails(err: unknown): string {
  if (err instanceof ApiError && err.details) {
    return `${err.message}: ${JSON.stringify(err.details)}`;
  }
  return err instanceof Error ? err.message : "Something went wrong";
}

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
  const [busy, setBusy] = useState(false);

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
      setError(formatDetails(err));
    }
  }, [requestId]);

  /* eslint-disable react-hooks/set-state-in-effect -- fetch-on-mount for server state selected by prop */
  useEffect(() => {
    load();
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function transition(to_status: RequestStatus) {
    setBusy(true);
    setError(null);
    try {
      await api.transition(requestId, to_status, note || undefined);
      setNote("");
      await load();
      onChanged();
    } catch (err) {
      setError(formatDetails(err));
    } finally {
      setBusy(false);
    }
  }

  async function unassign(episode_id: string) {
    setBusy(true);
    setError(null);
    try {
      await api.unassign(requestId, episode_id);
      await load();
      onChanged();
    } catch (err) {
      setError(formatDetails(err));
    } finally {
      setBusy(false);
    }
  }

  if (!detail) {
    return (
      <p className="text-sm text-muted-foreground">{error ?? "Loading…"}</p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-medium">
          #{detail.id} · {detail.task_name}
        </h2>
        <StatusBadge status={detail.status} />
        <span className="text-sm text-muted-foreground">
          {detail.assigned_count}/{detail.episodes_requested} episodes assigned
        </span>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Client</dt>
        <dd>
          {detail.client.name}
          {detail.client.organisation
            ? ` · ${detail.client.organisation}`
            : null}
        </dd>
        <dt className="text-muted-foreground">Deadline</dt>
        <dd>{detail.deadline}</dd>
        <dt className="text-muted-foreground">Notes</dt>
        <dd className="break-words">{detail.notes || "—"}</dd>
      </dl>

      {detail.allowed_transitions.length > 0 && (
        <div className="flex flex-col gap-2 rounded-xl border p-3">
          <p className="text-sm font-medium">Move to</p>
          <div className="flex flex-wrap gap-1.5">
            {detail.allowed_transitions.map((t) => (
              <ConfirmAction
                key={t}
                title={`Move request #${detail.id} to ${TRANSITION_LABEL[t]}?`}
                description={
                  t === "rejected"
                    ? "The request goes back for rework. A rejection reason is required."
                    : t === "delivered"
                      ? "The client will be asked to accept or reject the delivery."
                      : `The request status will change from ${TRANSITION_LABEL[detail.status]} to ${TRANSITION_LABEL[t]}.`
                }
                confirmLabel={`Move to ${TRANSITION_LABEL[t]}`}
                destructive={t === "rejected"}
                disabled={busy}
                onConfirm={() => transition(t)}
                trigger={
                  <Button
                    size="sm"
                    variant={t === "rejected" ? "destructive" : "default"}
                    disabled={busy}
                  >
                    {TRANSITION_LABEL[t]}
                  </Button>
                }
              />
            ))}
          </div>
          {(detail.allowed_transitions.includes("rejected") ||
            detail.allowed_transitions.includes("delivered")) && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`note-${detail.id}`}>
                Note
                {detail.allowed_transitions.includes("rejected") &&
                  " (required when rejecting)"}
              </Label>
              <Input
                id={`note-${detail.id}`}
                placeholder="Add context for the next step…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          )}
        </div>
      )}

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">
          Assigned episodes ({assignments.length})
        </h3>
        {assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet.</p>
        ) : (
          <ScrollArea className="max-h-64 rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Episode</TableHead>
                  <TableHead>Robot</TableHead>
                  <TableHead>Quality</TableHead>
                  {canAssign && (
                    <TableHead className="w-24 text-right">Action</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {assignments.map((a) => (
                  <TableRow key={a.episode.episode_id}>
                    <TableCell className="font-mono text-xs">
                      {a.episode.episode_id}
                    </TableCell>
                    <TableCell>{a.episode.robot_id}</TableCell>
                    <TableCell>
                      <QualityBadge quality={a.episode.quality} />
                    </TableCell>
                    {canAssign && (
                      <TableCell className="text-right">
                        <ConfirmAction
                          title={`Unassign ${a.episode.episode_id}?`}
                          description={`The episode becomes available for other requests. Request #${detail.id} will be short by one episode.`}
                          confirmLabel="Unassign"
                          destructive
                          disabled={busy}
                          onConfirm={() => unassign(a.episode.episode_id)}
                          trigger={
                            <Button size="xs" variant="ghost" disabled={busy}>
                              unassign
                            </Button>
                          }
                        />
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </section>

      <section className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">History</h3>
        <ScrollArea className="max-h-48 rounded-lg border p-3">
          <ol className="flex flex-col gap-2 text-sm">
            {detail.events.map((e) => (
              <li key={e.id} className="flex flex-col gap-0.5">
                <span className="text-muted-foreground">
                  <span className="text-foreground">
                    {e.from_status ?? "∅"} → {e.to_status}
                  </span>{" "}
                  by {e.actor.name} ·{" "}
                  {new Date(e.created_at).toLocaleString()}
                </span>
                {e.note && (
                  <span className="text-foreground">“{e.note}”</span>
                )}
              </li>
            ))}
          </ol>
        </ScrollArea>
      </section>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
