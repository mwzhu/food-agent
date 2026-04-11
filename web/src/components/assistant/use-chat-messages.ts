"use client";

import { useEffect, useReducer, useRef } from "react";
import type { Dispatch, MutableRefObject } from "react";

import type {
  HealthProfile,
  SupplementRunEvent,
  SupplementStateSnapshot,
} from "@/lib/supplement-types";
import { formatLabel, formatMoney, joinList } from "@/lib/utils";

import type { ChatMessage } from "./message-types";
import {
  createAssistantText,
  createAutopilotCard,
  createCheckoutCard,
  createComparisonCard,
  createIntakeForm,
  createProfileConfirmed,
  createSafetyCard,
  createSearchProgress,
  createStackCard,
  createThinking,
  createUserText,
} from "./message-types";

type UseChatMessagesOptions = {
  userId: string;
  runId: string | null;
  events: SupplementRunEvent[];
  snapshot: SupplementStateSnapshot | null;
};

type ChatAction =
  | { type: "RESET"; userId: string }
  | { type: "ADD"; message: ChatMessage }
  | { type: "ADD_MANY"; messages: ChatMessage[] }
  | { type: "UPSERT"; message: ChatMessage }
  | { type: "REPLACE_LAST_THINKING"; message: ChatMessage };

type SnapshotKeys = Record<
  "discovery" | "comparison" | "stack" | "safety" | "checkout" | "autopilot",
  string
>;

export function useChatMessages({
  userId,
  runId,
  events,
  snapshot,
}: UseChatMessagesOptions) {
  const [messages, dispatch] = useReducer(chatReducer, userId, buildIntroMessages);
  const processedEventIdsRef = useRef<Set<string>>(new Set());
  const narratedCardsRef = useRef<Set<string>>(new Set());
  const snapshotKeysRef = useRef<SnapshotKeys>(createSnapshotKeys());
  const previousRunIdRef = useRef<string | null>(runId);

  useEffect(() => {
    resetTracking(processedEventIdsRef, narratedCardsRef, snapshotKeysRef);
    previousRunIdRef.current = null;
    dispatch({ type: "RESET", userId });
  }, [userId]);

  useEffect(() => {
    if (previousRunIdRef.current === runId) {
      return;
    }

    resetTracking(processedEventIdsRef, narratedCardsRef, snapshotKeysRef);
    previousRunIdRef.current = runId;
  }, [runId]);

  useEffect(() => {
    if (!runId || !events.length) {
      return;
    }

    for (const event of events) {
      if (processedEventIdsRef.current.has(event.event_id)) {
        continue;
      }

      processedEventIdsRef.current.add(event.event_id);
      handleStreamEvent(event, dispatch);
    }
  }, [events, runId]);

  useEffect(() => {
    if (!runId || !snapshot) {
      return;
    }

    const discoveryComplete =
      snapshot.phase_statuses.discovery === "completed" ||
      snapshot.phase_statuses.discovery === "failed" ||
      (snapshot.current_phase !== "discovery" && snapshot.discovery_results.length > 0);
    const discoveryKey = snapshot.discovery_results.length
      ? JSON.stringify([snapshot.discovery_results, discoveryComplete])
      : "";
    if (discoveryKey && discoveryKey !== snapshotKeysRef.current.discovery) {
      snapshotKeysRef.current.discovery = discoveryKey;
      dispatch({
        type: "UPSERT",
        message: createSearchProgress(runId, snapshot.discovery_results, discoveryComplete),
      });
    }

    const comparisonKey = snapshot.product_comparisons.length
      ? JSON.stringify(snapshot.product_comparisons)
      : "";
    if (comparisonKey && comparisonKey !== snapshotKeysRef.current.comparison) {
      snapshotKeysRef.current.comparison = comparisonKey;
      if (!narratedCardsRef.current.has(`comparison:${runId}`)) {
        narratedCardsRef.current.add(`comparison:${runId}`);
        dispatch({
          type: "ADD",
          message: createAssistantText("Here's how the options compare."),
        });
      }
      dispatch({
        type: "UPSERT",
        message: createComparisonCard(runId, snapshot.product_comparisons),
      });
    }

    const stackKey = snapshot.recommended_stack
      ? JSON.stringify(snapshot.recommended_stack)
      : "";
    if (stackKey && stackKey !== snapshotKeysRef.current.stack) {
      const stack = snapshot.recommended_stack;
      if (!stack) {
        return;
      }

      snapshotKeysRef.current.stack = stackKey;
      if (!narratedCardsRef.current.has(`stack:${runId}`)) {
        narratedCardsRef.current.add(`stack:${runId}`);
        dispatch({
          type: "ADD",
          message: createAssistantText("Based on your goals, here's your recommended stack."),
        });
      }
      dispatch({
        type: "UPSERT",
        message: createStackCard(runId, stack),
      });
    }

    const safetyKey = snapshot.critic_verdict
      ? JSON.stringify(snapshot.critic_verdict)
      : "";
    if (safetyKey && safetyKey !== snapshotKeysRef.current.safety) {
      const verdict = snapshot.critic_verdict;
      if (!verdict) {
        return;
      }

      snapshotKeysRef.current.safety = safetyKey;
      dispatch({
        type: "UPSERT",
        message: createSafetyCard(runId, verdict),
      });
    }

    const checkoutKey =
      snapshot.store_carts.length || snapshot.approved_store_domains.length
        ? JSON.stringify([snapshot.store_carts, snapshot.approved_store_domains, snapshot.status])
        : "";
    if (checkoutKey && checkoutKey !== snapshotKeysRef.current.checkout) {
      snapshotKeysRef.current.checkout = checkoutKey;
      dispatch({
        type: "UPSERT",
        message: createCheckoutCard(
          runId,
          snapshot.status,
          snapshot.store_carts,
          snapshot.approved_store_domains,
        ),
      });
    }

    const autopilotKey =
      snapshot.status === "completed" && snapshot.recommended_stack
        ? JSON.stringify([snapshot.status, snapshot.recommended_stack])
        : "";
    if (autopilotKey && autopilotKey !== snapshotKeysRef.current.autopilot) {
      const stack = snapshot.recommended_stack;
      if (!stack) {
        return;
      }

      snapshotKeysRef.current.autopilot = autopilotKey;
      dispatch({
        type: "UPSERT",
        message: createAutopilotCard(runId, stack),
      });
    }
  }, [runId, snapshot]);

  const resetConversation = () => {
    resetTracking(processedEventIdsRef, narratedCardsRef, snapshotKeysRef);
    previousRunIdRef.current = null;
    dispatch({ type: "RESET", userId });
  };

  const startRun = (profile: HealthProfile, nextRunId: string) => {
    dispatch({
      type: "ADD_MANY",
      messages: [
        createUserText(summarizeHealthProfile(profile), `start:${nextRunId}:user`),
        createProfileConfirmed(profile, `start:${nextRunId}:profile`),
        createThinking("Setting up your supplement run...", `start:${nextRunId}:thinking`),
      ],
    });
  };

  const guideToIntake = (text: string) => {
    dispatch({
      type: "ADD_MANY",
      messages: [
        createUserText(text),
        createAssistantText(
          "I can work with that. Use the intake card above to confirm age, weight, allergies, and budget before I start shopping.",
        ),
      ],
    });
  };

  const explainLockedConversation = (text: string) => {
    dispatch({
      type: "ADD_MANY",
      messages: [
        createUserText(text),
        createAssistantText(
          "I'm still working on this stack, and mid-run edits aren't wired up yet. Finish or reset this run, then start a new stack to revise it.",
        ),
      ],
    });
  };

  return {
    messages,
    guideToIntake,
    explainLockedConversation,
    resetConversation,
    startRun,
  };
}

