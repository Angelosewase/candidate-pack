"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Episode } from "@/lib/api";
import { Button } from "@/components/ui/button";

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
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const LIMIT = 30;

  const load = useCallback(
    async (nextOffset: number, reset: boolean) => {
      setError(null);
      try {
        const page = await api.listEpisodes({
          task_name: taskName.trim() || undefined,
          quality: quality || undefined,
          assignable_only: assignableOnly,
          limit: LIMIT,
          offset: nextOffset,
        });
        setItems((prev) => (reset ? page.items : [...prev, ...page.items]));
        setHasMore(page.has_more);
        setOffset(nextOffset);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load episodes");
      }
    },
    [taskName, quality, assignableOnly],
  );

  /* eslint-disable react-hooks/set-state-in-effect -- server-state refetch when filters change */
  useEffect(() => {
    setSelected([]);
    load(0, true);
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
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

  const input =
    "h-8 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          className={input}
          placeholder="Filter by task_name"
          value={taskName}
          onChange={(e) => setTaskName(e.target.value)}
        />
        <select
          className={input}
          value={quality}
          onChange={(e) => setQuality(e.target.value)}
          aria-label="Filter by quality"
        >
          <option value="">any quality</option>
          <option value="good">good</option>
          <option value="usable">usable</option>
          <option value="bad">bad</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={assignableOnly}
            onChange={(e) => setAssignableOnly(e.target.checked)}
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
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">
            {selected.length} selected
          </span>
          <Button size="sm" disabled={busy} onClick={assign}>
            {busy ? "Assigning…" : `Assign to #${requestId}`}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>
            clear
          </Button>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      <ul className="flex flex-col gap-1.5">
        {items.map((e) => (
          <li
            key={e.episode_id}
            className="flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm"
          >
            <input
              type="checkbox"
              checked={selected.includes(e.episode_id)}
              onChange={() => toggle(e.episode_id)}
              disabled={e.assigned_request_id !== null}
              aria-label={`select ${e.episode_id}`}
            />
            <span className="font-mono text-xs">{e.episode_id}</span>
            <span className="min-w-0 flex-1 truncate text-muted-foreground">
              {e.task_name} · {e.robot_id} · {e.quality}
              {e.assigned_request_id !== null && ` · → #${e.assigned_request_id}`}
            </span>
          </li>
        ))}
      </ul>
      {items.length === 0 && !error && (
        <p className="text-sm text-muted-foreground">No episodes match.</p>
      )}
      {hasMore && (
        <Button variant="outline" size="sm" onClick={() => load(offset + LIMIT, false)}>
          Load more
        </Button>
      )}
    </div>
  );
}
