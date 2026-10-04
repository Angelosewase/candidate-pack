"use client";

import { RequireRole } from "@/components/RequireRole";
import { ImportPanel } from "@/components/ImportPanel";

export default function ImportPage() {
  return (
    <RequireRole roles={["operator", "admin"]}>
      <div className="max-w-3xl rounded-xl border p-4">
        <ImportPanel />
      </div>
    </RequireRole>
  );
}
