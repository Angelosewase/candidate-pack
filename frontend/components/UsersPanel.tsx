"use client";

import { useEffect, useState } from "react";
import { api, type Role, type User } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfirmAction } from "@/components/ConfirmAction";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export function UsersPanel() {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("client");
  const [pendingRole, setPendingRole] = useState<{
    user: User;
    role: Role;
  } | null>(null);

  async function load() {
    setError(null);
    try {
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users");
    }
  }

  /* eslint-disable react-hooks/set-state-in-effect -- fetch-on-mount for server state */
  useEffect(() => {
    load();
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.createUser({ email, name, password, role });
      setEmail("");
      setName("");
      setPassword("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  async function toggleActive(u: User) {
    setError(null);
    try {
      await api.updateUser(u.id, { is_active: !u.is_active });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function setRoleFor(u: User, next: Role) {
    setError(null);
    try {
      await api.updateUser(u.id, { role: next });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  const selectClass =
    "h-8 rounded-lg border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring";

  return (
    <div className="flex flex-col gap-3">
      <form
        onSubmit={create}
        className="grid grid-cols-2 gap-2 rounded-xl border p-3 sm:grid-cols-3 lg:grid-cols-[1fr_1fr_1fr_auto_auto]"
      >
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-user-email">Email</Label>
          <Input
            id="new-user-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-user-name">Name</Label>
          <Input
            id="new-user-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-user-password">Password</Label>
          <Input
            id="new-user-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={6}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="new-user-role">Role</Label>
          <select
            id="new-user-role"
            className={selectClass}
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
          >
            <option value="client">client</option>
            <option value="operator">operator</option>
            <option value="admin">admin</option>
          </select>
        </div>
        <div className="flex items-end">
          <Button size="sm" type="submit" className="w-full">
            Create user
          </Button>
        </div>
      </form>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <ScrollArea className="max-h-96 rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {u.email}
                </TableCell>
                <TableCell>
                  <select
                    className={selectClass}
                    value={u.role}
                    onChange={(e) => {
                      const next = e.target.value as Role;
                      if (next !== u.role) setPendingRole({ user: u, role: next });
                    }}
                    aria-label={`role for ${u.email}`}
                  >
                    <option value="client">client</option>
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                  </select>
                </TableCell>
                <TableCell>
                  <Badge variant={u.is_active ? "default" : "destructive"}>
                    {u.is_active ? "active" : "disabled"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <ConfirmAction
                    title={`${u.is_active ? "Disable" : "Enable"} ${u.name}?`}
                    description={
                      u.is_active
                        ? "They will be signed out immediately: every request re-checks the account, so existing tokens stop working."
                        : "They will be able to sign in again."
                    }
                    confirmLabel={u.is_active ? "Disable" : "Enable"}
                    destructive={u.is_active}
                    onConfirm={() => toggleActive(u)}
                    trigger={
                      <Button size="xs" variant="outline">
                        {u.is_active ? "disable" : "enable"}
                      </Button>
                    }
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {users.length === 0 && !error && (
          <p className="p-4 text-sm text-muted-foreground">No users found.</p>
        )}
      </ScrollArea>

      <AlertDialog
        open={pendingRole !== null}
        onOpenChange={(open) => {
          if (!open) setPendingRole(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Change {pendingRole?.user.name}’s role to {pendingRole?.role}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Permissions apply immediately: the account is re-checked on every
              request, so the next API call already uses the new role.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                if (pendingRole) {
                  const { user, role } = pendingRole;
                  setPendingRole(null);
                  setRoleFor(user, role);
                }
              }}
            >
              Change role
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
