"use client";

import { useState } from "react";
import { CalendarClock, Repeat, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SupplementStack } from "@/lib/supplement-types";
import { formatMoney, formatLabel } from "@/lib/utils";

type AutopilotCardProps = {
  stack: SupplementStack;
};

export function AutopilotCard({ stack }: AutopilotCardProps) {
  const [isDismissed, setIsDismissed] = useState(false);
  const [isEnabled, setIsEnabled] = useState(false);

  if (isDismissed) {
    return null;
  }

  return (
    <Card className="border-success/20 bg-[linear-gradient(180deg,rgba(47,122,83,0.12),rgba(255,250,243,0.92))]">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="success">Demo follow-up</Badge>
          <Badge variant="outline">{stack.items.length} products</Badge>
        </div>
        <CardTitle className="mt-2">Want me to handle refills?</CardTitle>
        <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
          Autopilot would watch this stack for monthly spend drift, keep refills on cadence, and hold the line on
          your budget before every reorder.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3">
          <Feature icon={CalendarClock} label="Refill cadence" value="~30 days per item" />
          <Feature
            icon={Repeat}
            label="Budget guardrail"
            value={
              stack.total_monthly_cost !== null
                ? `Watch ${formatMoney(stack.total_monthly_cost, stack.currency || "USD")} / month`
                : "Track monthly spend"
            }
          />
          <Feature icon={ShieldCheck} label="Safety check" value="Pause if the stack changes" />
        </div>

        <div className="space-y-3 rounded-[1.35rem] border border-border bg-background/65 p-4">
          {stack.items.map((item) => (
            <div
              key={`${item.category}-${item.product.store_domain}-${item.product.product_id}`}
              className="flex items-center justify-between gap-3 border-b border-border/70 pb-3 last:border-b-0 last:pb-0"
            >
              <div>
                      <p className="text-sm font-semibold text-foreground">{item.product.title}</p>
                      <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                        {formatLabel(item.category)} - refill in ~30 days
                      </p>
                    </div>
              {item.monthly_cost !== null ? (
                <Badge variant="outline">{formatMoney(item.monthly_cost, item.product.price_range.currency || stack.currency || "USD")}</Badge>
              ) : null}
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-3">
          <Button onClick={() => setIsEnabled(true)} type="button">
            {isEnabled ? "Autopilot enabled (demo)" : "Enable Autopilot"}
          </Button>
          <Button onClick={() => setIsDismissed(true)} type="button" variant="ghost">
            Not now
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Feature({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof CalendarClock;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-[1.2rem] border border-border bg-background/70 p-4">
      <Icon className="size-4 text-secondary-foreground" />
      <p className="mt-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium leading-6 text-foreground">{value}</p>
    </div>
  );
}
