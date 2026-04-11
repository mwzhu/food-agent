"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUp,
  ArrowUpRight,
  Brain,
  Check,
  ChevronLeft,
  CircleUserRound,
  Clock3,
  LayoutGrid,
  Loader2,
  MessageCircle,
  Package,
  Plus,
  Settings,
  Sparkles,
  X,
} from "lucide-react";

import { useCurrentUser } from "@/components/layout/providers";
import {
  useApproveSupplementRun,
  useCreateSupplementRun,
  useSupplementRun,
  useSupplementRunStream,
} from "@/hooks/use-supplement-run";
import { useUser } from "@/hooks/use-user";
import type {
  HealthProfile,
  ProductComparison,
  ShopifyProduct,
  StackItem,
  StoreCart,
  SupplementRunEvent,
  SupplementRunLifecycleStatus,
  SupplementStateSnapshot,
} from "@/lib/supplement-types";
import type { UserProfileRead } from "@/lib/types";
import { cn, formatMoney, joinList } from "@/lib/utils";

const APP_ITEMS = [
  { id: "chat", label: "Chat", icon: MessageCircle },
  { id: "inventory", label: "Inventory", icon: Package },
  { id: "agents", label: "Agents", icon: Brain },
] as const;

const ARCHIVED_CONVERSATIONS = [
  { title: "Sleep & recovery", subtitle: "Apr 8" },
  { title: "Travel immunity", subtitle: "Mar 22" },
  { title: "Focus & energy", subtitle: "Mar 4" },
];

const DEMO_USER_ID = "demo-supplement-user";

const DEFAULT_DEMO_PROFILE: HealthProfile = {
  age: 32,
  weight_lbs: 165,
  sex: "female",
  health_goals: [],
  current_supplements: [],
  medications: [],
  conditions: [],
  allergies: [],
  monthly_budget: 100,
};

const NEW_CONVERSATION_USE_CASES = [
  "Build me a sleep stack under $100",
  "Find stress-support supplements that won't make me groggy",
  "Put together a focus and energy stack for work",
  "Create a recovery and immunity cart with clean ingredients",
] as const;

type DemoMessage =
  | {
      id: string;
      type: "assistant";
      text: string;
      streaming: boolean;
    }
  | {
      id: string;
      type: "user";
      text: string;
    }
  | {
      id: string;
      type: "progress";
      steps: DemoProgressStep[];
    }
  | {
      id: string;
      type: "widget";
      widget: CartWidgetModel;
    };

type DemoStepStatus = "pending" | "running" | "completed" | "error";

type DemoProgressStep = {
  key: string;
  label: string;
  status: DemoStepStatus;
  detail?: string;
  durationLabel?: string;
};

type DemoIntent = {
  prompt: string;
  budget: number;
  goals: string[];
  conversationLabel: string;
};

type ActiveConversation = {
  sessionKey: string;
  intent: DemoIntent;
  healthProfile: HealthProfile;
};

type ProfileContext = {
  userId: string;
  usingFallback: boolean;
  statsLabel: string;
  allergyLabel: string;
  memoryLabel: string;
  baseHealthProfile: Omit<HealthProfile, "health_goals" | "monthly_budget">;
  defaultBudget: number;
};

type CartWidgetLineItem = {
  key: string;
  title: string;
  subtitle: string;
  imageUrl: string | null;
  quantity: number;
  amountLabel: string;
  tag?: string;
};

type CartWidgetModel = {
  storeDomain: string;
  storeName: string;
  checkoutUrl: string | null;
  statusLine: string;
  subtotal: number | null;
  budget: number;
  approved: boolean;
  buyState: "idle" | "approving" | "opened" | "error";
  items: CartWidgetLineItem[];
};

export function V1Workspace() {
  const router = useRouter();
  const { isHydrated, userId } = useCurrentUser();

  if (!isHydrated) {
    return (
      <div className="v1-theme grid h-screen w-screen place-items-center bg-[#E3E3E5]">
        <p className="text-sm text-[rgba(0,0,0,0.54)]">Loading supplement workspace...</p>
      </div>
    );
  }

  return (
    <div className="v1-theme h-screen w-screen overflow-hidden bg-[#E3E3E5] text-black">
      <div className="flex h-full w-full overflow-hidden">
        <PrimarySidebar
          onOpenInventory={() => router.push("/inventory")}
          onOpenProfile={() => router.push("/profile")}
          onOpenWorkspace={() => router.push("/")}
        />

        <div className="flex min-w-0 flex-1 gap-2 px-0 pb-2 pr-2 pt-2">
          <main className="flex min-w-0 flex-1 overflow-hidden rounded-lg bg-[#FCFCFC] shadow-[0_0_1px_rgba(0,0,0,0.25)]">
            <AgentListSidebar />
            <SupplementAgentWorkspace storedUserId={userId} />
          </main>
        </div>
      </div>
    </div>
  );
}

function PrimarySidebar({
  onOpenInventory,
  onOpenProfile,
  onOpenWorkspace,
}: {
  onOpenInventory: () => void;
  onOpenProfile: () => void;
  onOpenWorkspace: () => void;
}) {
  return (
    <aside className="flex w-16 shrink-0 flex-col items-center justify-between bg-[#E3E3E5] px-2 py-3">
      <div className="flex flex-col items-center gap-3">
        <button
          className="grid h-10 w-10 place-items-center rounded-lg text-[#323232] transition-colors hover:bg-black/5"
          onClick={onOpenWorkspace}
          title="Home"
          type="button"
        >
          <LayoutGrid className="size-[18px]" strokeWidth={1.8} />
        </button>

        {APP_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === "agents";
          const onClick = item.id === "inventory" ? onOpenInventory : undefined;

          return (
            <button
              key={item.id}
              className={cn(
                "grid h-10 w-10 place-items-center rounded-lg text-[#323232] transition-colors",
                isActive ? "bg-white text-black shadow-sm" : "hover:bg-black/5",
              )}
              onClick={onClick}
              title={item.label}
              type="button"
            >
              <Icon className="size-[18px]" strokeWidth={1.8} />
            </button>
          );
        })}
      </div>

      <div className="flex flex-col items-center gap-3">
        <button
          className="grid h-10 w-10 place-items-center rounded-lg text-[#323232] transition-colors hover:bg-black/5"
          title="Settings"
          type="button"
        >
          <Settings className="size-[18px]" strokeWidth={1.8} />
        </button>
        <button
          className="grid h-10 w-10 place-items-center rounded-lg text-[#323232] transition-colors hover:bg-black/5"
          onClick={onOpenProfile}
          title="Profile"
          type="button"
        >
          <CircleUserRound className="size-[18px]" strokeWidth={1.8} />
        </button>
      </div>
    </aside>
  );
}

