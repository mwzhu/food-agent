"use client";

import { ProductComparison } from "@/components/supplements/product-comparison";
import { CheckoutLinks } from "@/components/supplements/checkout-links";
import { StackRecommendation } from "@/components/supplements/stack-recommendation";
import type { HealthProfile } from "@/lib/supplement-types";
import { cn } from "@/lib/utils";

import { AutopilotCard } from "./autopilot-card";
import type { ChatMessage } from "./message-types";
import { IntakeFormCompact } from "./intake-form-compact";
import { ProfileConfirmedCard } from "./profile-confirmed-card";
import { SafetyCard } from "./safety-card";
import { SearchProgressCard } from "./search-progress-card";
import { ThinkingIndicator } from "./thinking-indicator";

type ChatMessageBubbleProps = {
  message: ChatMessage;
  intakeInitialValues?: Partial<HealthProfile>;
  onSubmitIntake: (payload: HealthProfile) => Promise<void>;
};

export function ChatMessageBubble({
  message,
  intakeInitialValues,
  onSubmitIntake,
}: ChatMessageBubbleProps) {
  switch (message.type) {
    case "user_text":
      return (
        <UserBubble>
          <div className="rounded-[1.55rem] border border-border bg-secondary px-4 py-3 text-sm leading-6 text-secondary-foreground shadow-soft">
            {message.text}
          </div>
        </UserBubble>
      );
    case "assistant_text":
      return (
        <AssistantBubble>
          <div className="rounded-[1.55rem] border border-border bg-card/95 px-4 py-3 text-sm leading-6 text-foreground shadow-soft">
            {message.text}
          </div>
        </AssistantBubble>
      );
    case "thinking":
      return (
        <AssistantBubble>
          <ThinkingIndicator text={message.text} />
        </AssistantBubble>
      );
    case "intake_form":
      return (
        <AssistantBubble>
          <IntakeFormCompact
            initialValues={intakeInitialValues}
            onSubmit={onSubmitIntake}
            userId={message.userId}
          />
        </AssistantBubble>
      );
    case "profile_confirmed":
      return (
        <AssistantBubble>
          <ProfileConfirmedCard profile={message.profile} />
        </AssistantBubble>
      );
    case "search_progress":
      return (
        <AssistantBubble>
          <SearchProgressCard isComplete={message.isComplete} results={message.results} />
        </AssistantBubble>
      );
    case "comparison_card":
      return (
        <AssistantBubble className="max-w-[min(95%,68rem)]">
          <ProductComparison comparisons={message.comparisons} />
        </AssistantBubble>
      );
    case "stack_card":
      return (
        <AssistantBubble className="max-w-[min(95%,64rem)]">
          <StackRecommendation stack={message.stack} />
        </AssistantBubble>
      );
    case "safety_card":
      return (
        <AssistantBubble>
          <SafetyCard verdict={message.verdict} />
        </AssistantBubble>
      );
    case "checkout_card":
      return (
        <AssistantBubble className="max-w-[min(95%,64rem)]">
          <CheckoutLinks
            approvedStoreDomains={message.approvedStoreDomains}
            runId={message.runId}
            runStatus={message.runStatus}
            storeCarts={message.storeCarts}
          />
        </AssistantBubble>
      );
    case "autopilot_card":
      return (
        <AssistantBubble>
          <AutopilotCard stack={message.stack} />
        </AssistantBubble>
      );
    default:
      return null;
  }
}

function AssistantBubble({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("mr-auto w-full max-w-[min(92%,60rem)]", className)}>{children}</div>;
}

function UserBubble({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={cn("ml-auto w-full max-w-[min(72%,38rem)]", className)}>{children}</div>;
}
