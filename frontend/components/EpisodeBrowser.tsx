"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Episode } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfirmAction } from "@/components/ConfirmAction";
import { QualityBadge } from "@/components/status-badges";
import { DataPagination } from "@/components/DataPagination";

const PAGE_SIZE = 15;

export function EpisodeBrowser({
  requestId,
  onAssigned,
}: {
  requestId: number | null;
  onAssigned: () => void;
}) {
  const [taskName, setTaskName] = useState("");
  const [quality, setQuality] = useState("");
  const [assignableOnly, setAssignableOnly] = useState(true);
  const [items, setItems] = useState<Episode[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await api.listEpisodes({
        task_name: taskName.trim() || undefined,
        quality: quality || undefined,
        assignable_only: assignableOnly,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      });
      setItems(res.items);
      setTotal(res.total);
      if (res.items.length === 0 && res.total > 0 && page > 1) {
        setPage(Math.max(1, Math.ceil(res.total / PAGE_SIZE)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load episodes");
    }
  }, [taskName, quality, assignableOnly, page]);

  /* eslint-disable react-hooks/set-state-in-effect -- server-state refetch when filters change */
  useEffect(() => {
    load();
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // Filters change the result set — always restart from page one.
  function updateFilters(updater: () => void) {
    setSelected([]);
    setPage(1);
    updater();
  }

  function toggle(id: string) {
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : [...s, id],
    );
  }

  async function assign() {
    if (!requestId || selected.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await api.assign(requestId, selected);
      setSelected([]);
      onAssigned();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assign failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ep-task-filter">Task name</Label>
          <Input
            id="ep-task-filter"
            placeholder="e.g. pick cup"
            value={taskName}
            onChange={(e) =>
              updateFilters(() => setTaskName(e.target.value))
            }
            className="w-44"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ep-quality-filter">Quality</Label>
          <select
            id="ep-quality-filter"
            value={quality}
            onChange={(e) =>
              updateFilters(() => setQuality(e.target.value))
            }
            className="h-8 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring"
          >
            <option value="">any quality</option>
            <option value="good">good</option>
            <option value="usable">usable</option>
            <option value="bad">bad</option>
          </select>
        </div>
        <label className="flex h-8 cursor-pointer items-center gap-2 text-sm">
          <Checkbox
            checked={assignableOnly}
            onCheckedChange={(v) =>
              updateFilters(() => setAssignableOnly(v === true))
            }
          />
          assignable only
        </label>
      </div>

      {!requestId && (
        <p className="text-sm text-muted-foreground">
          Select a request to assign episodes to it.
        </p>
      )}

      {selected.length > 0 && requestId && (
        <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2">
          <span className="text-sm">
            {selected.length} episode{selected.length === 1 ? "" : "s"} selected
          </span>
          <ConfirmAction
            title={`Assign ${selected.length} episode${selected.length === 1 ? "" : "s"} to request #${requestId}?`}
            description="Only unassigned episodes graded good or usable can be assigned. The operation is all-or-nothing: if any episode fails a rule, nothing is assigned."
            confirmLabel={`Assign to #${requestId}`}
            disabled={busy}
            onConfirm={assign}
            trigger={
              <Button size="sm" disabled={busy}>
                {busy ? "Assigning…" : `Assign to #${requestId}`}
              </Button>
            }
          />
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            clear
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <ScrollArea className="rounded-lg border">
        <div className="max-h-96 overflow-auto">
          <Table>
            <TableHeader className="sticky top-0 bg-background">
            <TableRow>
              <TableHead className="w-10">
                <span className="sr-only">Select</span>
              </TableHead>
              <TableHead>Episode</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>Robot</TableHead>
              <TableHead>Quality</TableHead>
              <TableHead>Assigned to</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((e) => {
              const taken = e.assigned_request_id !== null;
              return (
                <TableRow
                  key={e.episode_id}
                  data-state={selected.includes(e.episode_id) ? "selected" : undefined}
                >
                  <TableCell>
                    <Checkbox
                      checked={selected.includes(e.episode_id)}
                      disabled={taken}
                      onCheckedChange={() => toggle(e.episode_id)}
                      aria-label={`select ${e.episode_id}`}
                    />
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {e.episode_id}
                  </TableCell>
                  <TableCell className="max-w-40 truncate">
                    {e.task_name}
                  </TableCell>
                  <TableCell>{e.robot_id}</TableCell>
                  <TableCell>
                    <QualityBadge quality={e.quality} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {taken ? `#${e.assigned_request_id}` : "—"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
          </Table>
        </div>
        <ScrollBar orientation="horizontal" />
        {items.length === 0 && !error && (
          <p className="p-4 text-sm text-muted-foreground">
            No episodes match the current filters.
          </p>
        )}
      </ScrollArea>

      <DataPagination
        page={page}
        totalPages={totalPages}
        totalItems={total}
        onChange={setPage}
      />
    </div>
  );
}
