"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  SupplementPhaseName,
  SupplementPhaseStatuses,
  SupplementRunEvent,
  SupplementRunLifecycleStatus,
} from "@/lib/supplement-types";
import { formatDateTime, formatLabel } from "@/lib/utils";

import { SupplementPhaseStepper } from "./phase-stepper";

type SupplementRunProgressProps = {
  events: SupplementRunEvent[];
  isStreaming: boolean;
  runStatus: SupplementRunLifecycleStatus;
  currentPhase: SupplementPhaseName | null;
  phaseStatuses: SupplementPhaseStatuses;
  readyCartCount: number;
};

export function SupplementRunProgress({
  events,
  isStreaming,
  runStatus,
  currentPhase,
  phaseStatuses,
  readyCartCount,
}: SupplementRunProgressProps) {
  const visibleEvents = events.slice(-12).reverse();

  return (
    <section className="space-y-5">
      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Run progress
            </p>
            <CardTitle>Live supplement execution timeline</CardTitle>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={runStatusBadge(runStatus)}>{runStatus}</Badge>
            <Badge variant={isStreaming ? "secondary" : "outline"}>
              {isStreaming ? "Streaming" : "Idle"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <SupplementPhaseStepper
            currentPhase={currentPhase}
            phaseStatuses={phaseStatuses}
            runStatus={runStatus}
          />

          <div className="grid gap-3 md:grid-cols-3">
            <Metric label="Events" value={String(events.length)} />
            <Metric
              label="Current phase"
              value={currentPhase ? formatLabel(currentPhase) : runStatus === "completed" ? "Finished" : "Queued"}
            />
            <Metric label="Checkout-ready stores" value={String(readyCartCount)} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Event log</p>
          <CardTitle>What the supplement agent is doing</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {visibleEvents.length ? (
            visibleEvents.map((event) => (
              <article
                key={event.event_id}
                className="rounded-[1.25rem] border border-border bg-background/75 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">{event.message}</p>
                    <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                      {formatLabel(event.event_type)}
                      {event.node_name ? ` · ${formatLabel(event.node_name)}` : ""}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground">{formatDateTime(event.created_at)}</span>
                </div>
              </article>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">Waiting for the first supplement run event.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.25rem] border border-border bg-background/75 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <strong className="mt-1 block text-2xl">{value}</strong>
    </div>
  );
}

function runStatusBadge(status: SupplementRunLifecycleStatus) {
  if (status === "completed") {
    return "success";
  }
  if (status === "awaiting_approval") {
    return "secondary";
  }
  if (status === "failed") {
    return "outline";
  }
  return "default";
}
