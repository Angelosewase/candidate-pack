"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
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

export function ImportPanel() {
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.importCsv>> | null>(null);
  const [history, setHistory] = useState<Awaited<ReturnType<typeof api.listImports>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadHistory() {
    try {
      setHistory(await api.listImports());
    } catch {
      /* non-fatal */
    }
  }

  /* eslint-disable react-hooks/set-state-in-effect -- fetch-on-mount for server state */
  useEffect(() => {
    loadHistory();
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function onFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const report = await api.importCsv(file);
      setResult(report);
      await loadHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="csv-upload">Upload episode CSV (idempotent, max 50MB)</Label>
        <Input
          id="csv-upload"
          type="file"
          accept=".csv,text/csv"
          disabled={busy}
          onChange={(e) => onFile(e.target.files?.[0])}
        />
      </div>
      {busy && <p className="text-sm text-muted-foreground">Importing…</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {result && (
        <div className="rounded-xl border p-3 text-sm">
          <p className="font-medium">
            {result.inserted} inserted · {result.updated} updated · {result.unchanged} unchanged ·{" "}
            {result.skipped} skipped (of {result.total_rows} rows)
          </p>
          {Object.keys(result.skipped_by_reason).length > 0 && (
            <p className="text-muted-foreground">
              Skipped:{" "}
              {Object.entries(result.skipped_by_reason)
                .map(([k, v]) => `${k} ×${v}`)
                .join(", ")}
            </p>
          )}
          {result.skipped_rows.slice(0, 10).map((s) => (
            <p key={s.row} className="font-mono text-xs text-muted-foreground">
              row {s.row} {s.episode_id ?? ""} [{s.reason}] {s.detail}
            </p>
          ))}
          {result.skipped_rows.length > 10 && (
            <p className="text-xs text-muted-foreground">
              …and {result.skipped_rows.length - 10} more (see API response for full report)
            </p>
          )}
          {result.warnings.slice(0, 10).map((w, i) => (
            <p key={i} className="font-mono text-xs text-muted-foreground">
              warn row {w.row} {w.episode_id ?? ""} [{w.reason}] {w.detail}
            </p>
          ))}
        </div>
      )}
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-medium">Recent imports</h3>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">None yet.</p>
        ) : (
          <ScrollArea className="max-h-56 rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead className="text-right">Inserted</TableHead>
                  <TableHead className="text-right">Updated</TableHead>
                  <TableHead className="text-right">Unchanged</TableHead>
                  <TableHead className="text-right">Skipped</TableHead>
                  <TableHead className="text-right">Rows</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((h) => (
                  <TableRow key={h.id}>
                    <TableCell className="font-mono text-xs">#{h.id}</TableCell>
                    <TableCell className="max-w-40 truncate">
                      {h.filename}
                    </TableCell>
                    <TableCell className="text-right">{h.inserted}</TableCell>
                    <TableCell className="text-right">{h.updated}</TableCell>
                    <TableCell className="text-right">{h.unchanged}</TableCell>
                    <TableCell className="text-right">{h.skipped}</TableCell>
                    <TableCell className="text-right text-muted-foreground">
                      {h.total_rows}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </div>
      <Button variant="outline" size="sm" onClick={loadHistory} className="self-start">
        Refresh
      </Button>
    </div>
  );
}
