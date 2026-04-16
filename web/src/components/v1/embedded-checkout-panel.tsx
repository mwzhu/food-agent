"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Loader2, ShieldCheck, X } from "lucide-react";

import { OrderConfirmationCard } from "@/components/v1/order-confirmation-card";
import { PaymentSetupBanner } from "@/components/v1/payment-setup-banner";
import { StoreCheckoutTimeline } from "@/components/v1/store-checkout-timeline";
import type {
  SupplementCheckoutSessionRead,
  SupplementOrderConfirmation,
} from "@/lib/supplement-types";
import { cn, formatMoney } from "@/lib/utils";

type EmbeddedCheckoutPanelProps = {
  buyerProfileReady: boolean;
  confirming: boolean;
  errorMessage: string | null;
  fallbackReason: string | null;
  onCancelStore: (storeDomain: string) => Promise<void>;
  onClose: () => void;
  onOpenBuyerProfile: () => void;
  onMarkOrderPlaced?: (storeDomain: string) => Promise<void>;
  onOpenFallback?: (storeDomain: string, fallbackUrl: string) => Promise<void>;
  onSelectStore: (storeDomain: string) => void;
  open: boolean;
  orderConfirmations: SupplementOrderConfirmation[];
  sessions: SupplementCheckoutSessionRead[];
  selectedStoreDomain: string | null;
};

