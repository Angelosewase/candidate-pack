"use client";

import { RequireRole } from "@/components/RequireRole";
import { ImportPanel } from "@/components/ImportPanel";
import { PageHeader } from "@/components/PageHeader";

export default function ImportPage() {
  return (
    <RequireRole roles={["operator", "admin"]}>
      <div className="flex max-w-3xl flex-col gap-4">
        <PageHeader
          title="Import episodes"
          description="Upload a recording-system CSV. The import is idempotent — re-uploading the same file changes nothing — and every skipped row is reported with a reason."
        />
        <div className="rounded-xl border p-4">
          <ImportPanel />
        </div>
      </div>
    </RequireRole>
  );
}
