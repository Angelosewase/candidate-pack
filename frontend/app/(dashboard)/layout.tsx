"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { AppSidebar } from "@/components/AppSidebar";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

const TITLES: { prefix: string; title: string }[] = [
  { prefix: "/requests", title: "Requests" },
  { prefix: "/episodes", title: "Episodes" },
  { prefix: "/import", title: "Import" },
  { prefix: "/analytics", title: "Analytics" },
  { prefix: "/users", title: "Users" },
];

/** Authenticated shell: sidebar navigation + page content. */
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  const title =
    TITLES.find((t) => pathname.startsWith(t.prefix))?.title ?? "Workspace";

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
          <SidebarTrigger aria-label="Toggle sidebar" />
          <h1 className="text-sm font-medium">{title}</h1>
        </header>
        <main className="flex-1 p-4 sm:p-6">
          <div className="mx-auto w-full max-w-6xl">{children}</div>
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
