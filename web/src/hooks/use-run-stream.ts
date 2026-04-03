"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { subscribeToRun } from "@/lib/sse";
import type { PhaseStatus, PlannerStateSnapshot, RunEvent, RunLifecycleStatus, RunRead } from "@/lib/types";

type StreamState = {
  events: RunEvent[];
  isStreaming: boolean;
};

export function useRunStream(runId: string): StreamState {
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    const cachedEvents = queryClient.getQueryData<RunEvent[]>(["run-events", runId]) ?? [];
    setEvents(cachedEvents);
  }, [queryClient, runId]);

  useEffect(() => {
    const handleEvent = (event: RunEvent) => {
      setEvents((previousEvents) => {
        if (previousEvents.some((existingEvent) => existingEvent.event_id === event.event_id)) {
          return previousEvents;
        }
        const nextEvents = [...previousEvents, event];
        queryClient.setQueryData(["run-events", runId], nextEvents);
        return nextEvents;
      });

      queryClient.setQueryData<RunRead | undefined>(["run", runId], (currentRun) => {
        if (!currentRun) {
          return currentRun;
        }

        const nextSnapshot = applyEventToSnapshot(currentRun.state_snapshot, event);
        return {
          ...currentRun,
          status: deriveRunStatus(event),
          state_snapshot: nextSnapshot,
        };
      });

      if (isTerminalEvent(event)) {
        setIsStreaming(false);
        void queryClient.invalidateQueries({ queryKey: ["run", runId] });
        void queryClient.invalidateQueries({ queryKey: ["runs"] });
      }
    };

    const eventSource = subscribeToRun(runId, handleEvent, setIsStreaming);
    return () => {
      eventSource.close();
      setIsStreaming(false);
    };
  }, [queryClient, runId]);

  return { events, isStreaming };
}

function isTerminalEvent(event: RunEvent): boolean {
  switch (event.event_type) {
    case "run_completed":
    case "error":
      return true;
    case "phase_started":
    case "phase_completed":
    case "node_entered":
    case "node_completed":
      return false;
    default:
      return assertNever(event);
  }
}

function deriveRunStatus(event: RunEvent): RunLifecycleStatus {
  switch (event.event_type) {
    case "error":
      return "failed";
    case "run_completed":
      return event.data.status;
    case "phase_started":
    case "phase_completed":
    case "node_entered":
    case "node_completed":
      return "running";
    default:
      return assertNever(event);
  }
}

function applyEventToSnapshot(snapshot: PlannerStateSnapshot, event: RunEvent): PlannerStateSnapshot {
  const nextSnapshot: PlannerStateSnapshot = {
    ...snapshot,
    current_node: event.node_name ?? snapshot.current_node,
    current_phase: event.phase ?? snapshot.current_phase,
    latest_error: event.event_type === "error" ? event.message : snapshot.latest_error,
  };

  const phase = event.phase;
  if (phase) {
    nextSnapshot.phase_statuses = {
      ...nextSnapshot.phase_statuses,
      [phase]: patchPhaseStatus(nextSnapshot.phase_statuses[phase], event),
    };
  }

  nextSnapshot.status = deriveRunStatus(event);

  return nextSnapshot;
}

function patchPhaseStatus(currentStatus: PhaseStatus, event: RunEvent): PhaseStatus {
  switch (event.event_type) {
    case "phase_started":
      return "running";
    case "phase_completed":
      if (event.data.passed === false || event.data.status === "failed") {
        return "failed";
      }
      return "completed";
    case "node_entered":
    case "node_completed":
    case "run_completed":
    case "error":
      return currentStatus;
    default:
      return assertNever(event);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled run event: ${JSON.stringify(value)}`);
}