function AgentListSidebar() {
  return (
    <aside className="flex w-[212px] shrink-0 flex-col overflow-hidden border-r border-black/5 bg-[#F9F9F9]">
      <div className="flex h-12 items-center justify-between pl-4 pr-2">
        <h2 className="text-base font-semibold text-black">Agents</h2>
        <button
          className="rounded border border-black/10 bg-white p-1 text-[rgba(0,0,0,0.68)] transition-colors hover:border-black/20 hover:text-black"
          title="New agent"
          type="button"
        >
          <Plus className="size-4" strokeWidth={1.8} />
        </button>
      </div>

      <div className="v1-scrollbar flex-1 overflow-y-auto px-2 pb-3">
        <div className="space-y-0.5">
          <button
            className="flex w-full items-center gap-2 rounded-md bg-[#EAEAEA] px-3 py-1.5 text-left text-sm font-medium text-black"
            type="button"
          >
            <div className="grid h-5 w-5 place-items-center rounded-full bg-black text-white">
              <Sparkles className="size-3" strokeWidth={1.9} />
            </div>
            <div className="min-w-0 flex-1">
              <span className="block truncate">Supplement Agent</span>
              <span className="block truncate text-[10px] font-normal leading-tight text-[rgba(0,0,0,0.54)]">
                Search, plan, cart, checkout
              </span>
            </div>
            <div className="h-1.5 w-1.5 shrink-0 rounded-full bg-green-400" />
          </button>

          <button
            className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm text-[#323232] opacity-55 transition-colors hover:bg-black/5"
            type="button"
          >
            <div className="h-2 w-2 rounded-full bg-gray-300" />
            <div className="min-w-0 flex-1">
              <span className="block truncate">Meal Agent</span>
              <span className="block truncate text-[10px] leading-tight text-[rgba(0,0,0,0.54)]">
                Presentational only
              </span>
            </div>
          </button>
        </div>
      </div>
    </aside>
  );
}

function SupplementAgentWorkspace({ storedUserId }: { storedUserId: string | null }) {
  const [runId, setRunId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [messages, setMessages] = useState<DemoMessage[]>([]);
  const [activeConversation, setActiveConversation] = useState<ActiveConversation | null>(null);
  const [buyState, setBuyState] = useState<CartWidgetModel["buyState"]>("idle");

  const userQuery = useUser(storedUserId);
  const createSupplementRunMutation = useCreateSupplementRun();
  const approveMutation = useApproveSupplementRun();
  const runQuery = useSupplementRun(runId ?? "", true);
  const stream = useSupplementRunStream(runId ?? "");
  const snapshot = runQuery.data?.state_snapshot ?? null;
  const runStatus = runQuery.data?.status ?? null;

  const profileContext = useMemo(
    () => buildProfileContext(storedUserId, userQuery.data),
    [storedUserId, userQuery.data],
  );
  const currentConversationLabel = activeConversation?.intent.conversationLabel ?? "New conversation";
  const isEmptyConversation = !activeConversation && messages.length === 0;
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const streamedReasoningRef = useRef<Set<string>>(new Set());
  const streamedFailureRef = useRef<Set<string>>(new Set());
  const buyAcknowledgedRef = useRef<Set<string>>(new Set());

  const progressSteps = useMemo(
    () =>
      activeConversation
        ? buildProgressSteps({
            events: stream.events,
            intent: activeConversation.intent,
            profileContext,
            runStatus,
            snapshot,
          })
        : [],
    [activeConversation, profileContext, runStatus, snapshot, stream.events],
  );
  const featuredCart = useMemo(
    () =>
      activeConversation
        ? buildCartWidget({
            buyState,
            intent: activeConversation.intent,
            runStatus,
            snapshot,
          })
        : null,
    [activeConversation, buyState, runStatus, snapshot],
  );

  useEffect(() => {
    return () => {
      clearAllTimers(timersRef);
    };
  }, []);

  useEffect(() => {
    if (!activeConversation) {
      return;
    }

    setMessages((previousMessages) =>
      upsertMessage(previousMessages, {
        id: `progress:${activeConversation.sessionKey}`,
        type: "progress",
        steps: progressSteps,
      }),
    );
  }, [activeConversation, progressSteps]);

  useEffect(() => {
    if (!activeConversation || !featuredCart) {
      return;
    }

    setMessages((previousMessages) =>
      upsertMessage(previousMessages, {
        id: `widget:${activeConversation.sessionKey}`,
        type: "widget",
        widget: featuredCart,
      }),
    );
  }, [activeConversation, featuredCart]);

  useEffect(() => {
    if (!activeConversation || !featuredCart || !snapshot?.recommended_stack) {
      return;
    }

    if (streamedReasoningRef.current.has(activeConversation.sessionKey)) {
      return;
    }

    streamedReasoningRef.current.add(activeConversation.sessionKey);
    const messageId = `reasoning:${activeConversation.sessionKey}`;
    const reasoningText = buildReasoningText({
      intent: activeConversation.intent,
      profileContext,
      snapshot,
      widget: featuredCart,
    });

    setMessages((previousMessages) =>
      upsertMessage(previousMessages, {
        id: messageId,
        type: "assistant",
        text: "",
        streaming: true,
      }),
    );
    streamAssistantText(messageId, reasoningText, setMessages, timersRef);
  }, [activeConversation, featuredCart, profileContext, snapshot]);

  useEffect(() => {
    if (!activeConversation || !runStatus || runStatus !== "failed") {
      return;
    }

    if (streamedFailureRef.current.has(activeConversation.sessionKey)) {
      return;
    }

    streamedFailureRef.current.add(activeConversation.sessionKey);
    const messageId = `failure:${activeConversation.sessionKey}`;
    const failureText =
      snapshot?.latest_error ??
      "The run stopped before I could finish the cart. Start a new conversation and I'll try again.";

    setMessages((previousMessages) =>
      upsertMessage(previousMessages, {
        id: messageId,
        type: "assistant",
        text: "",
        streaming: true,
      }),
    );
    streamAssistantText(messageId, failureText, setMessages, timersRef);
  }, [activeConversation, runStatus, snapshot]);

  const resetWorkspace = () => {
    clearAllTimers(timersRef);
    streamedReasoningRef.current.clear();
    streamedFailureRef.current.clear();
    buyAcknowledgedRef.current.clear();
    setRunId(null);
    setErrorMessage(null);
    setBuyState("idle");
    setActiveConversation(null);
    setMessages([]);
  };

  const startConversation = async (prompt: string) => {
    clearAllTimers(timersRef);
    streamedReasoningRef.current.clear();
    streamedFailureRef.current.clear();
    buyAcknowledgedRef.current.clear();
    setRunId(null);
    setErrorMessage(null);
    setBuyState("idle");

    const intent = parsePromptIntent(prompt, profileContext);
    const healthProfile = buildHealthProfile(intent, profileContext);
    const sessionKey = createSessionKey();

    setActiveConversation({
      sessionKey,
      intent,
      healthProfile,
    });
    setMessages([
      { id: `user:${sessionKey}`, type: "user", text: prompt },
      {
        id: `intro:${sessionKey}`,
        type: "assistant",
        text: "",
        streaming: true,
      },
      {
        id: `progress:${sessionKey}`,
        type: "progress",
        steps: buildInitialProgressSteps(intent, profileContext),
      },
    ]);

    streamAssistantText(
      `intro:${sessionKey}`,
      buildOpeningNarrative(intent, profileContext),
      setMessages,
      timersRef,
    );

    try {
      const run = await createSupplementRunMutation.mutateAsync({
        user_id: profileContext.userId,
        health_profile: healthProfile,
      });
      setRunId(run.run_id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not start the supplement run.";
      setErrorMessage(message);
      setMessages((previousMessages) =>
        previousMessages.concat({
          id: `startup-error:${sessionKey}`,
          type: "assistant",
          text: message,
          streaming: false,
        }),
      );
    }
  };

  const handleSend = async (text: string) => {
    const runIsActive =
      runStatus === "running" || runStatus === "awaiting_approval" || createSupplementRunMutation.isPending;

    if (runIsActive) {
      return;
    }

    await startConversation(text);
  };

  const handleBuy = async () => {
    if (!featuredCart?.checkoutUrl) {
      return;
    }

    if (buyState === "opened") {
      window.open(featuredCart.checkoutUrl, "_blank", "noopener,noreferrer");
      return;
    }

    const previewWindow = window.open("", "_blank", "noopener,noreferrer");
    setBuyState("approving");
    setErrorMessage(null);

    try {
      let checkoutUrl = featuredCart.checkoutUrl;

      if (runId && runStatus === "awaiting_approval") {
        const approvedRun = await approveMutation.mutateAsync({
          runId,
          payload: {
            approved_store_domains: [featuredCart.storeDomain],
          },
        });
        const approvedWidget = buildCartWidget({
          buyState: "opened",
          intent: activeConversation?.intent ?? parsePromptIntent("", profileContext),
          runStatus: approvedRun.status,
          snapshot: approvedRun.state_snapshot,
        });
        checkoutUrl = approvedWidget?.checkoutUrl ?? checkoutUrl;
      }

      if (!checkoutUrl) {
        throw new Error("Checkout URL is not available for this cart yet.");
      }

      if (previewWindow) {
        previewWindow.location.href = checkoutUrl;
      } else {
        window.open(checkoutUrl, "_blank", "noopener,noreferrer");
      }

      setBuyState("opened");

      if (activeConversation && !buyAcknowledgedRef.current.has(activeConversation.sessionKey)) {
        buyAcknowledgedRef.current.add(activeConversation.sessionKey);
        const confirmationId = `buy:${activeConversation.sessionKey}`;
        const confirmationText =
          "I opened the checkout in a new tab. The cart is already filled, and you can adjust quantities or complete payment there.";

        setMessages((previousMessages) =>
          upsertMessage(previousMessages, {
            id: confirmationId,
            type: "assistant",
            text: "",
            streaming: true,
          }),
        );
        streamAssistantText(confirmationId, confirmationText, setMessages, timersRef);
      }
    } catch (error) {
      previewWindow?.close();
      setBuyState("error");
      setErrorMessage(error instanceof Error ? error.message : "Could not open checkout.");
    }
  };

  return (
    <div className="flex min-w-0 flex-1 overflow-hidden rounded-r-lg bg-white">
      <ConversationSidebar
        activeLabel={currentConversationLabel}
        collapsed={!showHistory}
        onNewConversation={resetWorkspace}
        onToggle={() => setShowHistory((current) => !current)}
      />

      <div className="flex min-w-0 flex-1 flex-col bg-white">
        {isEmptyConversation ? (
          <NewConversationState
            disabled={
              createSupplementRunMutation.isPending ||
              runStatus === "running" ||
              runStatus === "awaiting_approval" ||
              approveMutation.isPending
            }
            onSend={handleSend}
            suggestions={NEW_CONVERSATION_USE_CASES}
          />
        ) : (
          <ChatThread buyState={buyState} messages={messages} onBuy={handleBuy} />
        )}

        {errorMessage ? (
          <div className="border-t border-[#EAEAEA] bg-[#FCF1F1] px-6 py-3 text-sm text-[#B32F2F]">
            {errorMessage}
          </div>
        ) : null}

        {isEmptyConversation ? null : (
          <ChatInput
            disabled={
              createSupplementRunMutation.isPending ||
              runStatus === "running" ||
              runStatus === "awaiting_approval" ||
              approveMutation.isPending
            }
            onSend={handleSend}
            placeholder={inputPlaceholder(runStatus)}
          />
        )}
      </div>
    </div>
  );
}

function ConversationSidebar({
  activeLabel,
  collapsed,
  onNewConversation,
  onToggle,
}: {
  activeLabel: string;
  collapsed: boolean;
  onNewConversation: () => void;
  onToggle: () => void;
}) {
  return (
    <aside
      className={cn(
        "shrink-0 border-r border-black/5 transition-[width,background-color] duration-200",
        collapsed ? "w-12 bg-white" : "w-[212px] bg-[#F9F9F9]",
      )}
    >
      {collapsed ? (
        <div className="flex h-full flex-col items-center gap-2 pt-3">
          <button
            className="rounded-lg p-2 text-[rgba(0,0,0,0.54)] transition-colors hover:bg-black/5 hover:text-black"
            onClick={onToggle}
            title="Show history"
            type="button"
          >
            <Clock3 className="size-4" strokeWidth={1.9} />
          </button>
        </div>
      ) : (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between px-3 pb-1 pt-3">
            <span className="text-xs font-medium text-[rgba(0,0,0,0.54)]">History</span>
            <button
              className="rounded p-1 text-[rgba(0,0,0,0.54)] transition-colors hover:bg-black/5 hover:text-black"
              onClick={onToggle}
              title="Hide history"
              type="button"
            >
              <ChevronLeft className="size-4" strokeWidth={1.9} />
            </button>
          </div>

          <div className="px-2 pt-2">
            <button
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-sm text-[rgba(0,0,0,0.68)] transition-colors hover:bg-black/5"
              onClick={onNewConversation}
              type="button"
            >
              <Plus className="size-[14px]" strokeWidth={1.9} />
              <span>New conversation</span>
            </button>
          </div>

          <div className="v1-scrollbar flex-1 overflow-y-auto px-2 pb-3">
            <div className="space-y-0.5">
              <ConversationItem active subtitle="Current workspace" title={activeLabel} />
              {ARCHIVED_CONVERSATIONS.map((conversation) => (
                <ConversationItem
                  key={conversation.title}
                  subtitle={conversation.subtitle}
                  title={conversation.title}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function ConversationItem({
  title,
  subtitle,
  active = false,
}: {
  title: string;
  subtitle: string;
  active?: boolean;
}) {
  return (
    <button
      className={cn(
        "flex h-[32px] w-full items-center rounded-md px-2 text-left text-sm transition-colors",
        active ? "bg-black/8 font-medium text-black" : "text-[#323232] hover:bg-black/5",
      )}
      type="button"
    >
      <span className="truncate text-[13px]">{title}</span>
      <span className="sr-only">{subtitle}</span>
    </button>
  );
}

function NewConversationState({
  disabled,
  onSend,
  suggestions,
}: {
  disabled?: boolean;
  onSend: (message: string) => Promise<void> | void;
  suggestions: readonly string[];
}) {
  const [draft, setDraft] = useState("");

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-10">
      <div className="w-full max-w-[760px]">
        <h1 className="mb-8 text-center text-2xl font-semibold leading-9 tracking-tight text-black">
          What&apos;s on the agenda?
        </h1>

        <ChatInput
          disabled={disabled}
          onSend={onSend}
          onValueChange={setDraft}
          placeholder="Ask anything"
          value={draft}
          variant="centered"
        />

        <ul className="mt-4 divide-y divide-black/8 px-4">
          {suggestions.map((suggestion) => (
            <li key={suggestion}>
              <button
                className="flex w-full items-center py-3 text-left text-sm text-black/38 transition-colors hover:text-black/68"
                onClick={() => setDraft(suggestion)}
                type="button"
              >
                {suggestion}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ChatThread({
  buyState,
  messages,
  onBuy,
}: {
  buyState: CartWidgetModel["buyState"];
  messages: DemoMessage[];
  onBuy: () => Promise<void>;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const updateAutoScroll = () => {
      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      shouldAutoScrollRef.current = distanceFromBottom < 160;
    };

    updateAutoScroll();
    container.addEventListener("scroll", updateAutoScroll);

    return () => container.removeEventListener("scroll", updateAutoScroll);
  }, []);

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return;
    }

    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div ref={containerRef} className="v1-scrollbar flex-1 overflow-y-auto px-6 pb-28 pt-6">
      <div className="mx-auto max-w-5xl space-y-6">
        {messages.map((message) => (
          <MessageRow key={message.id} buyState={buyState} message={message} onBuy={onBuy} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageRow({
  buyState,
  message,
  onBuy,
}: {
  buyState: CartWidgetModel["buyState"];
  message: DemoMessage;
  onBuy: () => Promise<void>;
}) {
  if (message.type === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[min(72%,36rem)] rounded-[1.5rem] bg-[#F3F3F3] px-4 py-2.5 text-[15px] leading-6 text-black">
          {message.text}
        </div>
      </div>
    );
  }

  if (message.type === "progress") {
    return <ActionProgress steps={message.steps} />;
  }

  if (message.type === "widget") {
    return <CartWidget buyState={buyState} onBuy={onBuy} widget={message.widget} />;
  }

  return <AssistantTextMessage streaming={message.streaming} text={message.text} />;
}

function AssistantTextMessage({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}) {
  return (
    <div className="max-w-4xl text-[16px] leading-relaxed text-black">
      <p className="whitespace-pre-wrap">
        {text}
        {streaming ? <span className="ml-0.5 inline-block h-6 w-0.5 animate-pulse bg-black/70 align-[-2px]" /> : null}
      </p>
    </div>
  );
}

function ActionProgress({ steps }: { steps: DemoProgressStep[] }) {
  return (
    <div className="max-w-4xl space-y-4 py-1">
      {steps.map((step) => (
        <div key={step.key} className="flex items-start gap-4">
          <div className="mt-1.5 shrink-0">
            <ProgressIcon status={step.status} />
          </div>
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
            <span
              className={cn(
                "text-[15px] leading-6",
                step.status === "running" ? "text-black" : "text-black/45",
                step.status === "error" && "text-[#D93025]",
              )}
            >
              {step.label}
            </span>
            {step.detail ? (
              <span className="text-[15px] leading-6 text-black/28">
                {step.detail}
              </span>
            ) : null}
            {step.durationLabel ? (
              <span className="text-[15px] leading-6 text-black/28">
                {step.durationLabel}
              </span>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function ProgressIcon({ status }: { status: DemoStepStatus }) {
  if (status === "completed") {
    return <Check className="size-5 text-black/35" strokeWidth={2} />;
  }

  if (status === "error") {
    return <X className="size-5 text-[#D93025]" strokeWidth={2.2} />;
  }

  if (status === "running") {
    return <div className="h-3.5 w-3.5 rounded-full bg-black/80" />;
  }

  return <div className="h-3.5 w-3.5 rounded-full bg-black/22" />;
}

function CartWidget({
  buyState,
  onBuy,
  widget,
}: {
  buyState: CartWidgetModel["buyState"];
  onBuy: () => Promise<void>;
  widget: CartWidgetModel;
}) {
  const budgetDelta =
    widget.subtotal !== null ? Math.round((widget.budget - widget.subtotal) * 100) / 100 : null;
  const buyLabel =
    buyState === "approving"
      ? "Opening checkout..."
      : buyState === "opened"
        ? "Checkout opened"
        : buyState === "error"
          ? "Try buy again"
          : "Buy";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-[rgba(0,0,0,0.62)]">
        <div className="grid h-10 w-10 place-items-center rounded-full bg-black text-white">
          <Sparkles className="size-4" strokeWidth={1.9} />
        </div>
        <span className="text-[16px] font-medium tracking-tight">Supplement checkout</span>
      </div>

      <div className="overflow-hidden rounded-[2rem] border border-black/10 bg-[#242424] text-white shadow-[0_24px_60px_rgba(0,0,0,0.18)]">
        <div className="flex items-start justify-between gap-4 border-b border-white/10 px-6 py-5">
          <div className="flex items-start gap-4">
            <div className="grid h-16 w-16 place-items-center rounded-2xl bg-[#1f6feb] text-center text-sm font-semibold text-white">
              {widget.storeName.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h3 className="text-[1.375rem] font-semibold leading-none tracking-tight">{widget.storeName}</h3>
              <p className="mt-2 text-[13px] text-white/60">{widget.statusLine}</p>
            </div>
          </div>
          {widget.checkoutUrl ? (
            <button
              className="rounded-full p-2 text-white/70 transition-colors hover:bg-white/8 hover:text-white"
              onClick={() => {
                if (!widget.checkoutUrl) {
                  return;
                }
                window.open(widget.checkoutUrl, "_blank", "noopener,noreferrer");
              }}
              title="Open checkout"
              type="button"
            >
              <ArrowUpRight className="size-5" strokeWidth={2} />
            </button>
          ) : null}
        </div>

        <div className="divide-y divide-white/10">
          {widget.items.map((item) => (
            <div key={item.key} className="flex items-center gap-4 px-6 py-4">
              <div className="grid h-16 w-16 shrink-0 place-items-center overflow-hidden rounded-2xl bg-white">
                {item.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img alt={item.title} className="h-full w-full object-cover" src={item.imageUrl} />
                ) : (
                  <div className="grid h-full w-full place-items-center bg-[#F3F3F3] text-xs font-semibold text-black">
                    {item.title.slice(0, 2).toUpperCase()}
                  </div>
                )}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate text-[16px] font-medium">{item.title}</p>
                  {item.tag ? (
                    <span className="rounded-full bg-white/12 px-2.5 py-1 text-xs font-medium text-white/78">
                      {item.tag}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-[13px] text-white/58">{item.subtitle}</p>
              </div>

              <div className="flex shrink-0 items-center gap-3">
                <div className="rounded-full border border-white/12 px-3 py-1.5 text-[13px] text-white/76">
                  Qty {item.quantity}
                </div>
                <div className="text-right">
                  <p className="text-[15px] font-medium">{item.amountLabel}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-5 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[13px] text-white/55">Ready for one-click handoff</p>
              <p className="mt-1 text-[13px] text-white/55">
                {budgetDelta === null
                  ? "Pricing will be finalized at checkout."
                  : budgetDelta >= 0
                    ? `${formatMoney(budgetDelta)} left in your budget`
                    : `${formatMoney(Math.abs(budgetDelta))} over budget`}
              </p>
            </div>
            <div className="text-right">
              <p className="text-[13px] text-white/55">Items subtotal</p>
              <p className="mt-1 text-[1.75rem] font-semibold leading-none">
                {widget.subtotal !== null ? formatMoney(widget.subtotal) : "Pending"}
              </p>
            </div>
          </div>

          <button
            className="flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#2d2d35] text-base font-semibold text-white transition-colors hover:bg-[#35353e] disabled:cursor-not-allowed disabled:opacity-70"
            disabled={!widget.checkoutUrl || buyState === "approving"}
            onClick={() => void onBuy()}
            type="button"
          >
            {buyState === "approving" ? <Loader2 className="size-5 animate-spin" strokeWidth={2} /> : null}
            {buyLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function ChatInput({
  disabled,
  onSend,
  onValueChange,
  placeholder,
  value,
  variant = "docked",
}: {
  disabled?: boolean;
  onSend: (message: string) => Promise<void> | void;
  onValueChange?: (value: string) => void;
  placeholder: string;
  value?: string;
  variant?: "centered" | "docked";
}) {
  const [internalValue, setInternalValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resolvedValue = value ?? internalValue;

  const setValue = (nextValue: string) => {
    if (onValueChange) {
      onValueChange(nextValue);
      return;
    }

    setInternalValue(nextValue);
  };

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 220)}px`;
  }, [resolvedValue]);

  const submit = async () => {
    const trimmed = resolvedValue.trim();
    if (!trimmed || disabled) {
      return;
    }

    await onSend(trimmed);
    setValue("");
  };

  return (
    <div
      className={cn(
        variant === "centered"
          ? "w-full"
          : "relative z-10 -mt-6 px-6 pb-6 pt-0",
      )}
    >
      <div className={cn("mx-auto", variant === "centered" ? "max-w-[760px]" : "max-w-5xl")}>
        <div
          className={cn(
            "flex items-end gap-3 transition-colors focus-within:bg-white",
            variant === "centered"
              ? "rounded-[2rem] border border-[#DADADA] bg-white px-4 py-3 shadow-[0_1px_2px_rgba(0,0,0,0.06)] focus-within:border-black/15"
              : "rounded-[1.75rem] border border-[#DADADA] bg-white px-4 py-2.5 shadow-[0_10px_30px_rgba(0,0,0,0.08)] focus-within:border-black/15",
          )}
        >
          <textarea
            ref={textareaRef}
            className={cn(
              "max-h-[220px] flex-1 resize-none bg-transparent px-1 text-[15px] leading-6 text-black outline-none placeholder:text-[rgba(0,0,0,0.42)] disabled:opacity-55",
              variant === "centered" ? "py-2" : "py-1.5",
            )}
            disabled={disabled}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={placeholder}
            rows={1}
            value={resolvedValue}
          />
          <button
            className={cn(
              "grid shrink-0 place-items-center rounded-full bg-black text-white transition-colors hover:bg-[#222] disabled:opacity-35",
              variant === "centered" ? "h-11 w-11" : "h-10 w-10",
            )}
            disabled={disabled || !resolvedValue.trim()}
            onClick={() => void submit()}
            type="button"
          >
            <ArrowUp className="size-4" strokeWidth={2.2} />
          </button>
        </div>
      </div>
    </div>
  );
}

function buildProfileContext(
  storedUserId: string | null,
  userProfile: UserProfileRead | undefined,
): ProfileContext {
  const resolvedUserId = storedUserId ?? DEMO_USER_ID;
  const allergies = userProfile?.allergies ?? DEFAULT_DEMO_PROFILE.allergies;
  const age = userProfile?.age ?? DEFAULT_DEMO_PROFILE.age;
  const weight = userProfile?.weight_lbs ?? DEFAULT_DEMO_PROFILE.weight_lbs;
  const sex = userProfile?.sex ?? DEFAULT_DEMO_PROFILE.sex;
  const weeklyBudget = userProfile?.budget_weekly ?? 25;
  const defaultBudget = Math.max(80, Math.round(weeklyBudget * 4));
  const usingFallback = !userProfile;

  return {
    userId: resolvedUserId,
    usingFallback,
    statsLabel: `${age} yrs, ${weight} lb, ${sex}`,
    allergyLabel: allergies.length ? joinList(allergies) : "no recorded allergies",
    memoryLabel: usingFallback ? "demo baseline memory" : "saved supplement baseline",
    defaultBudget,
    baseHealthProfile: {
      age,
      weight_lbs: weight,
      sex,
      current_supplements: [],
      medications: [],
      conditions: [],
      allergies,
    },
  };
}

function parsePromptIntent(prompt: string, profileContext: ProfileContext): DemoIntent {
  const normalizedPrompt = prompt.trim();
  const lowercasePrompt = normalizedPrompt.toLowerCase();
  const goalSet = new Set<string>();

  if (/(sleep|sleeping|insomnia|restless|bedtime)/.test(lowercasePrompt)) {
    goalSet.add("better sleep");
  }
  if (/(stress|stressed|anxious|anxiety|overwhelmed|work)/.test(lowercasePrompt)) {
    goalSet.add("stress support");
  }
  if (/(focus|brain fog|concentrat|clarity)/.test(lowercasePrompt)) {
    goalSet.add("focus support");
  }
  if (/(energy|tired|fatigue|exhausted)/.test(lowercasePrompt)) {
    goalSet.add("energy support");
  }
  if (/(immune|immunity|sick|cold)/.test(lowercasePrompt)) {
    goalSet.add("immune support");
  }

  const goals = goalSet.size ? Array.from(goalSet) : ["general wellness"];
  const budgetMatch =
    lowercasePrompt.match(/(?:under|below|within|max(?:imum)?(?: of)?|cap(?:ped)? at)\s*\$?(\d+(?:\.\d+)?)/) ??
    lowercasePrompt.match(/\$ ?(\d+(?:\.\d+)?)/);
  const budget = budgetMatch ? Number(budgetMatch[1]) : profileContext.defaultBudget;

  return {
    prompt: normalizedPrompt,
    budget,
    goals,
    conversationLabel: goals.slice(0, 2).join(" & "),
  };
}

function buildHealthProfile(intent: DemoIntent, profileContext: ProfileContext): HealthProfile {
  return {
    ...profileContext.baseHealthProfile,
    health_goals: intent.goals,
    monthly_budget: intent.budget,
  };
}

function buildOpeningNarrative(intent: DemoIntent, profileContext: ProfileContext): string {
  return [
    `I’m pulling ${profileContext.usingFallback ? "the demo fallback profile" : "your saved profile"} — ${profileContext.statsLabel} with ${profileContext.allergyLabel}.`,
    `Next I’ll check ${profileContext.memoryLabel}, search verified stores for ${joinHumanList(intent.goals)}, and build one cart under ${formatMoney(intent.budget)} total.`,
  ].join(" ");
}

function buildInitialProgressSteps(intent: DemoIntent, profileContext: ProfileContext): DemoProgressStep[] {
  return [
    {
      key: "profile",
      label: "Loaded profile stats and allergies",
      status: "completed",
      detail: profileContext.usingFallback ? "demo fallback profile" : "saved profile",
    },
    {
      key: "memory",
      label: "Checked supplement memory",
      status: "pending",
      detail: profileContext.memoryLabel,
    },
    {
      key: "discovery",
      label: "Searched stores and products",
      status: "pending",
      detail: joinHumanList(intent.goals),
    },
    {
      key: "analysis",
      label: "Built supplement plan",
      status: "pending",
    },
    {
      key: "checkout",
      label: "Filled cart and prepared checkout",
      status: "pending",
    },
  ];
}

function buildProgressSteps({
  events,
  intent,
  profileContext,
  runStatus,
  snapshot,
}: {
  events: SupplementRunEvent[];
  intent: DemoIntent;
  profileContext: ProfileContext;
  runStatus: SupplementRunLifecycleStatus | null;
  snapshot: SupplementStateSnapshot | null;
}): DemoProgressStep[] {
  const memoryStep = derivePhaseStep(events, "memory");
  const discoveryStep = derivePhaseStep(events, "discovery");
  const analysisStep = derivePhaseStep(events, "analysis");
  const checkoutStep = deriveCheckoutStep(events, runStatus, snapshot);

  return [
    {
      key: "profile",
      label: "Loaded profile stats and allergies",
      status: "completed",
      detail: profileContext.usingFallback ? "demo fallback profile" : "saved profile",
    },
    {
      key: "memory",
      label: "Checked supplement memory",
      status: memoryStep.status,
      detail: memoryStep.status === "completed" ? profileContext.memoryLabel : undefined,
      durationLabel: memoryStep.durationLabel,
    },
    {
      key: "discovery",
      label: "Searched stores and products",
      status: discoveryStep.status,
      detail:
        discoveryStep.status === "completed" && snapshot?.discovery_results.length
          ? `${snapshot.discovery_results.length} categories for ${joinHumanList(intent.goals)}`
          : undefined,
      durationLabel: discoveryStep.durationLabel,
    },
    {
      key: "analysis",
      label: "Built supplement plan",
      status: analysisStep.status,
      detail:
        analysisStep.status === "completed" && snapshot?.recommended_stack?.items.length
          ? `${snapshot.recommended_stack.items.length} products selected`
          : undefined,
      durationLabel: analysisStep.durationLabel,
    },
    {
      key: "checkout",
      label: "Filled cart and prepared checkout",
      status: checkoutStep.status,
      detail:
        checkoutStep.status === "completed" && snapshot?.store_carts.length
          ? `${formatStoreName(selectFeaturedCart(snapshot.store_carts, snapshot.approved_store_domains)?.store_domain ?? snapshot.store_carts[0].store_domain)} ready`
          : undefined,
      durationLabel: checkoutStep.durationLabel,
    },
  ];
}

function derivePhaseStep(
  events: SupplementRunEvent[],
  phase: "memory" | "discovery" | "analysis",
): { status: DemoStepStatus; durationLabel?: string } {
  const phaseStarted = events.find((event) => event.event_type === "phase_started" && event.phase === phase);
  const phaseCompleted = events.find((event) => event.event_type === "phase_completed" && event.phase === phase);
  const phaseErrored = events.find((event) => event.event_type === "error" && event.phase === phase);

  if (phaseErrored) {
    return { status: "error" };
  }

  if (phaseCompleted && phaseStarted) {
    return {
      status: "completed",
      durationLabel: formatDurationLabel(phaseStarted.created_at, phaseCompleted.created_at),
    };
  }

  if (phaseStarted) {
    return { status: "running" };
  }

  return { status: "pending" };
}

function deriveCheckoutStep(
  events: SupplementRunEvent[],
  runStatus: SupplementRunLifecycleStatus | null,
  snapshot: SupplementStateSnapshot | null,
): { status: DemoStepStatus; durationLabel?: string } {
  const phaseStarted = events.find((event) => event.event_type === "phase_started" && event.phase === "checkout");
  const phaseCompleted = events.find((event) => event.event_type === "phase_completed" && event.phase === "checkout");
  const phaseErrored = events.find((event) => event.event_type === "error" && event.phase === "checkout");

  if (phaseErrored || runStatus === "failed") {
    return { status: "error" };
  }

  if (
    phaseCompleted &&
    phaseStarted &&
    snapshot?.store_carts.some((cart) => Boolean(cart.checkout_url)) &&
    (runStatus === "awaiting_approval" || runStatus === "completed")
  ) {
    return {
      status: "completed",
      durationLabel: formatDurationLabel(phaseStarted.created_at, phaseCompleted.created_at),
    };
  }

  if (phaseStarted) {
    return { status: "running" };
  }

  return { status: "pending" };
}

function buildCartWidget({
  buyState,
  intent,
  runStatus,
  snapshot,
}: {
  buyState: CartWidgetModel["buyState"];
  intent: DemoIntent;
  runStatus: SupplementRunLifecycleStatus | null;
  snapshot: SupplementStateSnapshot | null;
}): CartWidgetModel | null {
  if (!snapshot) {
    return null;
  }

  const featuredCart = selectFeaturedCart(snapshot.store_carts, snapshot.approved_store_domains);
  if (!featuredCart) {
    return null;
  }

  const productIndex = createProductIndex(snapshot);
  const fallbackItems = snapshot.recommended_stack?.items ?? [];
  const lineItems = featuredCart.lines.length
    ? featuredCart.lines.map((line, index) => {
        const matchedProduct =
          productIndex.get(productIndexKey(featuredCart.store_domain, line.product_id)) ??
          fallbackItems.find((item) => normalizeProductTitle(item.product.title) === normalizeProductTitle(line.product_title)) ??
          null;

        return {
          key: `${featuredCart.store_domain}:${line.line_id || line.variant_id || index}`,
          title: line.product_title,
          subtitle: matchedProduct
            ? `${matchedProduct.goal} • ${line.variant_title || "selected option"}`
            : line.variant_title || "selected option",
          imageUrl: productImageUrl(matchedProduct?.product),
          quantity: line.quantity,
          amountLabel: formatMoney(line.total_amount ?? line.subtotal_amount ?? 0, line.currency || "USD"),
          tag: matchedProduct ? formatGoalTag(matchedProduct.goal) : undefined,
        };
      })
    : fallbackItems.slice(0, 4).map((item, index) => ({
        key: `${item.product.store_domain}:${item.product.product_id}:${index}`,
        title: item.product.title,
        subtitle: item.rationale || item.goal,
        imageUrl: productImageUrl(item.product),
        quantity: item.quantity,
        amountLabel:
          item.monthly_cost !== null
            ? formatMoney(item.monthly_cost, item.product.price_range.currency || "USD")
            : "Pending",
        tag: formatGoalTag(item.goal),
      }));

  return {
    storeDomain: featuredCart.store_domain,
    storeName: formatStoreName(featuredCart.store_domain),
    checkoutUrl: featuredCart.checkout_url,
    subtotal: featuredCart.total_amount ?? featuredCart.subtotal_amount,
    budget: intent.budget,
    approved: snapshot.approved_store_domains.includes(featuredCart.store_domain),
    buyState,
    statusLine:
      runStatus === "completed"
        ? "Approved and ready for checkout"
        : "Checkout-ready cart built from the selected supplement plan",
    items: lineItems,
  };
}

function buildReasoningText({
  intent,
  profileContext,
  snapshot,
  widget,
}: {
  intent: DemoIntent;
  profileContext: ProfileContext;
  snapshot: SupplementStateSnapshot;
  widget: CartWidgetModel;
}): string {
  const stack = snapshot.recommended_stack;
  const comparisons = snapshot.product_comparisons;
  const warnings = snapshot.critic_verdict?.warnings ?? [];
  const selectedItems = stack?.items.slice(0, 3) ?? [];
  const comparisonAlternatives = collectAlternatives(comparisons, selectedItems).slice(0, 2);
  const firstParagraph = [
    `I optimized for ${joinHumanList(intent.goals)} while keeping the cart at ${
      widget.subtotal !== null ? formatMoney(widget.subtotal) : formatMoney(intent.budget)
    }.`,
    profileContext.baseHealthProfile.allergies.length
      ? `I screened against ${profileContext.allergyLabel}.`
      : "There are no recorded allergies to filter against in this profile.",
  ].join(" ");

  const recommendationLines = selectedItems.map((item) => {
    const rationale =
      item.rationale ||
      `${item.goal} support with a cleaner ingredient profile than the nearby alternatives.`;
    return `- ${trimProductName(item.product.title)}: ${rationale}`;
  });

  const alternativeLine = comparisonAlternatives.length
    ? `Alternatives I kept on the bench: ${comparisonAlternatives.map((product) => trimProductName(product.title)).join(", ")}.`
    : "";
  const warningLine = warnings.length ? `Watch-outs: ${warnings.slice(0, 2).join(" ")}` : "";

  return [firstParagraph, recommendationLines.join("\n"), alternativeLine, warningLine]
    .filter(Boolean)
    .join("\n\n");
}

function createProductIndex(snapshot: SupplementStateSnapshot) {
  const productIndex = new Map<string, StackItem>();

  for (const item of snapshot.recommended_stack?.items ?? []) {
    productIndex.set(productIndexKey(item.product.store_domain, item.product.product_id), item);
  }

  return productIndex;
}

function productIndexKey(storeDomain: string, productId: string) {
  return `${storeDomain.toLowerCase()}:${productId}`;
}

function selectFeaturedCart(
  storeCarts: StoreCart[],
  approvedStoreDomains: string[],
): StoreCart | null {
  const readyCarts = storeCarts.filter((cart) => Boolean(cart.checkout_url));
  if (!readyCarts.length) {
    return null;
  }

  const approvedCart = readyCarts.find((cart) =>
    approvedStoreDomains.some((domain) => domain.toLowerCase() === cart.store_domain.toLowerCase()),
  );
  if (approvedCart) {
    return approvedCart;
  }

  return readyCarts
    .slice()
    .sort(
      (left, right) =>
        (left.total_amount ?? left.subtotal_amount ?? Number.POSITIVE_INFINITY) -
        (right.total_amount ?? right.subtotal_amount ?? Number.POSITIVE_INFINITY),
    )[0];
}

function collectAlternatives(comparisons: ProductComparison[], selectedItems: StackItem[]) {
  const selectedKeys = new Set(
    selectedItems.map((item) => productIndexKey(item.product.store_domain, item.product.product_id)),
  );

  return comparisons
    .flatMap((comparison) => comparison.ranked_products)
    .map((candidate) => candidate.product)
    .filter((product) => !selectedKeys.has(productIndexKey(product.store_domain, product.product_id)));
}

function productImageUrl(product: ShopifyProduct | undefined) {
  if (!product) {
    return null;
  }

  return product.image_url ?? product.variants.find((variant) => Boolean(variant.image_url))?.image_url ?? null;
}

function trimProductName(value: string) {
  return value.length > 72 ? `${value.slice(0, 69)}...` : value;
}

function formatStoreName(storeDomain: string) {
  const domain = storeDomain.replace(/^www\./, "").split(".")[0] ?? storeDomain;
  return domain
    .split(/[-_]/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function formatGoalTag(goal: string) {
  return goal.replace(/\b\w/g, (character) => character.toUpperCase());
}

function normalizeProductTitle(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function joinHumanList(values: string[]) {
  if (!values.length) {
    return "general support";
  }

  if (values.length === 1) {
    return values[0];
  }

  if (values.length === 2) {
    return `${values[0]} and ${values[1]}`;
  }

  return `${values.slice(0, -1).join(", ")}, and ${values.at(-1)}`;
}

function formatDurationLabel(startedAt: string, completedAt: string) {
  const started = new Date(startedAt).getTime();
  const completed = new Date(completedAt).getTime();
  const durationMs = Math.max(0, completed - started);

  if (durationMs < 1000) {
    return `${durationMs}ms`;
  }

  const seconds = durationMs / 1000;
  if (seconds < 10) {
    return `${seconds.toFixed(1)}s`;
  }

  return `${Math.round(seconds)}s`;
}

function inputPlaceholder(runStatus: SupplementRunLifecycleStatus | null) {
  if (runStatus === "running") {
    return "Building your supplement plan...";
  }

  return "Ask anything";
}

function createSessionKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return Math.random().toString(36).slice(2, 10);
}

function upsertMessage(messages: DemoMessage[], message: DemoMessage) {
  const existingIndex = messages.findIndex((candidate) => candidate.id === message.id);
  if (existingIndex === -1) {
    return [...messages, message];
  }

  const nextMessages = [...messages];
  nextMessages[existingIndex] = message;
  return nextMessages;
}

function streamAssistantText(
  messageId: string,
  targetText: string,
  setMessages: React.Dispatch<React.SetStateAction<DemoMessage[]>>,
  timersRef: React.MutableRefObject<Map<string, ReturnType<typeof setTimeout>>>,
) {
  const tokens = targetText.split(/(\s+)/).filter(Boolean);
  let tokenIndex = 0;

  const step = () => {
    tokenIndex = Math.min(tokens.length, tokenIndex + Math.max(1, Math.ceil(Math.random() * 2)));
    const nextText = tokens.slice(0, tokenIndex).join("");

    setMessages((previousMessages) =>
      upsertMessage(previousMessages, {
        id: messageId,
        type: "assistant",
        text: nextText,
        streaming: tokenIndex < tokens.length,
      }),
    );

    if (tokenIndex >= tokens.length) {
      timersRef.current.delete(messageId);
      return;
    }

    const timer = setTimeout(step, 26);
    timersRef.current.set(messageId, timer);
  };

  const existingTimer = timersRef.current.get(messageId);
  if (existingTimer) {
    clearTimeout(existingTimer);
  }

  step();
}

function clearAllTimers(
  timersRef: React.MutableRefObject<Map<string, ReturnType<typeof setTimeout>>>,
) {
  for (const timer of timersRef.current.values()) {
    clearTimeout(timer);
  }
  timersRef.current.clear();
}
