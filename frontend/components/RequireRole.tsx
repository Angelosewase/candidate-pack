"use client";

import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import type { Role } from "@/lib/api";

/** Client-side role gate (the API remains the real enforcement point). */
export function RequireRole({
  roles,
  children,
}: {
  roles: Role[];
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  if (loading || !user) return null;
  if (!roles.includes(user.role)) {
    return (
      <div className="flex max-w-md flex-col gap-3 rounded-xl border p-6">
        <h2 className="text-base font-medium">Not permitted</h2>
        <p className="text-sm text-muted-foreground">
          Your role ({user.role}) cannot access this page.
        </p>
        <Button
          size="sm"
          variant="outline"
          className="self-start"
          render={<Link href="/requests">Back to requests</Link>}
        />
      </div>
    );
  }
  return <>{children}</>;
}