export function EmbeddedCheckoutPanel({
  buyerProfileReady,
  confirming,
  errorMessage,
  fallbackReason,
  onCancelStore,
  onClose,
  onOpenBuyerProfile,
  onMarkOrderPlaced,
  onOpenFallback,
  onSelectStore,
  open,
  orderConfirmations,
  selectedStoreDomain,
  sessions,
}: EmbeddedCheckoutPanelProps) {
  const [iframeLoaded, setIframeLoaded] = useState(false);
  const [iframeTimedOut, setIframeTimedOut] = useState(false);
  const activeSession =
    sessions.find((session) => session.store_domain === selectedStoreDomain) ??
    sessions.find((session) => !session.order_confirmation) ??
    sessions[0] ??
    null;
  const usesAgentMode = sessions.some((session) => session.presentation_mode === "agent");
  const visibleConfirmations =
    activeSession?.presentation_mode === "agent" && activeSession.order_confirmation
      ? orderConfirmations.filter(
          (confirmation) => confirmation.confirmation_id !== activeSession.order_confirmation?.confirmation_id,
        )
      : orderConfirmations;

  useEffect(() => {
    setIframeLoaded(false);
    setIframeTimedOut(false);
  }, [activeSession?.continue_url]);

  useEffect(() => {
    if (!open || !activeSession || activeSession.presentation_mode !== "iframe") {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setIframeTimedOut(true);
    }, 4500);
    return () => window.clearTimeout(timeoutId);
  }, [activeSession, open]);

  if (!open) {
    return null;
  }

  return (
    <aside className="fixed inset-0 z-40 flex flex-col bg-white lg:static lg:w-[430px] lg:shrink-0 lg:border-l lg:border-black/6">
      <div className="flex items-center justify-between border-b border-black/8 px-4 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-black/42">
            {usesAgentMode ? "Agent checkout" : "Embedded checkout"}
          </p>
          <h2 className="mt-1 text-[1.1rem] font-semibold tracking-tight text-black">
            {usesAgentMode ? "Watch the browser place the orders" : "Keep the purchase in /v1"}
          </h2>
        </div>
        <button
          className="rounded-full p-2 text-black/55 transition-colors hover:bg-black/5 hover:text-black lg:hidden"
          onClick={onClose}
          type="button"
        >
          <X className="size-5" strokeWidth={1.8} />
        </button>
      </div>

      <div className="v1-scrollbar flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {!buyerProfileReady ? <PaymentSetupBanner onOpenBuyerProfile={onOpenBuyerProfile} /> : null}

        {sessions.length ? (
          <StoreCheckoutTimeline
            activeStoreDomain={activeSession?.store_domain ?? null}
            onSelectStore={onSelectStore}
            sessions={sessions}
          />
        ) : null}

        {activeSession ? (
          <div className="space-y-4 rounded-[1.6rem] border border-black/8 bg-[#FAFAFB] p-3">
            {activeSession.presentation_mode === "agent" ? (
              <div className="space-y-4">
                <div className="rounded-[1.35rem] border border-black/8 bg-white px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-black">{formatStoreName(activeSession.store_domain)}</p>
                      <p className="mt-1 text-xs leading-5 text-black/52">{resolveAgentStatusText(activeSession)}</p>
                    </div>
                    {activeSession.order_total !== null ? (
                      <p className="text-sm font-semibold text-black">
                        {formatMoney(activeSession.order_total, activeSession.currency ?? "USD")}
                      </p>
                    ) : null}
                  </div>

                  <div className="mt-4 rounded-[1.2rem] border border-[#D9E6FF] bg-[#F4F8FF] p-4">
                    <div className="flex items-center gap-3">
                      {activeSession.status === "agent_running" ? (
                        <div className="grid size-10 place-items-center rounded-full bg-white text-[#3453A3] shadow-sm">
                          <Loader2 className="size-5 animate-spin" strokeWidth={2.2} />
                        </div>
                      ) : (
                        <div className="grid size-10 place-items-center rounded-full bg-white text-[#2F6D3A] shadow-sm">
                          <ShieldCheck className="size-5" strokeWidth={2} />
                        </div>
                      )}
                      <div>
                        <p className="text-sm font-semibold text-black">{agentHeadline(activeSession)}</p>
                        <p className="mt-1 text-xs leading-5 text-black/58">
                          Visible Chromium windows open on your desktop while the agent works through checkout.
                        </p>
                      </div>
                    </div>
                  </div>

                  {activeSession.error_message ? (
                    <p className="mt-4 rounded-[1.2rem] border border-[#F3C5C5] bg-[#FFF3F3] px-4 py-3 text-sm text-[#B32F2F]">
                      {activeSession.error_message}
                    </p>
                  ) : null}
                </div>

                {activeSession.order_confirmation ? (
                  <OrderConfirmationCard confirmation={activeSession.order_confirmation} />
                ) : null}

                {!activeSession.order_confirmation && activeSession.status !== "cancelled" ? (
                  <button
                    className="w-full rounded-full border border-black/12 px-4 py-3 text-sm font-medium text-black/72 transition-colors hover:bg-black/4"
                    disabled={confirming}
                    onClick={() => void onCancelStore(activeSession.store_domain)}
                    type="button"
                  >
                    Skip this store
                  </button>
                ) : null}
              </div>
            ) : (
              <>
                <div className="rounded-[1.35rem] border border-black/8 bg-white px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-black">{formatStoreName(activeSession.store_domain)}</p>
                      <p className="mt-1 text-xs leading-5 text-black/52">{describeActiveSession(activeSession)}</p>
                    </div>
                    {activeSession.order_total !== null ? (
                      <p className="text-sm font-semibold text-black">
                        {formatMoney(activeSession.order_total, activeSession.currency ?? "USD")}
                      </p>
                    ) : null}
                  </div>

                  <div className="mt-3 flex items-center gap-2 rounded-full bg-[#F5F5F6] px-3 py-2 text-[12px] text-black/58">
                    <ShieldCheck className="size-4 text-[#2F6D3A]" strokeWidth={1.9} />
                    Payment details stay with the merchant checkout.
                  </div>
                </div>

                {activeSession.presentation_mode === "iframe" && activeSession.continue_url ? (
                  <div className="overflow-hidden rounded-[1.35rem] border border-black/8 bg-white">
                    <div className="relative h-[420px] bg-[#F4F4F5]">
                      {!iframeLoaded ? (
                        <div className="absolute inset-0 grid place-items-center bg-[#F4F4F5] text-sm text-black/48">
                          <div className="flex items-center gap-2">
                            <Loader2 className="size-4 animate-spin" strokeWidth={2} />
                            Loading merchant checkout
                          </div>
                        </div>
                      ) : null}
                      {/* eslint-disable-next-line @next/next/no-sync-scripts */}
                      <iframe
                        className="h-full w-full bg-white"
                        onLoad={() => setIframeLoaded(true)}
                        src={activeSession.continue_url}
                        title={`${formatStoreName(activeSession.store_domain)} checkout`}
                      />
                    </div>
                  </div>
                ) : null}

                {(activeSession.presentation_mode === "external" || iframeTimedOut || fallbackReason) &&
                activeSession.fallback_url ? (
                  <div className="rounded-[1.35rem] border border-[#E9D7B3] bg-[#FFF9EE] px-4 py-4 text-sm text-[#6B4B10]">
                    <p className="font-medium text-[#4B3410]">Fallback handoff ready</p>
                    <p className="mt-1 leading-6">
                      {fallbackReason ??
                        "If the merchant blocks embedding, keep the context here and open the same checkout in a controlled handoff."}
                    </p>
                    {onOpenFallback ? (
                      <button
                        className="mt-3 inline-flex items-center gap-2 rounded-full bg-[#4B3410] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#5B4015]"
                        onClick={() => void onOpenFallback(activeSession.store_domain, activeSession.fallback_url!)}
                        type="button"
                      >
                        <ExternalLink className="size-4" strokeWidth={2} />
                        Open fallback checkout
                      </button>
                    ) : null}
                  </div>
                ) : null}

                {errorMessage ? (
                  <p className="rounded-[1.2rem] border border-[#F3C5C5] bg-[#FFF3F3] px-4 py-3 text-sm text-[#B32F2F]">
                    {errorMessage}
                  </p>
                ) : null}

                <div className="grid gap-2 sm:grid-cols-2">
                  {onMarkOrderPlaced ? (
                    <button
                      className={cn(
                        "rounded-full bg-black px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-[#222]",
                        confirming && "opacity-80",
                      )}
                      disabled={confirming}
                      onClick={() => void onMarkOrderPlaced(activeSession.store_domain)}
                      type="button"
                    >
                      {confirming ? "Saving..." : "I completed this order"}
                    </button>
                  ) : null}
                  <button
                    className="rounded-full border border-black/12 px-4 py-3 text-sm font-medium text-black/72 transition-colors hover:bg-black/4"
                    disabled={confirming}
                    onClick={() => void onCancelStore(activeSession.store_domain)}
                    type="button"
                  >
                    Skip this store
                  </button>
                </div>
              </>
            )}
          </div>
        ) : null}

        {visibleConfirmations.length ? (
          <div className="space-y-3">
            {visibleConfirmations.map((confirmation) => (
              <OrderConfirmationCard key={confirmation.confirmation_id} confirmation={confirmation} />
            ))}
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function describeActiveSession(session: SupplementCheckoutSessionRead) {
  if (session.presentation_mode === "agent") {
    return resolveAgentStatusText(session);
  }
  if (session.order_confirmation) {
    return session.order_confirmation.message;
  }
  if (session.error_message) {
    return session.error_message;
  }
  if (session.presentation_mode === "external") {
    return "Merchant checkout needs a controlled handoff.";
  }
  return "Confirm the checkout in-app, then mark the store as placed once the merchant confirms the order.";
}

function resolveAgentStatusText(session: SupplementCheckoutSessionRead) {
  const statusText = session.embedded_state_payload["agent_status_text"];
  if (typeof statusText === "string" && statusText.trim()) {
    return statusText;
  }
  if (session.order_confirmation) {
    return session.order_confirmation.message;
  }
  if (session.status === "failed") {
    return session.error_message ?? "Browser agent could not finish checkout.";
  }
  if (session.status === "cancelled") {
    return "Store skipped from the agent queue.";
  }
  return "Browser agent is navigating the merchant checkout.";
}

function agentHeadline(session: SupplementCheckoutSessionRead) {
  if (session.order_confirmation) {
    return "Order placed and confirmation synced";
  }
  if (session.status === "failed") {
    return "Agent needs attention";
  }
  if (session.status === "cancelled") {
    return "Store skipped";
  }
  return "Agent checkout is in progress";
}

function formatStoreName(storeDomain: string) {
  const domain = storeDomain.replace(/^www\./, "").split(".")[0] ?? storeDomain;
  return domain
    .split(/[-_]/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}
