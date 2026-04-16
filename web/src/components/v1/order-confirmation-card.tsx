"use client";

import type { SupplementOrderConfirmation } from "@/lib/supplement-types";
import { formatMoney } from "@/lib/utils";

type OrderConfirmationCardProps = {
  confirmation: SupplementOrderConfirmation;
};

export function OrderConfirmationCard({ confirmation }: OrderConfirmationCardProps) {
  const linkUrl = confirmation.confirmation_url ?? storeHomeUrl(confirmation.store_domain);
  const linkLabel = confirmation.confirmation_url ? "View merchant receipt" : "Open store";

  return (
    <div className="rounded-[1.5rem] border border-[#D7EAD9] bg-[#F5FBF6] px-4 py-4 text-sm text-[#235331]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">Order placed with {formatStoreName(confirmation.store_domain)}</p>
          <p className="mt-1 leading-6">{confirmation.message}</p>
        </div>
        <a
          className="rounded-full border border-[#235331]/18 bg-white/80 px-3 py-1.5 text-[13px] font-semibold text-[#235331] transition-colors hover:bg-white"
          href={linkUrl}
          rel="noreferrer"
          target="_blank"
        >
          {linkLabel}
        </a>
      </div>

      {confirmation.line_items.length ? (
        <div className="mt-4 rounded-[1.1rem] border border-[#D7EAD9] bg-white/62 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#235331]/58">Items</p>
          <div className="mt-2 space-y-2">
            {confirmation.line_items.map((item, index) => (
              <div
                className="flex items-start justify-between gap-3 text-[13px] leading-5 text-[#235331]/86"
                key={`${item.title}:${item.variant_title ?? ""}:${index}`}
              >
                <div>
                  <p className="font-medium text-[#235331]">
                    {item.quantity}x {item.title}
                  </p>
                  {item.variant_title ? <p className="text-[#235331]/62">{item.variant_title}</p> : null}
                </div>
                {item.total_amount !== null ? (
                  <span className="shrink-0 font-medium">
                    {formatMoney(item.total_amount, item.currency ?? confirmation.currency ?? "USD")}
                  </span>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-3 text-[13px] text-[#235331]/80">
        <span>{new Date(confirmation.placed_at).toLocaleString()}</span>
        {confirmation.order_total !== null ? (
          <span>{formatMoney(confirmation.order_total, confirmation.currency ?? "USD")}</span>
        ) : null}
        <span>{confirmation.confirmation_id}</span>
      </div>
    </div>
  );
}

function formatStoreName(storeDomain: string) {
  const domain = storeDomain.replace(/^www\./, "").split(".")[0] ?? storeDomain;
  return domain
    .split(/[-_]/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function storeHomeUrl(storeDomain: string) {
  return `https://www.${storeDomain.replace(/^www\./, "")}`;
}
