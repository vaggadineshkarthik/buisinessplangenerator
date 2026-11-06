import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/lib/types";

const CONFIG: Record<
  DocumentStatus,
  { label: string; variant: "success" | "warning" | "danger"; icon: typeof CheckCircle2 }
> = {
  ready: { label: "Ready", variant: "success", icon: CheckCircle2 },
  processing: { label: "Processing", variant: "warning", icon: Loader2 },
  error: { label: "Error", variant: "danger", icon: XCircle },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const config = CONFIG[status] ?? CONFIG.processing;
  const Icon = config.icon;
  return (
    <Badge variant={config.variant}>
      <Icon
        className={
          status === "processing" ? "h-3 w-3 animate-spin" : "h-3 w-3"
        }
      />
      {config.label}
    </Badge>
  );
}
