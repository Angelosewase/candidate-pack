"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type Analytics, type RequestStatus } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const STATUS_ORDER: RequestStatus[] = [
  "submitted",
  "in_progress",
  "delivered",
  "accepted",
  "rejected",
];

const STATUS_LABEL: Record<RequestStatus, string> = {
  submitted: "submitted",
  in_progress: "in progress",
  delivered: "delivered",
  accepted: "accepted",
  rejected: "rejected",
};

/** Bars/segments drawn from the theme chart palette, red reserved for rejected. */
const ROBOT_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

const STATUS_COLOR: Record<RequestStatus, string> = {
  submitted: "var(--chart-2)",
  in_progress: "var(--chart-1)",
  delivered: "var(--chart-3)",
  accepted: "var(--chart-4)",
  rejected: "var(--destructive)",
};

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-xl border p-3">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-2xl font-semibold tracking-tight">{value}</span>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}

export function AnalyticsPanel() {
  const today = useMemo(() => new Date(), []);
  const [from, setFrom] = useState(() =>
    iso(new Date(today.getTime() - 30 * 86400000)),
  );
  const [to, setTo] = useState(() => iso(today));
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showData, setShowData] = useState(false);

  async function fetchAnalytics(f: string, t: string) {
    setBusy(true);
    setError(null);
    try {
      setData(await api.analytics(f, t));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load analytics");
    } finally {
      setBusy(false);
    }
  }

  /* eslint-disable react-hooks/set-state-in-effect -- initial server-state fetch */
  useEffect(() => {
    fetchAnalytics(from, to);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  function applyPreset(days: number) {
    const t = iso(today);
    const f = iso(new Date(today.getTime() - days * 86400000));
    setFrom(f);
    setTo(t);
    fetchAnalytics(f, t);
  }

  const robots = useMemo(
    () =>
      [...new Set((data?.episodes_per_day ?? []).map((r) => r.robot_id))].sort(),
    [data],
  );

  /** Pivot per-day rows into { day, <robot>: n, total } — weekly buckets for long ranges. */
  const dailySeries = useMemo(() => {
    const rows = data?.episodes_per_day ?? [];
    const days = [...new Set(rows.map((r) => r.day))].sort();
    const bucket = (day: string) => {
      if (days.length <= 45) return day;
      const d = new Date(`${day}T00:00:00Z`);
      const monday = new Date(d);
      monday.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
      return `w/o ${monday.toISOString().slice(0, 10)}`;
    };
    const map = new Map<string, Record<string, number>>();
    for (const r of rows) {
      const key = bucket(r.day);
      const entry = map.get(key) ?? { total: 0 };
      entry[r.robot_id] = (entry[r.robot_id] ?? 0) + r.episodes;
      entry.total += r.episodes;
      map.set(key, entry);
    }
    return [...map.entries()]
      .sort(([a], [b]) => (a < b ? -1 : 1))
      .map(
        ([day, counts]): { day: string; [robot: string]: string | number } => ({
          day,
          ...counts,
        }),
      );
  }, [data]);

  const statusSlices = useMemo(() => {
    if (!data) return [];
    return STATUS_ORDER.map((s) => ({
      name: STATUS_LABEL[s],
      value: data.request_fulfilment.by_status[s] ?? 0,
      color: STATUS_COLOR[s],
    })).filter((s) => s.value > 0);
  }, [data]);

  const totalEpisodes = useMemo(
    () => (data?.episodes_per_day ?? []).reduce((n, r) => n + r.episodes, 0),
    [data],
  );
  const goodEpisodes = useMemo(
    () =>
      (data?.top_tasks_by_good_episodes ?? []).reduce(
        (n, t) => n + t.good_episodes,
        0,
      ),
    [data],
  );
  const topMax = data?.top_tasks_by_good_episodes[0]?.good_episodes ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex items-center gap-1.5">
          {[
            { label: "7d", days: 7 },
            { label: "30d", days: 30 },
            { label: "90d", days: 90 },
          ].map((p) => (
            <Button
              key={p.label}
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => applyPreset(p.days)}
            >
              {p.label}
            </Button>
          ))}
        </div>
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
        <Button size="sm" disabled={busy} onClick={() => fetchAnalytics(from, to)}>
          {busy ? "Loading…" : "Run"}
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {!data && !error && (
        <p className="text-sm text-muted-foreground">
          Loading analytics — all aggregations run in Postgres.
        </p>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
            <Kpi label="Requests" value={String(data.request_fulfilment.total)} />
            <Kpi
              label="Delivered"
              value={String(data.request_fulfilment.delivered_count)}
              hint="submitted in range"
            />
            <Kpi
              label="Median time to delivery"
              value={
                data.request_fulfilment.median_hours_submitted_to_delivered !== null
                  ? `${data.request_fulfilment.median_hours_submitted_to_delivered} h`
                  : "—"
              }
            />
            <Kpi label="Episodes recorded" value={String(totalEpisodes)} />
            <Kpi
              label="Good episodes"
              value={String(goodEpisodes)}
              hint="across top tasks"
            />
          </div>

          <section className="flex flex-col gap-2 rounded-xl border p-4">
            <div>
              <h3 className="text-sm font-medium">Episodes recorded</h3>
              <p className="text-xs text-muted-foreground">
                Per {dailySeries.length > 0 && dailySeries[0].day.startsWith("w/o ") ? "week" : "day"}, stacked by robot
              </p>
            </div>
            {dailySeries.length === 0 ? (
              <p className="text-sm text-muted-foreground">None in range.</p>
            ) : (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={dailySeries} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                    <XAxis
                      dataKey="day"
                      tick={{ fontSize: 11 }}
                      tickLine={false}
                      minTickGap={32}
                      tickFormatter={(v: string) => v.replace("w/o ", "").slice(5)}
                    />
                    <YAxis tick={{ fontSize: 11 }} tickLine={false} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 8,
                        fontSize: 12,
                        background: "var(--popover)",
                        color: "var(--popover-foreground)",
                        borderColor: "var(--border)",
                      }}
                    />
                    {robots.map((robot, i) => (
                      <Bar
                        key={robot}
                        dataKey={robot}
                        stackId="episodes"
                        fill={ROBOT_COLORS[i % ROBOT_COLORS.length]}
                        name={robot}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {robots.map((robot, i) => (
                <span
                  key={robot}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground"
                >
                  <span
                    className="size-2.5 rounded-xs"
                    style={{ background: ROBOT_COLORS[i % ROBOT_COLORS.length] }}
                    aria-hidden
                  />
                  {robot}
                </span>
              ))}
            </div>
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="flex flex-col gap-2 rounded-xl border p-4">
              <div>
                <h3 className="text-sm font-medium">Requests by status</h3>
                <p className="text-xs text-muted-foreground">
                  {data.request_fulfilment.total} requests in range
                </p>
              </div>
              {statusSlices.length === 0 ? (
                <p className="text-sm text-muted-foreground">None in range.</p>
              ) : (
                <div className="flex items-center gap-4">
                  <div className="h-44 w-44 shrink-0">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={statusSlices}
                          dataKey="value"
                          nameKey="name"
                          innerRadius={52}
                          outerRadius={72}
                          paddingAngle={2}
                          strokeWidth={0}
                        >
                          {statusSlices.map((s) => (
                            <Cell key={s.name} fill={s.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            borderRadius: 8,
                            fontSize: 12,
                            background: "var(--popover)",
                            color: "var(--popover-foreground)",
                            borderColor: "var(--border)",
                          }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <ul className="flex min-w-0 flex-1 flex-col gap-1.5">
                    {statusSlices.map((s) => (
                      <li
                        key={s.name}
                        className="flex items-center gap-2 text-sm"
                      >
                        <span
                          className="size-2.5 shrink-0 rounded-xs"
                          style={{ background: s.color }}
                          aria-hidden
                        />
                        <span className="min-w-0 flex-1 truncate">{s.name}</span>
                        <span className="font-medium">{s.value}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            <section className="flex flex-col gap-2 rounded-xl border p-4">
              <div>
                <h3 className="text-sm font-medium">Top tasks by good episodes</h3>
                <p className="text-xs text-muted-foreground">Top 5 in range</p>
              </div>
              {data.top_tasks_by_good_episodes.length === 0 ? (
                <p className="text-sm text-muted-foreground">None in range.</p>
              ) : (
                <ul className="flex flex-col gap-2.5 pt-1">
                  {data.top_tasks_by_good_episodes.map((t) => (
                    <li key={t.task_name} className="flex flex-col gap-1">
                      <div className="flex items-baseline justify-between gap-2 text-sm">
                        <span className="min-w-0 truncate font-medium">
                          {t.task_name}
                        </span>
                        <span className="shrink-0 text-muted-foreground">
                          {t.good_episodes} good
                        </span>
                      </div>
                      <div
                        className="h-2 overflow-hidden rounded-full bg-secondary"
                        role="img"
                        aria-label={`${t.task_name}: ${t.good_episodes} good episodes`}
                      >
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{
                            width: `${topMax === 0 ? 0 : Math.max(4, Math.round((t.good_episodes / topMax) * 100))}%`,
                          }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowData((v) => !v)}
              aria-expanded={showData}
            >
              {showData ? "Hide raw per-day data" : "Show raw per-day data"}
            </Button>
            {showData && (
              <ul className="mt-2 max-h-48 overflow-auto rounded-lg border p-3">
                {dailySeries.map((d) => (
                  <li
                    key={d.day}
                    className="font-mono text-xs text-muted-foreground"
                  >
                    {d.day} ·{" "}
                    {robots.map((r) => `${r} ×${d[r] ?? 0}`).join(" · ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
