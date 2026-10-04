"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChartColumn,
  Clapperboard,
  ClipboardList,
  Database,
  LogOut,
  Upload,
  Users,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { useRequestEvents } from "@/hooks/use-request-events";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";

interface NavItem {
  href: string;
  label: string;
  icon: typeof ClipboardList;
  roles: ("client" | "operator" | "admin")[];
  matchPrefix?: boolean;
}

const NAV: NavItem[] = [
  {
    href: "/requests",
    label: "Requests",
    icon: ClipboardList,
    roles: ["client", "operator", "admin"],
    matchPrefix: true,
  },
  {
    href: "/episodes",
    label: "Episodes",
    icon: Clapperboard,
    roles: ["operator", "admin"],
  },
  {
    href: "/import",
    label: "Import",
    icon: Upload,
    roles: ["operator", "admin"],
  },
  {
    href: "/analytics",
    label: "Analytics",
    icon: ChartColumn,
    roles: ["operator", "admin"],
  },
  {
    href: "/users",
    label: "Users",
    icon: Users,
    roles: ["admin"],
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const isStaff = user?.role === "operator" || user?.role === "admin";
  const { connected } = useRequestEvents(!!user && isStaff);

  const items = NAV.filter(
    (item) => user && item.roles.includes(user.role),
  );

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              size="lg"
              tooltip="Dataset Request Desk"
              render={<Link href="/requests" />}
            >
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Database className="size-4" aria-hidden />
              </span>
              <span className="flex flex-col leading-tight">
                <span className="font-medium">Request Desk</span>
                <span className="text-xs text-muted-foreground">
                  Robotics datasets
                </span>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {items.map((item) => {
                const active =
                  item.matchPrefix && item.href !== "/"
                    ? pathname === item.href ||
                      pathname.startsWith(`${item.href}/`)
                    : pathname === item.href;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      isActive={active}
                      tooltip={item.label}
                      render={<Link href={item.href} />}
                    >
                      <item.icon aria-hidden />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          {isStaff && (
            <SidebarMenuItem>
              <span
                className={`flex items-center gap-2 px-2 py-1 text-xs ${
                  connected ? "text-green-600" : "text-muted-foreground"
                }`}
              >
                <span
                  className={`size-1.5 rounded-full ${
                    connected ? "bg-green-600" : "bg-muted-foreground"
                  }`}
                  aria-hidden
                />
                {connected ? "Live" : "Reconnecting…"}
              </span>
            </SidebarMenuItem>
          )}
          {user && (
            <SidebarMenuItem>
              <div className="flex flex-col gap-0.5 px-2 py-1 text-xs">
                <span className="truncate font-medium">{user.name}</span>
                <span className="text-muted-foreground">{user.role}</span>
              </div>
            </SidebarMenuItem>
          )}
          <SidebarMenuItem>
            <SidebarMenuButton tooltip="Sign out" onClick={logout}>
              <LogOut aria-hidden />
              <span>Sign out</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
