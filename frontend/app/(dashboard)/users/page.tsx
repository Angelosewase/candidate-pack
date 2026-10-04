"use client";

import { RequireRole } from "@/components/RequireRole";
import { UsersPanel } from "@/components/UsersPanel";
import { PageHeader } from "@/components/PageHeader";

export default function UsersPage() {
  return (
    <RequireRole roles={["admin"]}>
      <div className="flex flex-col gap-4">
        <PageHeader
          title="Users"
          description="Create accounts, change roles, or disable access. Changes apply immediately — disabled users are signed out on their next request."
        />
        <div className="rounded-xl border p-4">
          <UsersPanel />
        </div>
      </div>
    </RequireRole>
  );
}
