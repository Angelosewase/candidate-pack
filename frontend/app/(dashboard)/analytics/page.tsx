"use client";

import { RequireRole } from "@/components/RequireRole";
import { AnalyticsPanel } from "@/components/AnalyticsPanel";

export default function AnalyticsPage() {
  return (
    <RequireRole roles={["operator", "admin"]}>
      <div className="max-w-3xl rounded-xl border p-4">
        <AnalyticsPanel />
      </div>
    </RequireRole>
  );
}
