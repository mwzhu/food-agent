import type {
  CategoryDiscoveryResult,
  HealthProfile,
  ProductComparison,
  StoreCart,
  SupplementCriticVerdict,
  SupplementRunLifecycleStatus,
  SupplementStack,
} from "@/lib/supplement-types";

type ChatMessageBase = {
  id: string;
  timestamp: string;
};

export type ChatMessage =
  | ({ type: "assistant_text"; text: string } & ChatMessageBase)
  | ({ type: "user_text"; text: string } & ChatMessageBase)
  | ({ type: "intake_form"; userId: string } & ChatMessageBase)
  | ({ type: "profile_confirmed"; profile: HealthProfile } & ChatMessageBase)
  | ({ type: "search_progress"; results: CategoryDiscoveryResult[]; isComplete: boolean } & ChatMessageBase)
  | ({ type: "comparison_card"; comparisons: ProductComparison[] } & ChatMessageBase)
  | ({ type: "stack_card"; stack: SupplementStack } & ChatMessageBase)
  | ({ type: "safety_card"; verdict: SupplementCriticVerdict } & ChatMessageBase)
  | ({
      type: "checkout_card";
      runId: string;
      runStatus: SupplementRunLifecycleStatus;
      storeCarts: StoreCart[];
      approvedStoreDomains: string[];
    } & ChatMessageBase)
  | ({ type: "autopilot_card"; stack: SupplementStack } & ChatMessageBase)
  | ({ type: "thinking"; text: string } & ChatMessageBase);

function createTimestamp() {
  return new Date().toISOString();
}

function createId(prefix: string) {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}:${crypto.randomUUID()}`;
  }

  return `${prefix}:${Math.random().toString(36).slice(2, 10)}`;
}

export function createSemanticId(kind: string, runId: string) {
  return `${kind}:${runId}`;
}

export function createAssistantText(text: string, id = createId("assistant")): ChatMessage {
  return {
    id,
    timestamp: createTimestamp(),
    type: "assistant_text",
    text,
  };
}

export function createUserText(text: string, id = createId("user")): ChatMessage {
  return {
    id,
    timestamp: createTimestamp(),
    type: "user_text",
    text,
  };
}

export function createIntakeForm(userId: string, id = createId("intake")): ChatMessage {
  return {
    id,
    timestamp: createTimestamp(),
    type: "intake_form",
    userId,
  };
}

export function createProfileConfirmed(profile: HealthProfile, id = createId("profile")): ChatMessage {
  return {
    id,
    timestamp: createTimestamp(),
    type: "profile_confirmed",
    profile,
  };
}

export function createSearchProgress(
  runId: string,
  results: CategoryDiscoveryResult[],
  isComplete: boolean,
): ChatMessage {
  return {
    id: createSemanticId("discovery", runId),
    timestamp: createTimestamp(),
    type: "search_progress",
    results,
    isComplete,
  };
}

export function createComparisonCard(runId: string, comparisons: ProductComparison[]): ChatMessage {
  return {
    id: createSemanticId("comparison", runId),
    timestamp: createTimestamp(),
    type: "comparison_card",
    comparisons,
  };
}

export function createStackCard(runId: string, stack: SupplementStack): ChatMessage {
  return {
    id: createSemanticId("stack", runId),
    timestamp: createTimestamp(),
    type: "stack_card",
    stack,
  };
}

export function createSafetyCard(runId: string, verdict: SupplementCriticVerdict): ChatMessage {
  return {
    id: createSemanticId("safety", runId),
    timestamp: createTimestamp(),
    type: "safety_card",
    verdict,
  };
}

export function createCheckoutCard(
  runId: string,
  runStatus: SupplementRunLifecycleStatus,
  storeCarts: StoreCart[],
  approvedStoreDomains: string[],
): ChatMessage {
  return {
    id: createSemanticId("checkout", runId),
    timestamp: createTimestamp(),
    type: "checkout_card",
    runId,
    runStatus,
    storeCarts,
    approvedStoreDomains,
  };
}

export function createAutopilotCard(runId: string, stack: SupplementStack): ChatMessage {
  return {
    id: createSemanticId("autopilot", runId),
    timestamp: createTimestamp(),
    type: "autopilot_card",
    stack,
  };
}

export function createThinking(text: string, id = createId("thinking")): ChatMessage {
  return {
    id,
    timestamp: createTimestamp(),
    type: "thinking",
    text,
  };
}
