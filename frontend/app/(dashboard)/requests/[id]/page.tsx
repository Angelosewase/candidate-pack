"use client";

import Link from "next/link";
import { use } from "react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { RequestDetailView } from "@/components/RequestDetail";

export default function RequestPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const requestId = Number(id);
  const { user } = useAuth();
  const isStaff = user?.role === "operator" || user?.role === "admin";

  if (!Number.isInteger(requestId)) {
    return <p className="text-sm text-destructive">Invalid request id.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          render={<Link href="/requests">← All requests</Link>}
        />
        {isStaff && (
          <Button
            size="sm"
            variant="outline"
            render={
              <Link href={`/episodes?request=${requestId}`}>
                Assign episodes
              </Link>
            }
          />
        )}
      </div>
      <div className="rounded-xl border p-4">
        <RequestDetailView
          requestId={requestId}
          onChanged={() => {}}
          canAssign={isStaff}
        />
      </div>
    </div>
  );
}
