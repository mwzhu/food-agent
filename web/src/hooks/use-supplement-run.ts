"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveSupplementRun,
  createSupplementRun,
  getSupplementRun,
  getSupplementRunStreamUrl,
} from "@/lib/api";
import type {
  SupplementPhaseStatus,
  SupplementRunApproveRequest,
  SupplementRunCreateRequest,
  SupplementRunEvent,
  SupplementRunEventType,
  SupplementRunLifecycleStatus,
  SupplementRunRead,
  SupplementStateSnapshot,
} from "@/lib/supplement-types";

const SUPPLEMENT_RUN_EVENT_TYPES: SupplementRunEventType[] = [
  "phase_started",
  "phase_completed",
  "node_entered",
  "node_completed",
  "approval_requested",
  "approval_resolved",
  "run_completed",
  "error",
];

type SupplementStreamState = {
  events: SupplementRunEvent[];
  isStreaming: boolean;
};

export function useSupplementRun(runId: string, pollWhileRunning = false) {
  return useQuery({
    queryKey: ["supplement-run", runId],
    queryFn: () => getSupplementRun(runId),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      if (!pollWhileRunning) {
        return false;
      }
      return query.state.data?.status === "running" ? 2000 : false;
    },
  });
}

export function useCreateSupplementRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: SupplementRunCreateRequest) => createSupplementRun(payload),
    onSuccess: (run) => {
      queryClient.setQueryData<SupplementRunRead>(["supplement-run", run.run_id], run);
    },
  });
}

export function useApproveSupplementRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ runId, payload }: { runId: string; payload: SupplementRunApproveRequest }) =>
      approveSupplementRun(runId, payload),
    onSuccess: (run) => {
      queryClient.setQueryData<SupplementRunRead>(["supplement-run", run.run_id], run);
    },
  });
}

export function useSupplementRunStream(runId: string): SupplementStreamState {
  const queryClient = useQueryClient();
  const [events, setEvents] = useState<SupplementRunEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    if (!runId) {
      setEvents([]);
      return;
    }
    const cachedEvents = queryClient.getQueryData<SupplementRunEvent[]>(["supplement-run-events", runId]) ?? [];
    setEvents(cachedEvents);
  }, [queryClient, runId]);

  useEffect(() => {
    if (!runId) {
      return;
    }

    const handleEvent = (event: SupplementRunEvent) => {
      setEvents((previousEvents) => {
        if (previousEvents.some((existingEvent) => existingEvent.event_id === event.event_id)) {
          return previousEvents;
        }

        const nextEvents = [...previousEvents, event];
        queryClient.setQueryData(["supplement-run-events", runId], nextEvents);
        return nextEvents;
      });

      queryClient.setQueryData<SupplementRunRead | undefined>(["supplement-run", runId], (currentRun) => {
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
        void queryClient.invalidateQueries({ queryKey: ["supplement-run", runId] });
      }
    };

    const eventSource = subscribeToSupplementRun(runId, handleEvent, setIsStreaming);
    return () => {
      eventSource.close();
      setIsStreaming(false);
    };
  }, [queryClient, runId]);

  return { events, isStreaming };
}

function subscribeToSupplementRun(
  runId: string,
  onEvent: (event: SupplementRunEvent) => void,
  onConnectionChange?: (connected: boolean) => void,
): EventSource {
  const eventSource = new EventSource(getSupplementRunStreamUrl(runId));

  const handleTypedEvent = (event: Event) => {
    if (!(event instanceof MessageEvent) || typeof event.data !== "string" || event.data.length === 0) {
      return;
    }

    try {
      const payload = JSON.parse(event.data) as SupplementRunEvent;
      onEvent(payload);
    } catch (error) {
      console.error("Failed to parse supplement run stream event.", {
        error,
        eventType: event.type,
        rawData: event.data,
      });
    }
  };

  SUPPLEMENT_RUN_EVENT_TYPES.forEach((eventType) => {
    eventSource.addEventListener(eventType, handleTypedEvent);
  });

  eventSource.onopen = () => onConnectionChange?.(true);
  eventSource.onerror = () => onConnectionChange?.(false);

  return eventSource;
}

function isTerminalEvent(event: SupplementRunEvent): boolean {
  switch (event.event_type) {
    case "approval_requested":
    case "run_completed":
    case "error":
      return true;
    case "phase_started":
    case "phase_completed":
    case "node_entered":
    case "node_completed":
    case "approval_resolved":
      return false;
    default:
      return assertNever(event);
  }
}

function deriveRunStatus(event: SupplementRunEvent): SupplementRunLifecycleStatus {
  switch (event.event_type) {
    case "error":
      return "failed";
    case "approval_requested":
      return "awaiting_approval";
    case "run_completed":
      return event.data.status;
    case "phase_started":
    case "phase_completed":
    case "node_entered":
    case "node_completed":
    case "approval_resolved":
      return "running";
    default:
      return assertNever(event);
  }
}

function applyEventToSnapshot(
  snapshot: SupplementStateSnapshot,
  event: SupplementRunEvent,
): SupplementStateSnapshot {
  const nextSnapshot: SupplementStateSnapshot = {
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

  if (event.event_type === "approval_resolved") {
    const approvedStoreDomains = event.data.approved_store_domains;
    if (Array.isArray(approvedStoreDomains)) {
      nextSnapshot.approved_store_domains = approvedStoreDomains.filter(
        (domain): domain is string => typeof domain === "string",
      );
    }
  }

  return nextSnapshot;
}

function patchPhaseStatus(
  currentStatus: SupplementPhaseStatus,
  event: SupplementRunEvent,
): SupplementPhaseStatus {
  switch (event.event_type) {
    case "phase_started":
      return "running";
    case "phase_completed":
      if (event.data.decision === "failed" || event.data.status === "failed") {
        return "failed";
      }
      return "completed";
    case "node_entered":
    case "node_completed":
    case "approval_requested":
    case "approval_resolved":
    case "run_completed":
    case "error":
      return currentStatus;
    default:
      return assertNever(event);
  }
}

function assertNever(value: never): never {
  throw new Error(`Unhandled supplement run event: ${JSON.stringify(value)}`);
}
