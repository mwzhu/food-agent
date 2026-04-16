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

import { BuyerProfileDrawer } from "@/components/v1/buyer-profile-drawer";
import { OrderConfirmationCard } from "@/components/v1/order-confirmation-card";
import { PaymentCredentialsModal } from "@/components/v1/payment-credentials-modal";
import { useCurrentUser } from "@/components/layout/providers";
import { useStartAgentCheckout, useUpdateSupplementCartQuantities } from "@/hooks/use-supplement-checkout";
import { useSupplementBuyerProfile, useUpsertSupplementBuyerProfile } from "@/hooks/use-supplement-buyer-profile";
import {
  useApproveSupplementRun,
  useCreateSupplementRun,
  useSupplementRun,
  useSupplementRunStream,
} from "@/hooks/use-supplement-run";
import { useUser } from "@/hooks/use-user";
import type {
  HealthProfile,
  PaymentCredentials,
  ProductComparison,
  ShopifyProduct,
  StackItem,
  StoreCart,
  StoreCartLine,
  SupplementBuyerProfileRead,
  SupplementBuyerProfileUpsertRequest,
  SupplementCheckoutSessionRead,
  SupplementOrderConfirmation,
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
    }
  | {
      id: string;
      type: "order_confirmation";
      confirmation: SupplementOrderConfirmation;
    }
  | {
      id: string;
      type: "agent_browser";
      session: SupplementCheckoutSessionRead;
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
  storeDomain: string;
  lineId: string | null;
  variantId: string | null;
  productId: string | null;
  title: string;
  subtitle: string;
  imageUrl: string | null;
  quantity: number;
  amountLabel: string;
  tag?: string;
};

type CartWidgetStore = {
  storeDomain: string;
  storeName: string;
  checkoutSession: SupplementCheckoutSessionRead | null;
  fallbackUrl: string | null;
  statusLine: string;
  subtotal: number | null;
  approved: boolean;
  items: CartWidgetLineItem[];
};

type CartWidgetModel = {
  stores: CartWidgetStore[];
  subtotal: number | null;
  budget: number;
  topLevelState: CheckoutTopLevelState;
  actionLabel: string;
};

