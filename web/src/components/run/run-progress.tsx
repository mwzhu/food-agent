"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PhaseName, PhaseStatuses, RunEvent, RunLifecycleStatus } from "@/lib/types";
import { formatDateTime, formatDuration, formatLabel } from "@/lib/utils";

import { PhaseStepper } from "./phase-stepper";

type RunProgressProps = {
  events: RunEvent[];
  isStreaming: boolean;
  runStatus: RunLifecycleStatus;
  currentPhase: PhaseName | null;
  phaseStatuses: PhaseStatuses;
};

export function RunProgress({
  events,
  isStreaming,
  runStatus,
  currentPhase,
  phaseStatuses,
}: RunProgressProps) {
  const phaseDurations = buildPhaseDurations(events);
  const visibleEvents = events.slice(-12).reverse();

  return (
    <section className="space-y-5">
      <Card>
        <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Run progress
            </p>
            <CardTitle>Live execution timeline</CardTitle>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={runStatusBadge(runStatus)}>
              {runStatus}
            </Badge>
            <Badge variant={isStreaming ? "secondary" : "outline"}>
              {isStreaming ? "Streaming" : "Disconnected"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <PhaseStepper currentPhase={currentPhase} phaseStatuses={phaseStatuses} runStatus={runStatus} />

          <div className="grid gap-3 md:grid-cols-3">
            <Metric label="Events" value={String(events.length)} />
            <Metric
              label="Current phase"
              value={currentPhase ? formatLabel(currentPhase) : runStatus === "completed" ? "Finished" : "Queued"}
            />
            <Metric
              label="Planning time"
              value={phaseDurations.planning ? formatDuration(phaseDurations.planning) : "In progress"}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Event log</p>
          <CardTitle>What the planner is doing</CardTitle>
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
                      {formatLabel(event.event_type)} {event.node_name ? `· ${formatLabel(event.node_name)}` : ""}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground">{formatDateTime(event.created_at)}</span>
                </div>
              </article>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">Waiting for the first run event.</p>
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

function buildPhaseDurations(events: RunEvent[]) {
  const starts = new Map<string, number>();
  const durations: Record<string, number> = {};

  events.forEach((event) => {
    if (!event.phase) {
      return;
    }
    const timestamp = new Date(event.created_at).getTime();
    if (event.event_type === "phase_started") {
      starts.set(event.phase, timestamp);
    }
    if (event.event_type === "phase_completed") {
      const start = starts.get(event.phase);
      if (start) {
        durations[event.phase] = timestamp - start;
      }
    }
  });

  return durations;
}

function runStatusBadge(status: RunLifecycleStatus) {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "outline";
  }
  return "default";
}
