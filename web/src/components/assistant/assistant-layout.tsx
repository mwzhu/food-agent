"use client";

import { useState } from "react";

import { HistorySidebar } from "@/components/assistant/history-sidebar";
import { StackRail } from "@/components/assistant/stack-rail";
import { ChatInput } from "@/components/assistant/chat-input";
import { ChatThread } from "@/components/assistant/chat-thread";
import { useChatMessages } from "@/components/assistant/use-chat-messages";
import { useCreateSupplementRun, useSupplementRun, useSupplementRunStream } from "@/hooks/use-supplement-run";
import { useUser } from "@/hooks/use-user";
import type { HealthProfile, SupplementRunLifecycleStatus, SupplementStateSnapshot } from "@/lib/supplement-types";

type AssistantLayoutProps = {
  userId: string;
};

export function AssistantLayout({ userId }: AssistantLayoutProps) {
  const [runId, setRunId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const userQuery = useUser(userId);
  const createSupplementRunMutation = useCreateSupplementRun();
  const runQuery = useSupplementRun(runId ?? "", true);
  const stream = useSupplementRunStream(runId ?? "");
  const snapshot = runQuery.data?.state_snapshot ?? null;
  const runStatus = runQuery.data?.status ?? null;
  const intakeInitialValues: Partial<HealthProfile> | undefined = userQuery.data
    ? {
        age: userQuery.data.age,
        weight_lbs: userQuery.data.weight_lbs,
        sex: userQuery.data.sex,
        allergies: userQuery.data.allergies,
      }
    : undefined;

  const chat = useChatMessages({
    userId,
    runId,
    events: stream.events,
    snapshot,
  });

  const startSupplementRun = async (healthProfile: HealthProfile) => {
    setErrorMessage(null);

    try {
      const run = await createSupplementRunMutation.mutateAsync({
        user_id: userId,
        health_profile: healthProfile,
      });

      chat.startRun(healthProfile, run.run_id);
      setRunId(run.run_id);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start the supplement run.");
    }
  };

  const resetWorkspace = () => {
    setRunId(null);
    setErrorMessage(null);
    chat.resetConversation();
  };

  const handleSend = async (text: string) => {
    if (!runId) {
      chat.guideToIntake(text);
      return;
    }

    if (runStatus === "completed" || runStatus === "failed") {
      resetWorkspace();
      chat.guideToIntake(text);
      return;
    }

    chat.explainLockedConversation(text);
  };

  return (
    <section className="overflow-hidden rounded-[2rem] border border-border bg-card/60 shadow-soft backdrop-blur-xl">
      <div className="flex h-[calc(100vh-120px)] min-h-[720px]">
        <HistorySidebar
          activeLabel={activeConversationLabel(snapshot)}
          onNewConversation={resetWorkspace}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <ChatThread
            intakeInitialValues={intakeInitialValues}
            messages={chat.messages}
            onSubmitIntake={startSupplementRun}
          />
          {errorMessage ? (
            <div className="border-t border-border/70 bg-accent/45 px-5 py-3 text-sm text-accent-foreground">
              {errorMessage}
            </div>
          ) : null}
          <ChatInput
            disabled={createSupplementRunMutation.isPending}
            onSend={handleSend}
            status={inputStatus(runId, runStatus)}
          />
        </div>

        <StackRail snapshot={snapshot} />
      </div>
    </section>
  );
}

function inputStatus(
  runId: string | null,
  runStatus: SupplementRunLifecycleStatus | null,
) {
  if (!runId) {
    return "idle" as const;
  }

  if (runStatus === "completed" || runStatus === "failed") {
    return "reset" as const;
  }

  return "working" as const;
}

function activeConversationLabel(snapshot: SupplementStateSnapshot | null) {
  if (!snapshot) {
    return "New stack draft";
  }

  const goals = snapshot.health_profile.health_goals;
  if (!goals.length) {
    return "Current stack";
  }

  return goals.slice(0, 2).join(" & ");
}