type CheckoutTopLevelState =
  | "planning"
  | "awaiting_approval"
  | "checkout_in_progress"
  | "completed_or_needs_attention";

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
  const [buyerProfileOpen, setBuyerProfileOpen] = useState(false);
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [pendingAgentCheckoutAfterProfile, setPendingAgentCheckoutAfterProfile] = useState(false);
  const [selectedStoreDomain, setSelectedStoreDomain] = useState<string | null>(null);

  const userQuery = useUser(storedUserId);
  const createSupplementRunMutation = useCreateSupplementRun();
  const approveMutation = useApproveSupplementRun();
  const buyerProfileQuery = useSupplementBuyerProfile(runId ?? "", Boolean(runId));
  const upsertBuyerProfileMutation = useUpsertSupplementBuyerProfile();
  const startAgentCheckoutMutation = useStartAgentCheckout();
  const updateCartQuantitiesMutation = useUpdateSupplementCartQuantities();
  const runQuery = useSupplementRun(runId ?? "", true);
  const stream = useSupplementRunStream(runId ?? "");
  const snapshot = runQuery.data?.state_snapshot ?? null;
  const runStatus = runQuery.data?.status ?? null;
  const buyerProfile = buyerProfileQuery.data ?? null;
  const checkoutUiState = useMemo(() => deriveCheckoutUiState(runStatus, snapshot), [runStatus, snapshot]);

  const profileContext = useMemo(
    () => buildProfileContext(storedUserId, userQuery.data),
    [storedUserId, userQuery.data],
  );
  const currentConversationLabel = activeConversation?.intent.conversationLabel ?? "New conversation";
  const isEmptyConversation = !activeConversation && messages.length === 0;
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const streamedReasoningRef = useRef<Set<string>>(new Set());
  const streamedFailureRef = useRef<Set<string>>(new Set());
  const milestoneNarrationRef = useRef<Set<string>>(new Set());
  const actionPending =
    approveMutation.isPending ||
    upsertBuyerProfileMutation.isPending ||
    startAgentCheckoutMutation.isPending ||
    updateCartQuantitiesMutation.isPending;
  const activeCheckoutStore =
    selectedStoreDomain ??
    snapshot?.active_checkout_store ??
    snapshot?.checkout_sessions.find((checkoutSession) => !isCheckoutSessionTerminal(checkoutSession.status))?.store_domain ??
    null;
  const activeCheckoutSession =
    snapshot?.checkout_sessions.find((checkoutSession) => checkoutSession.store_domain === activeCheckoutStore) ?? null;

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
            checkoutUiState,
            intent: activeConversation.intent,
            runStatus,
            snapshot,
          })
        : null,
    [activeConversation, checkoutUiState, runStatus, snapshot],
  );

  useEffect(() => {
    return () => {
      clearAllTimers(timersRef);
    };
  }, []);

  useEffect(() => {
    if (!snapshot?.checkout_sessions.length) {
      if (!snapshot?.order_confirmations.length) {
        setSelectedStoreDomain(null);
      }
      return;
    }

    if (
      selectedStoreDomain &&
      snapshot.checkout_sessions.some((checkoutSession) => checkoutSession.store_domain === selectedStoreDomain)
    ) {
      return;
    }

    setSelectedStoreDomain(
      snapshot.active_checkout_store ?? snapshot.checkout_sessions.find((checkoutSession) => !isCheckoutSessionTerminal(checkoutSession.status))?.store_domain ?? snapshot.checkout_sessions[0]?.store_domain ?? null,
    );
  }, [selectedStoreDomain, snapshot]);

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
    if (!activeConversation || !snapshot) {
      return;
    }

    const visibleAgentSessions = snapshot.checkout_sessions.filter(
      (checkoutSession) =>
        checkoutSession.presentation_mode === "agent" && checkoutSession.status !== "order_placed",
    );
    const visibleMessageIds = new Set(
      visibleAgentSessions.map((checkoutSession) => `agent-browser:${checkoutSession.session_id}`),
    );

    setMessages((previousMessages) => {
      let nextMessages = previousMessages.filter(
        (message) => message.type !== "agent_browser" || visibleMessageIds.has(message.id),
      );

      visibleAgentSessions.forEach((checkoutSession) => {
        nextMessages = upsertMessage(nextMessages, {
          id: `agent-browser:${checkoutSession.session_id}`,
          type: "agent_browser",
          session: checkoutSession,
        });
      });

      return nextMessages;
    });
  }, [activeConversation, snapshot]);

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

  useEffect(() => {
    if (!activeConversation || !snapshot) {
      return;
    }

    if (runStatus === "awaiting_approval" && snapshot.store_carts.length) {
      queueNarration({
        key: `approval:${activeConversation.sessionKey}`,
        text: `I found ${snapshot.store_carts.length} store${snapshot.store_carts.length === 1 ? "" : "s"} for this stack. Confirm and buy when you’re ready, and I’ll stream the checkout browser directly into this chat.`,
        timersRef,
        messages,
        setMessages,
        seenRef: milestoneNarrationRef,
      });
    }

    if (snapshot.approved_store_domains.length && !snapshot.buyer_profile_ready) {
      queueNarration({
        key: `buyer:${activeConversation.sessionKey}`,
        text: "Before I buy, I need your shipping details.",
        timersRef,
        messages,
        setMessages,
        seenRef: milestoneNarrationRef,
      });
    }

    if (activeCheckoutSession) {
      const checkoutNarration =
        activeCheckoutSession.status === "agent_running"
          ? `Browser agent is checking out at ${formatStoreName(activeCheckoutSession.store_domain)}. Watch the live browser card in this chat.`
          : activeCheckoutSession.status === "failed"
            ? `${formatStoreName(activeCheckoutSession.store_domain)} checkout failed: ${activeCheckoutSession.error_message ?? "the store could not be reached from the browser agent."}`
            : activeCheckoutSession.presentation_mode === "external"
              ? `${formatStoreName(activeCheckoutSession.store_domain)} needs a controlled continuation step in the checkout panel.`
              : activeCheckoutSession.status === "order_placed"
                ? `${formatStoreName(activeCheckoutSession.store_domain)} order confirmation is ready in this chat.`
                : `${formatStoreName(activeCheckoutSession.store_domain)} checkout is waiting in this chat.`;

      queueNarration({
        key: `checkout:${activeConversation.sessionKey}:${activeCheckoutSession.store_domain}:${activeCheckoutSession.status}`,
        text: checkoutNarration,
        timersRef,
        messages,
        setMessages,
        seenRef: milestoneNarrationRef,
      });
    }

    snapshot.order_confirmations.forEach((confirmation) => {
      setMessages((previousMessages) =>
        upsertMessage(previousMessages, {
          id: `confirmation:${confirmation.confirmation_id}`,
          type: "order_confirmation",
          confirmation,
        }),
      );
      queueNarration({
        key: `order:${activeConversation.sessionKey}:${confirmation.confirmation_id}`,
        text: `${formatStoreName(confirmation.store_domain)} order placed.`,
        timersRef,
        messages,
        setMessages,
        seenRef: milestoneNarrationRef,
      });
    });
  }, [activeCheckoutSession, activeConversation, messages, runStatus, snapshot]);

  const resetWorkspace = () => {
    clearAllTimers(timersRef);
    streamedReasoningRef.current.clear();
    streamedFailureRef.current.clear();
    milestoneNarrationRef.current.clear();
    setRunId(null);
    setErrorMessage(null);
    setBuyerProfileOpen(false);
    setPaymentModalOpen(false);
    setPendingAgentCheckoutAfterProfile(false);
    setSelectedStoreDomain(null);
    setActiveConversation(null);
    setMessages([]);
  };

  const startConversation = async (prompt: string) => {
    clearAllTimers(timersRef);
    streamedReasoningRef.current.clear();
    streamedFailureRef.current.clear();
    milestoneNarrationRef.current.clear();
    setRunId(null);
    setErrorMessage(null);
    setBuyerProfileOpen(false);
    setPaymentModalOpen(false);
    setPendingAgentCheckoutAfterProfile(false);
    setSelectedStoreDomain(null);

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

  const handleAgentCheckout = async () => {
    if (!runId || !snapshot) {
      return;
    }

    const checkoutReadyStoreDomains = collectCheckoutReadyStoreDomains(snapshot);
    if (!checkoutReadyStoreDomains.length) {
      return;
    }

    if (
      snapshot.order_confirmations.length ||
      snapshot.checkout_sessions.some((checkoutSession) => checkoutSession.status === "agent_running")
    ) {
      setSelectedStoreDomain(activeCheckoutStore ?? checkoutReadyStoreDomains[0] ?? null);
      return;
    }

    setErrorMessage(null);

    try {
      let workingRun = runQuery.data;
      const approvedAllStores =
        snapshot.approved_store_domains.length === checkoutReadyStoreDomains.length &&
        checkoutReadyStoreDomains.every((storeDomain) => snapshot.approved_store_domains.includes(storeDomain));

      if (runStatus === "awaiting_approval" || !approvedAllStores) {
        workingRun = await approveMutation.mutateAsync({
          runId,
          payload: {
            approved_store_domains: checkoutReadyStoreDomains,
          },
        });
      }

      const approvedStoreDomains =
        workingRun?.state_snapshot.approved_store_domains.length
          ? workingRun.state_snapshot.approved_store_domains
          : checkoutReadyStoreDomains;
      setSelectedStoreDomain(approvedStoreDomains[0] ?? checkoutReadyStoreDomains[0] ?? null);

      if (!isBuyerProfileReady(buyerProfile)) {
        setPendingAgentCheckoutAfterProfile(true);
        setBuyerProfileOpen(true);
        return;
      }

      setPaymentModalOpen(true);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not prepare agent checkout.");
    }
  };

  const handleCartQuantityChange = async (item: CartWidgetLineItem, quantity: number) => {
    if (!runId || quantity < 1) {
      return;
    }

    try {
      setErrorMessage(null);
      await updateCartQuantitiesMutation.mutateAsync({
        runId,
        payload: {
          updates: [
            {
              store_domain: item.storeDomain,
              line_id: item.lineId,
              variant_id: item.variantId,
              product_id: item.productId,
              quantity,
            },
          ],
        },
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not update cart quantity.");
    }
  };

  const handleBuyerProfileSubmit = async (payload: SupplementBuyerProfileUpsertRequest) => {
    if (!runId) {
      return;
    }

    try {
      await upsertBuyerProfileMutation.mutateAsync({ runId, payload });
      setBuyerProfileOpen(false);
      if (pendingAgentCheckoutAfterProfile) {
        setPendingAgentCheckoutAfterProfile(false);
        setPaymentModalOpen(true);
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not save buyer setup.");
    }
  };

  const handlePaymentSubmit = async ({
    payment_credentials,
    simulate_success,
  }: {
    payment_credentials: PaymentCredentials;
    simulate_success: boolean;
  }) => {
    if (!runId || !snapshot) {
      return;
    }

    try {
      setPaymentModalOpen(false);
      const approvedStoreDomains = snapshot.approved_store_domains.length
        ? snapshot.approved_store_domains
        : collectCheckoutReadyStoreDomains(snapshot);
      const startedRun = await startAgentCheckoutMutation.mutateAsync({
        runId,
        payload: {
          store_domains: approvedStoreDomains,
          payment_credentials,
          simulate_success,
        },
      });
      setSelectedStoreDomain(
        startedRun.state_snapshot.active_checkout_store ??
          startedRun.state_snapshot.checkout_sessions[0]?.store_domain ??
          approvedStoreDomains[0] ??
          null,
      );
      setPendingAgentCheckoutAfterProfile(false);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not start agent checkout.");
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

      <div className="flex min-w-0 flex-1 bg-white">
        <div className="flex min-w-0 flex-1 flex-col bg-white">
          {isEmptyConversation ? (
            <NewConversationState
              disabled={
                createSupplementRunMutation.isPending ||
                runStatus === "running" ||
                runStatus === "awaiting_approval" ||
                actionPending
              }
              onSend={handleSend}
              suggestions={NEW_CONVERSATION_USE_CASES}
            />
          ) : (
            <ChatThread
              actionPending={actionPending}
              checkoutUiState={checkoutUiState}
              messages={messages}
              onCheckout={handleAgentCheckout}
              onQuantityChange={handleCartQuantityChange}
            />
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
                actionPending
              }
              onSend={handleSend}
              placeholder={inputPlaceholder(runStatus, checkoutUiState)}
            />
          )}
        </div>

      </div>

      <BuyerProfileDrawer
        defaultBudget={profileContext.defaultBudget}
        errorMessage={errorMessage}
        initialValue={buyerProfile}
        onClose={() => setBuyerProfileOpen(false)}
        onSubmit={handleBuyerProfileSubmit}
        open={buyerProfileOpen}
        saving={upsertBuyerProfileMutation.isPending}
      />
      <PaymentCredentialsModal
        errorMessage={errorMessage}
        onClose={() => {
          setPendingAgentCheckoutAfterProfile(false);
          setPaymentModalOpen(false);
        }}
        onSubmit={handlePaymentSubmit}
        open={paymentModalOpen}
        saving={startAgentCheckoutMutation.isPending}
      />
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
  actionPending,
  checkoutUiState,
  messages,
  onCheckout,
  onQuantityChange,
}: {
  actionPending: boolean;
  checkoutUiState: CheckoutTopLevelState;
  messages: DemoMessage[];
  onCheckout: () => Promise<void>;
  onQuantityChange: (item: CartWidgetLineItem, quantity: number) => Promise<void>;
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

  const agentBrowserSessions = messages.flatMap((message) =>
    message.type === "agent_browser" ? [message.session] : [],
  );
  const firstAgentBrowserMessageId = messages.find((message) => message.type === "agent_browser")?.id ?? null;
  const renderedMessages: ReactNode[] = [];
  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];

    if (message.type === "agent_browser") {
      if (message.id !== firstAgentBrowserMessageId) {
        continue;
      }

      renderedMessages.push(
        <AgentBrowserGrid
          key={`agent-browser-grid:${agentBrowserSessions.map((session) => session.session_id).join(":")}`}
          sessions={agentBrowserSessions}
        />,
      );
      continue;
    }

    renderedMessages.push(
      <MessageRow
        key={message.id}
        actionPending={actionPending}
        checkoutUiState={checkoutUiState}
        message={message}
        onCheckout={onCheckout}
        onQuantityChange={onQuantityChange}
      />,
    );
  }

  return (
    <div ref={containerRef} className="v1-scrollbar flex-1 overflow-y-auto px-6 pb-28 pt-6">
      <div className="mx-auto max-w-5xl space-y-6">
        {renderedMessages}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function MessageRow({
  actionPending,
  checkoutUiState,
  message,
  onCheckout,
  onQuantityChange,
}: {
  actionPending: boolean;
  checkoutUiState: CheckoutTopLevelState;
  message: DemoMessage;
  onCheckout: () => Promise<void>;
  onQuantityChange: (item: CartWidgetLineItem, quantity: number) => Promise<void>;
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
    return (
      <CartWidget
        actionPending={actionPending}
        checkoutUiState={checkoutUiState}
        onCheckout={onCheckout}
        onQuantityChange={onQuantityChange}
        widget={message.widget}
      />
    );
  }

  if (message.type === "order_confirmation") {
    return <OrderConfirmationCard confirmation={message.confirmation} />;
  }

  if (message.type === "agent_browser") {
    return <AgentBrowserLiveCard session={message.session} />;
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

function AgentBrowserGrid({ sessions }: { sessions: SupplementCheckoutSessionRead[] }) {
  return (
    <div className="grid w-full grid-cols-1 gap-3 md:grid-cols-2">
      {sessions.map((session) => (
        <AgentBrowserLiveCard key={session.session_id} session={session} />
      ))}
    </div>
  );
}

function AgentBrowserLiveCard({ session }: { session: SupplementCheckoutSessionRead }) {
  const liveUrl = payloadString(session.embedded_state_payload, "agent_live_url");
  const viewMode = payloadString(session.embedded_state_payload, "agent_view_mode") ?? "local";
  const statusText =
    payloadString(session.embedded_state_payload, "agent_status_text") ??
    (session.status === "agent_running" ? "Browser agent is working through checkout." : "Checkout needs attention.");
  const isRunning = session.status === "agent_running";
  const isCloud = viewMode === "cloud";

  return (
    <div className="min-w-0 overflow-hidden rounded-[1.35rem] border border-black/10 bg-[#0F1714] text-white shadow-[0_16px_38px_rgba(0,0,0,0.16)]">
      <div className="flex items-start justify-between gap-3 border-b border-white/10 px-4 py-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <p className="truncate text-[13px] font-semibold">Live checkout at {formatStoreName(session.store_domain)}</p>
            <span className="shrink-0 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-emerald-100">
              {isCloud ? "Cloud browser" : "Local browser"}
            </span>
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-5 text-white/60">{statusText}</p>
        </div>

        {liveUrl ? (
          <a
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-white/12 bg-white/8 px-2.5 py-1 text-[11px] font-semibold text-white/82 transition-colors hover:bg-white/12 hover:text-white"
            href={liveUrl}
            rel="noreferrer"
            target="_blank"
          >
            Open <ArrowUpRight className="size-3" strokeWidth={2} />
          </a>
        ) : null}
      </div>

      {liveUrl && isRunning ? (
        <div className="relative aspect-[16/9] min-h-[210px] bg-black">
          <iframe
            allow="autoplay; clipboard-read; clipboard-write; fullscreen"
            className="h-full w-full border-0"
            src={liveUrl}
            style={{ pointerEvents: "none" }}
            title={`Live checkout for ${session.store_domain}`}
          />
          <div className="pointer-events-none absolute left-3 top-3 rounded-full border border-white/12 bg-black/45 px-2.5 py-1 text-[11px] font-medium text-white/78 backdrop-blur">
            Watch-only
          </div>
        </div>
      ) : (
        <div className="grid min-h-[170px] place-items-center bg-[radial-gradient(circle_at_top_left,rgba(74,222,128,0.18),transparent_36%),linear-gradient(135deg,#101915,#17211d)] px-5 py-7 text-center">
          <div className="max-w-sm">
            {isRunning ? <Loader2 className="mx-auto size-5 animate-spin text-emerald-200" strokeWidth={2} /> : null}
            <p className="mt-3 text-sm font-semibold">
              {isRunning
                ? isCloud
                  ? "Waiting for Browser Use to attach the live stream..."
                  : "The agent is running in a local browser window."
                : session.status === "failed"
                  ? "Checkout stopped before completion."
                  : "Checkout session finished."}
            </p>
            <p className="mt-1.5 text-xs leading-5 text-white/58">
              {session.error_message ??
                (isCloud
                  ? "The iframe appears as soon as Browser Use Cloud returns the viewer URL."
                  : "Turn on cloud checkout mode to embed the browser stream directly in chat.")}
            </p>
          </div>
        </div>
      )}
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
  actionPending,
  checkoutUiState,
  onCheckout,
  onQuantityChange,
  widget,
}: {
  actionPending: boolean;
  checkoutUiState: CheckoutTopLevelState;
  onCheckout: () => Promise<void>;
  onQuantityChange: (item: CartWidgetLineItem, quantity: number) => Promise<void>;
  widget: CartWidgetModel;
}) {
  const budgetDelta =
    widget.subtotal !== null ? Math.round((widget.budget - widget.subtotal) * 100) / 100 : null;
  const canEditQuantities = checkoutUiState === "awaiting_approval" && !actionPending;

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
            <div className="grid h-16 w-16 place-items-center rounded-2xl bg-[#30E17A] text-center text-sm font-bold text-[#092313]">
              {widget.stores.length}
            </div>
            <div>
              <h3 className="text-[1.375rem] font-semibold leading-none tracking-tight">
                {widget.stores.length === 1 ? "1 store checkout" : `${widget.stores.length} store checkout`}
              </h3>
              <p className="mt-2 text-[13px] text-white/60">
                {widget.stores.length === 1
                  ? widget.stores[0].statusLine
                  : "Review every store and quantity before the browser agent starts."}
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-4 px-4 py-4">
          {widget.stores.map((store) => (
            <div key={store.storeDomain} className="overflow-hidden rounded-[1.45rem] border border-white/10 bg-white/[0.045]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold">{store.storeName}</p>
                    {store.approved ? (
                      <span className="rounded-full bg-[#30E17A]/14 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9DF7BC]">
                        Approved
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-xs text-white/50">{store.statusLine}</p>
                </div>
                <div className="flex items-center gap-3">
                  <p className="text-sm font-semibold text-white/86">
                    {store.subtotal !== null ? formatMoney(store.subtotal) : "Pending"}
                  </p>
                  {store.fallbackUrl ? (
                    <button
                      className="rounded-full p-2 text-white/62 transition-colors hover:bg-white/8 hover:text-white"
                      onClick={() => {
                        if (!store.fallbackUrl) {
                          return;
                        }
                        window.open(store.fallbackUrl, "_blank", "noopener,noreferrer");
                      }}
                      title={`Open ${store.storeName} checkout`}
                      type="button"
                    >
                      <ArrowUpRight className="size-4" strokeWidth={2} />
                    </button>
                  ) : null}
                </div>
              </div>

              <div className="divide-y divide-white/8">
                {store.items.map((item) => (
                  <div key={item.key} className="flex items-center gap-4 px-4 py-3">
                    <div className="grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-2xl bg-white">
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
                        <p className="truncate text-[15px] font-medium">{item.title}</p>
                        {item.tag ? (
                          <span className="rounded-full bg-white/12 px-2.5 py-1 text-xs font-medium text-white/78">
                            {item.tag}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-[13px] text-white/58">{item.subtitle}</p>
                    </div>

                    <div className="flex shrink-0 items-center gap-3">
                      <div className="flex items-center rounded-full border border-white/14 bg-black/18 p-1">
                        <button
                          className="grid h-7 w-7 place-items-center rounded-full text-white/72 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
                          disabled={!canEditQuantities || item.quantity <= 1}
                          onClick={() => void onQuantityChange(item, item.quantity - 1)}
                          type="button"
                        >
                          -
                        </button>
                        <span className="min-w-8 px-2 text-center text-sm font-semibold text-white">
                          {item.quantity}
                        </span>
                        <button
                          className="grid h-7 w-7 place-items-center rounded-full text-white/72 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
                          disabled={!canEditQuantities}
                          onClick={() => void onQuantityChange(item, item.quantity + 1)}
                          type="button"
                        >
                          +
                        </button>
                      </div>
                      <div className="w-20 text-right">
                        <p className="text-[15px] font-medium">{item.amountLabel}</p>
                      </div>
                    </div>
                  </div>
                ))}
                {!store.items.length ? (
                  <div className="px-4 py-5 text-sm text-white/52">No purchasable items were found for this store.</div>
                ) : null}
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-5 border-t border-white/10 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-[13px] text-white/55">{descriptionForCheckoutState(checkoutUiState)}</p>
              <p className="mt-1 text-[13px] text-white/55">
                {budgetDelta === null
                  ? "Pricing will be finalized at checkout."
                  : budgetDelta >= 0
                    ? `${formatMoney(budgetDelta)} left in your budget`
                    : `${formatMoney(Math.abs(budgetDelta))} over budget`}
              </p>
              {canEditQuantities ? (
                <p className="mt-1 text-[13px] text-[#9DF7BC]">
                  Use + and - to adjust quantities before buying.
                </p>
              ) : null}
            </div>
            <div className="text-right">
              <p className="text-[13px] text-white/55">Planned subtotal</p>
              <p className="mt-1 text-[1.75rem] font-semibold leading-none">
                {widget.subtotal !== null ? formatMoney(widget.subtotal) : "Pending"}
              </p>
            </div>
          </div>

          <button
            className="flex h-14 w-full items-center justify-center gap-3 rounded-full bg-[#30E17A] text-base font-bold text-[#092313] shadow-[0_16px_38px_rgba(48,225,122,0.30)] transition-all hover:-translate-y-0.5 hover:bg-[#50F08F] disabled:translate-y-0 disabled:cursor-not-allowed disabled:bg-white/18 disabled:text-white/42 disabled:shadow-none"
            disabled={checkoutUiState === "planning" || actionPending}
            onClick={() => void onCheckout()}
            type="button"
          >
            {actionPending ? <Loader2 className="size-5 animate-spin" strokeWidth={2} /> : null}
            {actionPending ? "Updating checkout..." : widget.actionLabel}
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
  checkoutUiState,
  intent,
  runStatus,
  snapshot,
}: {
  checkoutUiState: CheckoutTopLevelState;
  intent: DemoIntent;
  runStatus: SupplementRunLifecycleStatus | null;
  snapshot: SupplementStateSnapshot | null;
}): CartWidgetModel | null {
  if (!snapshot) {
    return null;
  }

  const readyCarts = snapshot.store_carts.filter((cart) => Boolean(cart.checkout_url));
  if (!readyCarts.length) {
    return null;
  }
  const productIndex = createProductIndex(snapshot);
  const fallbackItems = snapshot.recommended_stack?.items ?? [];
  const stores = readyCarts.map((cart) => {
    const checkoutSession =
      snapshot.checkout_sessions.find((session) => session.store_domain === cart.store_domain) ?? null;
    return {
      storeDomain: cart.store_domain,
      storeName: formatStoreName(cart.store_domain),
      checkoutSession,
      fallbackUrl: checkoutSession?.fallback_url ?? cart.checkout_url,
      subtotal: cart.total_amount ?? cart.subtotal_amount,
      approved: snapshot.approved_store_domains.includes(cart.store_domain),
      statusLine: statusLineForWidget(runStatus, snapshot, checkoutSession),
      items: cart.lines.length
        ? cart.lines.map((line, index) =>
            buildCartWidgetLineItem({
              cart,
              fallbackItems,
              index,
              line,
              productIndex,
            }),
          )
        : fallbackItems
            .filter((item) => item.product.store_domain === cart.store_domain)
            .map((item, index) => buildFallbackCartWidgetLineItem(item, index)),
    };
  });
  const subtotal = sumNullable(stores.map((store) => store.subtotal));

  return {
    stores,
    subtotal,
    budget: intent.budget,
    topLevelState: checkoutUiState,
    actionLabel: actionLabelForWidget(checkoutUiState, snapshot),
  };
}

function buildCartWidgetLineItem({
  cart,
  fallbackItems,
  index,
  line,
  productIndex,
}: {
  cart: StoreCart;
  fallbackItems: StackItem[];
  index: number;
  line: StoreCartLine;
  productIndex: Map<string, StackItem>;
}): CartWidgetLineItem {
  const matchedProduct =
    productIndex.get(productIndexKey(cart.store_domain, line.product_id)) ??
    fallbackItems.find((item) => normalizeProductTitle(item.product.title) === normalizeProductTitle(line.product_title)) ??
    null;

  return {
    key: `${cart.store_domain}:${line.line_id || line.variant_id || index}`,
    storeDomain: cart.store_domain,
    lineId: line.line_id || null,
    variantId: line.variant_id || null,
    productId: line.product_id || null,
    title: line.product_title,
    subtitle: matchedProduct
      ? `${matchedProduct.goal} • ${line.variant_title || "selected option"}`
      : line.variant_title || "selected option",
    imageUrl: productImageUrl(matchedProduct?.product),
    quantity: line.quantity,
    amountLabel:
      line.total_amount !== null || line.subtotal_amount !== null
        ? formatMoney(line.total_amount ?? line.subtotal_amount ?? 0, line.currency || "USD")
        : "Pending",
    tag: matchedProduct ? formatGoalTag(matchedProduct.goal) : undefined,
  };
}

function buildFallbackCartWidgetLineItem(item: StackItem, index: number): CartWidgetLineItem {
  return {
    key: `${item.product.store_domain}:${item.product.product_id}:${index}`,
    storeDomain: item.product.store_domain,
    lineId: null,
    variantId: item.product.variants[0]?.variant_id ?? null,
    productId: item.product.product_id,
    title: item.product.title,
    subtitle: item.rationale || item.goal,
    imageUrl: productImageUrl(item.product),
    quantity: item.quantity,
    amountLabel:
      item.monthly_cost !== null
        ? formatMoney(item.monthly_cost, item.product.price_range.currency || "USD")
        : "Pending",
    tag: formatGoalTag(item.goal),
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

function deriveCheckoutUiState(
  runStatus: SupplementRunLifecycleStatus | null,
  snapshot: SupplementStateSnapshot | null,
): CheckoutTopLevelState {
  if (!snapshot || runStatus === null) {
    return "planning";
  }

  if (runStatus === "failed" || runStatus === "completed" || snapshot.order_confirmations.length) {
    return "completed_or_needs_attention";
  }

  if (snapshot.checkout_sessions.length || snapshot.approved_store_domains.length) {
    return "checkout_in_progress";
  }

  if (runStatus === "awaiting_approval") {
    return "awaiting_approval";
  }

  return "planning";
}

function isBuyerProfileReady(profile: SupplementBuyerProfileRead | null) {
  if (!profile) {
    return false;
  }

  return Boolean(
    profile.email &&
      profile.shipping_name &&
      profile.shipping_address.line1 &&
      profile.shipping_address.city &&
      profile.shipping_address.state &&
      profile.shipping_address.postal_code &&
      profile.consent_granted,
  );
}

function isCheckoutSessionTerminal(status: SupplementCheckoutSessionRead["status"]) {
  return status === "order_placed" || status === "cancelled" || status === "failed";
}

function collectCheckoutReadyStoreDomains(snapshot: SupplementStateSnapshot) {
  return snapshot.store_carts
    .filter((cart) => Boolean(cart.checkout_url))
    .map((cart) => cart.store_domain.toLowerCase());
}

function actionLabelForWidget(
  checkoutUiState: CheckoutTopLevelState,
  snapshot: SupplementStateSnapshot,
) {
  if (checkoutUiState === "planning") {
    return "Preparing stack";
  }

  if (checkoutUiState === "awaiting_approval") {
    return "Confirm and buy";
  }

  if (snapshot.order_confirmations.length) {
    return "View confirmations";
  }

  if (!snapshot.buyer_profile_ready) {
    return "Add buyer setup";
  }

  if (snapshot.checkout_sessions.some((checkoutSession) => checkoutSession.status === "agent_running")) {
    return "Agent checkout running...";
  }

  if (snapshot.checkout_sessions.some((checkoutSession) => checkoutSession.presentation_mode === "agent")) {
    return "View live checkout";
  }

  if (snapshot.checkout_sessions.length) {
    return "Open in-app checkout";
  }

  return "Confirm and buy";
}

function statusLineForWidget(
  runStatus: SupplementRunLifecycleStatus | null,
  snapshot: SupplementStateSnapshot,
  checkoutSession: SupplementCheckoutSessionRead | null,
) {
  if (snapshot.order_confirmations.length) {
    return "Order confirmation synced back into the conversation";
  }

  if (runStatus === "awaiting_approval") {
    return "I built the carts. Confirm and buy when you want the browser agent to place the orders.";
  }

  if (!snapshot.buyer_profile_ready && snapshot.approved_store_domains.length) {
    return "Stores approved. Next I need shipping details before the browser agent can start.";
  }

  if (checkoutSession?.status === "agent_running") {
    const liveUrl = payloadString(checkoutSession.embedded_state_payload, "agent_live_url");
    return liveUrl
      ? "Browser agent is running in the embedded cloud browser."
      : "Browser agent is starting the checkout browser.";
  }

  if (checkoutSession?.status === "failed") {
    return checkoutSession.error_message
      ? `Checkout failed: ${checkoutSession.error_message}`
      : "Checkout failed before the browser agent could reach the store.";
  }

  if (checkoutSession?.presentation_mode === "agent") {
    return "Browser-agent checkout progress appears directly in this chat.";
  }

  if (checkoutSession?.presentation_mode === "external") {
    return "Checkout is ready, with a controlled handoff if embedding is blocked.";
  }

  if (checkoutSession) {
    return "Embedded checkout session is ready in this chat.";
  }

  return "Checkout-ready cart built from the selected supplement plan.";
}

function descriptionForCheckoutState(checkoutUiState: CheckoutTopLevelState) {
  switch (checkoutUiState) {
    case "planning":
      return "Building your supplement plan";
    case "awaiting_approval":
      return "Awaiting store approval";
    case "checkout_in_progress":
      return "Checkout in progress";
    case "completed_or_needs_attention":
      return "Completed or needs attention";
    default:
      return "Supplement checkout";
  }
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

function sumNullable(values: Array<number | null>) {
  if (values.some((value) => value === null)) {
    return null;
  }

  let total = 0;
  values.forEach((value) => {
    total += value ?? 0;
  });
  return Math.round(total * 100) / 100;
}

function payloadString(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  return typeof value === "string" && value.trim() ? value : null;
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

function inputPlaceholder(
  runStatus: SupplementRunLifecycleStatus | null,
  checkoutUiState: CheckoutTopLevelState,
) {
  if (checkoutUiState === "checkout_in_progress") {
    return "Checkout is active in chat...";
  }

  if (runStatus === "running") {
    return "Building your supplement plan...";
  }

  return "Ask anything";
}

function queueNarration({
  key,
  text,
  timersRef,
  messages,
  setMessages,
  seenRef,
}: {
  key: string;
  text: string;
  timersRef: React.MutableRefObject<Map<string, ReturnType<typeof setTimeout>>>;
  messages: DemoMessage[];
  setMessages: React.Dispatch<React.SetStateAction<DemoMessage[]>>;
  seenRef: React.MutableRefObject<Set<string>>;
}) {
  if (seenRef.current.has(key)) {
    return;
  }

  const assistantMessage = messages.find((message) => message.type === "assistant" && message.text === text);
  if (assistantMessage) {
    seenRef.current.add(key);
    return;
  }

  seenRef.current.add(key);
  setMessages((previousMessages) =>
    upsertMessage(previousMessages, {
      id: key,
      type: "assistant",
      text: "",
      streaming: true,
    }),
  );
  streamAssistantText(key, text, setMessages, timersRef);
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
