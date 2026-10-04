"use client";

import { RequireRole } from "@/components/RequireRole";
import { UsersPanel } from "@/components/UsersPanel";

export default function UsersPage() {
  return (
    <RequireRole roles={["admin"]}>
      <div className="rounded-xl border p-4">
        <UsersPanel />
      </div>
    </RequireRole>
  );
}
