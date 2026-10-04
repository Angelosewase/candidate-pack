"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { RequireRole } from "@/components/RequireRole";
import { EpisodeBrowser } from "@/components/EpisodeBrowser";

function EpisodesContent() {
  const searchParams = useSearchParams();
  const raw = searchParams.get("request");
  const requestId = raw !== null && /^\d+$/.test(raw) ? Number(raw) : null;

  return (
    <div className="flex flex-col gap-3">
      {requestId !== null && (
        <p className="rounded-lg border bg-muted/50 px-3 py-2 text-sm">
          Assigning to request{" "}
          <Link
            href={`/requests/${requestId}`}
            className="font-medium underline underline-offset-4"
          >
            #{requestId}
          </Link>
        </p>
      )}
      <div className="rounded-xl border p-4">
        <EpisodeBrowser requestId={requestId} onAssigned={() => {}} />
      </div>
    </div>
  );
}

export default function EpisodesPage() {
  return (
    <RequireRole roles={["operator", "admin"]}>
      <Suspense
        fallback={
          <p className="text-sm text-muted-foreground">Loading episodes…</p>
        }
      >
        <EpisodesContent />
      </Suspense>
    </RequireRole>
  );
}