function handleStreamEvent(event: SupplementRunEvent, dispatch: Dispatch<ChatAction>) {
  switch (event.event_type) {
    case "phase_started":
      if (event.phase === "memory") {
        dispatch({
          type: "REPLACE_LAST_THINKING",
          message: createThinking("Analyzing your health profile..."),
        });
        return;
      }

      if (event.phase === "discovery") {
        dispatch({
          type: "ADD_MANY",
          messages: [
            createAssistantText("Searching verified stores..."),
            createThinking("Querying stores..."),
          ],
        });
        return;
      }

      if (event.phase === "analysis") {
        dispatch({
          type: "ADD",
          message: createThinking(
            event.data.replan_count && Number(event.data.replan_count) > 0
              ? "Reworking the stack from safety feedback..."
              : "Comparing products and building your stack...",
          ),
        });
        return;
      }

      if (event.phase === "checkout") {
        dispatch({
          type: "ADD_MANY",
          messages: [
            createAssistantText("Preparing checkout links..."),
            createThinking("Building store carts and approval links..."),
          ],
        });
      }
      return;
    case "phase_completed":
      if (event.phase === "memory") {
        dispatch({
          type: "REPLACE_LAST_THINKING",
          message: createAssistantText("Identified supplement categories."),
        });
        return;
      }

      if (event.phase === "discovery") {
        dispatch({
          type: "REPLACE_LAST_THINKING",
          message: createAssistantText("Store search complete."),
        });
        return;
      }

      if (event.phase === "analysis") {
        dispatch({
          type: "REPLACE_LAST_THINKING",
          message: createAssistantText(analysisPhaseSummary(event)),
        });
        return;
      }

      if (event.phase === "checkout") {
        dispatch({
          type: "REPLACE_LAST_THINKING",
          message: createAssistantText("Checkout links are staged for review."),
        });
      }
      return;
    case "approval_requested":
      dispatch({
        type: "REPLACE_LAST_THINKING",
        message: createAssistantText("Your cart is ready for review."),
      });
      return;
    case "approval_resolved":
      dispatch({
        type: "ADD",
        message: createAssistantText("Approved! Your checkout links are ready."),
      });
      return;
    case "run_completed":
      dispatch({
        type: "ADD",
        message: createAssistantText(runCompletedSummary(event)),
      });
      return;
    case "error":
      dispatch({
        type: "REPLACE_LAST_THINKING",
        message: createAssistantText(event.message || "The run hit an error before it could finish."),
      });
      return;
    case "node_entered":
    case "node_completed":
      return;
    default:
      return;
  }
}

