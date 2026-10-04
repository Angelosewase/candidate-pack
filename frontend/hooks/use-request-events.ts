"use client";

import { useEffect, useState } from "react";
import { API_URL, getToken } from "@/lib/api";

export interface DeskEvent {
  type: string;
  request_id: number;
  client_id: number;
  status: string;
}

/** Live request events over SSE (fetch-based so we can send the Bearer token).
 * The server publishes inside the mutating DB transaction, so events only
 * arrive for committed changes. The UI re-fetches state on each event. */
export function useRequestEvents(enabled: boolean) {
  const [lastEvent, setLastEvent] = useState<DeskEvent | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    let stopped = false;

    async function run() {
      // Reconnect loop: a dropped SSE stream re-opens after a pause.
      while (!stopped) {
        try {
          const token = getToken();
          const res = await fetch(`${API_URL}/events`, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            signal: ctrl.signal,
          });
          if (!res.ok || !res.body) throw new Error(`sse ${res.status}`);
          setConnected(true);
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              const chunk = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              for (const line of chunk.split("\n")) {
                const text = line.startsWith(":") ? "" : line.replace(/^data:\s?/, "");
                if (!text || line.startsWith(":")) continue;
                try {
                  setLastEvent(JSON.parse(text) as DeskEvent);
                } catch {
                  /* ignore malformed frames */
                }
              }
            }
          }
        } catch {
          if (ctrl.signal.aborted || stopped) break;
          setConnected(false);
          await new Promise((r) => setTimeout(r, 2000));
        }
      }
    }

    run();
    return () => {
      stopped = true;
      ctrl.abort();
      setConnected(false);
    };
  }, [enabled]);

  return { lastEvent, connected };
}
