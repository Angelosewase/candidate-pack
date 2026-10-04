import { Badge } from "@/components/ui/badge";
import type { Quality, RequestStatus } from "@/lib/api";

const STATUS_VARIANT: Record<RequestStatus, "default" | "secondary" | "destructive" | "outline"> = {
  submitted: "secondary",
  in_progress: "default",
  delivered: "outline",
  accepted: "default",
  rejected: "destructive",
};

const STATUS_LABEL: Record<RequestStatus, string> = {
  submitted: "submitted",
  in_progress: "in progress",
  delivered: "delivered",
  accepted: "accepted",
  rejected: "rejected",
};

export function StatusBadge({ status }: { status: RequestStatus }) {
  return <Badge variant={STATUS_VARIANT[status]}>{STATUS_LABEL[status]}</Badge>;
}

const QUALITY_VARIANT: Record<Quality, "default" | "secondary" | "destructive" | "outline"> = {
  good: "default",
  usable: "secondary",
  bad: "destructive",
};

export function QualityBadge({ quality }: { quality: Quality }) {
  return <Badge variant={QUALITY_VARIANT[quality]}>{quality}</Badge>;
}
