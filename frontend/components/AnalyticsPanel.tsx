"use client";

import { useState } from "react";
import { api, type Analytics } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

export function AnalyticsPanel() {
  const today = new Date();
  const monthAgo = new Date(today.getTime() - 30 * 86400000);
  const [from, setFrom] = useState(iso(monthAgo));
  const [to, setTo] = useState(iso(today));
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      setData(await api.analytics(from, to));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load analytics");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2 text-sm">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="analytics-from">From</Label>
          <Input
            id="analytics-from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="analytics-to">To</Label>
          <Input
            id="analytics-to"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <Button size="sm" disabled={busy} onClick={load}>
          {busy ? "…" : "Run"}
        </Button>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {!data && !error && (
        <p className="text-sm text-muted-foreground">Pick a range and run. All aggregations run in Postgres.</p>
      )}
      {data && (
        <div className="flex flex-col gap-3 text-sm">
          <section className="rounded-xl border p-3">
            <h3 className="font-medium">Fulfilment</h3>
            <p className="text-muted-foreground">
              {data.request_fulfilment.total} requests ·{" "}
              {Object.entries(data.request_fulfilment.by_status)
                .map(([k, v]) => `${k}: ${v}`)
                .join(" · ")}
            </p>
            <p className="text-muted-foreground">
              Median submitted → delivered:{" "}
              {data.request_fulfilment.median_hours_submitted_to_delivered ?? "—"} h
              {data.request_fulfilment.delivered_count > 0 &&
                ` (n=${data.request_fulfilment.delivered_count})`}
            </p>
          </section>
          <section className="rounded-xl border p-3">
            <h3 className="font-medium">Top tasks by good episodes</h3>
            {data.top_tasks_by_good_episodes.length === 0 ? (
              <p className="text-muted-foreground">None in range.</p>
            ) : (
              <ul>
                {data.top_tasks_by_good_episodes.map((t) => (
                  <li key={t.task_name}>
                    {t.task_name} — <span className="text-muted-foreground">{t.good_episodes} good</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="rounded-xl border p-3">
            <h3 className="font-medium">Episodes per day / robot ({data.episodes_per_day.length})</h3>
            <ul className="max-h-48 overflow-auto">
              {data.episodes_per_day.slice(0, 50).map((r, i) => (
                <li key={i} className="font-mono text-xs text-muted-foreground">
                  {r.day} {r.robot_id} ×{r.episodes}
                </li>
              ))}
            </ul>
            {data.episodes_per_day.length > 50 && (
              <p className="text-xs text-muted-foreground">
                …{data.episodes_per_day.length - 50} more rows
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