function chatReducer(state: ChatMessage[], action: ChatAction): ChatMessage[] {
  switch (action.type) {
    case "RESET":
      return buildIntroMessages(action.userId);
    case "ADD":
      return upsertMessages(state, [action.message]);
    case "ADD_MANY":
      return upsertMessages(state, action.messages);
    case "UPSERT":
      return upsertMessages(state, [action.message]);
    case "REPLACE_LAST_THINKING": {
      const nextState = [...state];
      const thinkingIndex = [...nextState]
        .reverse()
        .findIndex((message) => message.type === "thinking");

      if (thinkingIndex === -1) {
        return upsertMessages(state, [action.message]);
      }

      const resolvedIndex = nextState.length - 1 - thinkingIndex;
      nextState[resolvedIndex] = action.message;
      return nextState;
    }
    default:
      return state;
  }
}

function buildIntroMessages(userId: string): ChatMessage[] {
  return [
    createAssistantText(
      "Tell me what you want to improve, and I'll turn it into a budget-aware supplement stack with checkout-ready store links.",
      `intro:${userId}:greeting`,
    ),
    createIntakeForm(userId, `intro:${userId}:intake`),
  ];
}

function upsertMessages(state: ChatMessage[], incomingMessages: ChatMessage[]) {
  const nextState = [...state];

  for (const message of incomingMessages) {
    const existingIndex = nextState.findIndex((existingMessage) => existingMessage.id === message.id);
    if (existingIndex === -1) {
      nextState.push(message);
    } else {
      nextState[existingIndex] = message;
    }
  }

  return nextState;
}

function createSnapshotKeys(): SnapshotKeys {
  return {
    discovery: "",
    comparison: "",
    stack: "",
    safety: "",
    checkout: "",
    autopilot: "",
  };
}

function resetTracking(
  processedEventIdsRef: MutableRefObject<Set<string>>,
  narratedCardsRef: MutableRefObject<Set<string>>,
  snapshotKeysRef: MutableRefObject<SnapshotKeys>,
) {
  processedEventIdsRef.current.clear();
  narratedCardsRef.current.clear();
  snapshotKeysRef.current = createSnapshotKeys();
}

function summarizeHealthProfile(profile: HealthProfile) {
  const details = [
    `${profile.age}-year-old ${formatLabel(profile.sex).toLowerCase()}`,
    `${profile.weight_lbs} lb`,
    `${formatMoney(profile.monthly_budget)} monthly budget`,
  ];

  if (profile.allergies.length) {
    details.push(`watching for ${joinList(profile.allergies)}`);
  }

  return `I want help with ${joinList(profile.health_goals)}. ${details.join(" | ")}.`;
}

function analysisPhaseSummary(event: SupplementRunEvent) {
  const decision = String(event.data.decision ?? "");

  if (decision === "passed") {
    return "Safety review passed.";
  }

  if (decision === "manual_review_needed") {
    return "The stack is ready, but it needs manual review before checkout.";
  }

  if (decision === "failed") {
    return "Safety review flagged the stack for another pass.";
  }

  return "Safety review complete.";
}

function runCompletedSummary(event: SupplementRunEvent) {
  const decision = String(event.data.decision ?? "");
  const status = String(event.data.status ?? "");

  if (decision === "manual_review_needed") {
    return "Your stack is ready, but a clinician or pharmacist should review it before checkout.";
  }

  if (status === "completed") {
    return "Your supplement plan is complete.";
  }

  return "The run ended before checkout could be completed.";
}
