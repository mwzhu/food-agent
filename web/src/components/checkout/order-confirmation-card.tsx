"use client";

import type { OrderConfirmation } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type OrderConfirmationCardProps = {
  confirmation: OrderConfirmation;
};

export function OrderConfirmationCard({ confirmation }: OrderConfirmationCardProps) {
  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Order placed</p>
        <CardTitle>Confirmation {confirmation.confirmation_id}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Metric label="Placed at" value={new Date(confirmation.placed_at).toLocaleString()} />
          <Metric label="Total" value={`$${confirmation.total_cost.toFixed(2)}`} />
          <Metric label="Message" value={confirmation.message || "Order placed."} />
        </div>

        {confirmation.confirmation_url ? (
          <a
            className="text-sm font-medium text-foreground underline underline-offset-4"
            href={confirmation.confirmation_url}
            rel="noreferrer"
            target="_blank"
          >
            Open order confirmation
          </a>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.25rem] border border-border bg-background/70 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
