"use client";

import { getRunStreamUrl } from "@/lib/api";
import type { RunEvent, RunEventType } from "@/lib/types";

const RUN_EVENT_TYPES: RunEventType[] = [
  "phase_started",
  "phase_completed",
  "node_entered",
  "node_completed",
  "run_completed",
  "error",
];

export function subscribeToRun(
  runId: string,
  onEvent: (event: RunEvent) => void,
  onConnectionChange?: (connected: boolean) => void,
): EventSource {
  const eventSource = new EventSource(getRunStreamUrl(runId));

  const handleTypedEvent = (event: Event) => {
    const messageEvent = event as MessageEvent<string>;
    const payload = JSON.parse(messageEvent.data) as RunEvent;
    onEvent(payload);
  };

  RUN_EVENT_TYPES.forEach((eventType) => {
    eventSource.addEventListener(eventType, handleTypedEvent);
  });

  eventSource.onopen = () => onConnectionChange?.(true);
  eventSource.onerror = () => onConnectionChange?.(false);

  return eventSource;
}
