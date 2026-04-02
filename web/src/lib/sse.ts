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
    if (!(event instanceof MessageEvent) || typeof event.data !== "string" || event.data.length === 0) {
      return;
    }

    try {
      const payload = JSON.parse(event.data) as RunEvent;
      onEvent(payload);
    } catch (error) {
      console.error("Failed to parse run stream event.", {
        error,
        eventType: event.type,
        rawData: event.data,
      });
    }
  };

  RUN_EVENT_TYPES.forEach((eventType) => {
    eventSource.addEventListener(eventType, handleTypedEvent);
  });

  eventSource.onopen = () => onConnectionChange?.(true);
  eventSource.onerror = () => onConnectionChange?.(false);

  return eventSource;
}
