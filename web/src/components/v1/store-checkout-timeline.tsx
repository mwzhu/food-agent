"use client";

import type { SupplementCheckoutSessionRead } from "@/lib/supplement-types";
import { cn } from "@/lib/utils";

type StoreCheckoutTimelineProps = {
  activeStoreDomain: string | null;
  onSelectStore: (storeDomain: string) => void;
  sessions: SupplementCheckoutSessionRead[];
};

export function StoreCheckoutTimeline({
  activeStoreDomain,
  onSelectStore,
  sessions,
}: StoreCheckoutTimelineProps) {
  return (
    <div className="space-y-2">
      {sessions.map((session) => {
        const isActive = activeStoreDomain === session.store_domain;
        return (
          <button
            key={session.session_id}
            className={cn(
              "flex w-full items-center justify-between rounded-[1.2rem] border px-3 py-3 text-left transition-colors",
              isActive ? "border-black/16 bg-white text-black" : "border-black/8 bg-[#F7F7F8] text-black/74 hover:bg-white",
            )}
            onClick={() => onSelectStore(session.store_domain)}
            type="button"
          >
            <div>
              <p className="text-sm font-medium">{formatStoreName(session.store_domain)}</p>
              <p className="mt-1 text-xs text-black/42">{describeSessionStatus(session)}</p>
            </div>
            <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]", badgeClass(session.status))}>
              {session.status.replace(/_/g, " ")}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function describeSessionStatus(session: SupplementCheckoutSessionRead) {
  if (session.order_confirmation) {
    return session.order_confirmation.message;
  }
  if (session.error_message) {
    return session.error_message;
  }
  if (session.status === "agent_running") {
    return "Browser agent is working through checkout in a visible window.";
  }
  if (session.presentation_mode === "agent") {
    return "Ready for browser-agent checkout.";
  }
  if (session.presentation_mode === "external") {
    return "Fallback handoff is ready inside the panel.";
  }
  return "Embedded checkout is ready for confirmation.";
}

function badgeClass(status: SupplementCheckoutSessionRead["status"]) {
  switch (status) {
    case "agent_running":
      return "animate-pulse bg-[#E8F0FF] text-[#3453A3]";
    case "order_placed":
      return "bg-[#EAF7EE] text-[#216A34]";
    case "cancelled":
      return "bg-[#F1F1F1] text-black/55";
    case "external_handoff":
      return "bg-[#FFF4E6] text-[#A06100]";
    case "failed":
      return "bg-[#FFF0F0] text-[#B32F2F]";
    default:
      return "bg-[#EEF2FF] text-[#3453A3]";
  }
}

function formatStoreName(storeDomain: string) {
  const domain = storeDomain.replace(/^www\./, "").split(".")[0] ?? storeDomain;
  return domain
    .split(/[-_]/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}
