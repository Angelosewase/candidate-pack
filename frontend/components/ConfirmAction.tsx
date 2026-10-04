"use client";

import * as React from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

/** Confirmation dialog for state-changing actions.
 * Render the trigger as a child; `onConfirm` runs only after explicit approval. */
export function ConfirmAction({
  title,
  description,
  confirmLabel = "Confirm",
  destructive = false,
  disabled = false,
  busy = false,
  onConfirm,
  trigger,
}: {
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  disabled?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  trigger: React.ReactElement;
}) {
  const [open, setOpen] = React.useState(false);
  const [working, setWorking] = React.useState(false);

  async function handleConfirm() {
    setWorking(true);
    try {
      await onConfirm();
      setOpen(false);
    } finally {
      setWorking(false);
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        disabled={disabled || busy}
        render={React.cloneElement(
          trigger as React.ReactElement<{ disabled?: boolean }>,
          { disabled: disabled || busy },
        )}
      />
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant={destructive ? "destructive" : "default"}
            disabled={working}
            onClick={(e) => {
              e.preventDefault();
              handleConfirm();
            }}
          >
            {working ? "Working…" : confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

/** Destructive button that asks for confirmation first. */
export function ConfirmButton({
  children,
  title,
  description,
  confirmLabel,
  destructive,
  disabled,
  busy,
  onConfirm,
}: {
  children: React.ReactNode;
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  destructive?: boolean;
  disabled?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
}) {
  return (
    <ConfirmAction
      title={title}
      description={description}
      confirmLabel={confirmLabel}
      destructive={destructive}
      disabled={disabled}
      busy={busy}
      onConfirm={onConfirm}
      trigger={
        <Button
          size="sm"
          variant={destructive ? "destructive" : "default"}
          disabled={disabled || busy}
        >
          {children}
        </Button>
      }
    />
  );
}
