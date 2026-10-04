"use client";

import { RequireRole } from "@/components/RequireRole";
import { AnalyticsPanel } from "@/components/AnalyticsPanel";
import { PageHeader } from "@/components/PageHeader";

export default function AnalyticsPage() {
  return (
    <RequireRole roles={["operator", "admin"]}>
      <div className="flex max-w-3xl flex-col gap-4">
        <PageHeader
          title="Analytics"
          description="Pick a date range and run. Episodes per day and robot, fulfilment by status with median delivery time, and top tasks — all aggregated in the database."
        />
        <div className="rounded-xl border p-4">
          <AnalyticsPanel />
        </div>
      </div>
    </RequireRole>
  );
}
