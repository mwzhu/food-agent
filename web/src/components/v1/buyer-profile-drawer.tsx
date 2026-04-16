"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Loader2, X } from "lucide-react";

import type {
  ShippingAddress,
  SupplementBuyerProfileRead,
  SupplementBuyerProfileUpsertRequest,
} from "@/lib/supplement-types";
import { cn } from "@/lib/utils";

const EMPTY_ADDRESS: ShippingAddress = {
  line1: "",
  line2: "",
  city: "",
  state: "",
  postal_code: "",
  country_code: "US",
};

type BuyerProfileDrawerProps = {
  defaultBudget: number;
  errorMessage: string | null;
  initialValue: SupplementBuyerProfileRead | null | undefined;
  open: boolean;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: SupplementBuyerProfileUpsertRequest) => Promise<void>;
};

export function BuyerProfileDrawer({
  defaultBudget,
  errorMessage,
  initialValue,
  open,
  saving,
  onClose,
  onSubmit,
}: BuyerProfileDrawerProps) {
  const [draft, setDraft] = useState<SupplementBuyerProfileUpsertRequest>(() =>
    createInitialDraft(initialValue, defaultBudget),
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setDraft(createInitialDraft(initialValue, defaultBudget));
  }, [defaultBudget, initialValue, open]);

  if (!open) {
    return null;
  }

  const submit = async () => {
    await onSubmit(draft);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/35 backdrop-blur-[1px]">
      <div className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col bg-[#FBFBFC] shadow-[0_24px_80px_rgba(0,0,0,0.22)]">
        <div className="flex items-center justify-between border-b border-black/8 px-5 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-black/42">Checkout setup</p>
            <h2 className="mt-1 text-[1.35rem] font-semibold tracking-tight text-black">
              Save shipping and spending guardrails
            </h2>
          </div>
          <button
            className="rounded-full p-2 text-black/55 transition-colors hover:bg-black/5 hover:text-black"
            onClick={onClose}
            type="button"
          >
            <X className="size-5" strokeWidth={1.8} />
          </button>
        </div>

        <div className="v1-scrollbar flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <p className="rounded-2xl border border-black/8 bg-white px-4 py-3 text-sm leading-6 text-black/68">
            I&apos;ll use this only for guided supplement checkout. Payment credentials stay with the merchant.
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Email">
              <input
                className={INPUT_CLASS}
                onChange={(event) => setDraft((current) => ({ ...current, email: event.target.value }))}
                placeholder="name@example.com"
                value={draft.email ?? ""}
              />
            </Field>
            <Field label="Shipping name">
              <input
                className={INPUT_CLASS}
                onChange={(event) => setDraft((current) => ({ ...current, shipping_name: event.target.value }))}
                placeholder="Full name"
                value={draft.shipping_name ?? ""}
              />
            </Field>
          </div>

          <div className="space-y-4 rounded-[1.6rem] border border-black/8 bg-white p-4">
            <div className="grid gap-4">
              <Field label="Address line 1">
                <input
                  className={INPUT_CLASS}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      shipping_address: { ...current.shipping_address, line1: event.target.value },
                    }))
                  }
                  placeholder="Street address"
                  value={draft.shipping_address.line1 ?? ""}
                />
              </Field>
              <Field label="Address line 2">
                <input
                  className={INPUT_CLASS}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      shipping_address: { ...current.shipping_address, line2: event.target.value },
                    }))
                  }
                  placeholder="Apartment, suite, etc."
                  value={draft.shipping_address.line2 ?? ""}
                />
              </Field>
            </div>

            <div className="grid gap-4 sm:grid-cols-[1.5fr_0.8fr_0.9fr]">
              <Field label="City">
                <input
                  className={INPUT_CLASS}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      shipping_address: { ...current.shipping_address, city: event.target.value },
                    }))
                  }
                  value={draft.shipping_address.city ?? ""}
                />
              </Field>
              <Field label="State">
                <input
                  className={INPUT_CLASS}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      shipping_address: { ...current.shipping_address, state: event.target.value },
                    }))
                  }
                  value={draft.shipping_address.state ?? ""}
                />
              </Field>
              <Field label="ZIP">
                <input
                  className={INPUT_CLASS}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      shipping_address: { ...current.shipping_address, postal_code: event.target.value },
                    }))
                  }
                  value={draft.shipping_address.postal_code ?? ""}
                />
              </Field>
            </div>
          </div>

          <div className="rounded-[1.6rem] border border-black/8 bg-white p-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Max order total">
                <input
                  className={INPUT_CLASS}
                  inputMode="decimal"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      max_order_total: parseOptionalNumber(event.target.value),
                    }))
                  }
                  placeholder={String(defaultBudget)}
                  value={draft.max_order_total ?? ""}
                />
              </Field>
              <Field label="Max monthly total">
                <input
                  className={INPUT_CLASS}
                  inputMode="decimal"
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      max_monthly_total: parseOptionalNumber(event.target.value),
                    }))
                  }
                  placeholder={String(defaultBudget * 2)}
                  value={draft.max_monthly_total ?? ""}
                />
              </Field>
            </div>

            <label className="mt-4 flex items-start gap-3 rounded-2xl border border-black/8 bg-[#F8F8F8] px-3 py-3 text-sm text-black/72">
              <input
                checked={draft.consent_granted}
                className="mt-1 h-4 w-4 rounded border-black/20"
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    consent_granted: event.target.checked,
                  }))
                }
                type="checkbox"
              />
              <span>
                I approve Shopper to prepare merchant checkout sessions and continue only within the guardrails above.
              </span>
            </label>
          </div>

          {errorMessage ? (
            <p className="rounded-2xl border border-[#F3C5C5] bg-[#FFF3F3] px-4 py-3 text-sm text-[#B32F2F]">
              {errorMessage}
            </p>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-black/8 px-5 py-4">
          <button
            className="rounded-full border border-black/12 px-4 py-2 text-sm font-medium text-black/72 transition-colors hover:bg-black/4"
            onClick={onClose}
            type="button"
          >
            Not now
          </button>
          <button
            className={cn(
              "flex min-w-[164px] items-center justify-center gap-2 rounded-full bg-black px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#222]",
              saving && "opacity-80",
            )}
            disabled={saving}
            onClick={() => void submit()}
            type="button"
          >
            {saving ? <Loader2 className="size-4 animate-spin" strokeWidth={2} /> : null}
            Save and continue
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ children, label }: { children: ReactNode; label: string }) {
  return (
    <label className="block">
      <span className="mb-2 block text-[12px] font-medium uppercase tracking-[0.16em] text-black/42">{label}</span>
      {children}
    </label>
  );
}

function createInitialDraft(
  initialValue: SupplementBuyerProfileRead | null | undefined,
  defaultBudget: number,
): SupplementBuyerProfileUpsertRequest {
  return {
    email: initialValue?.email ?? "",
    shipping_name: initialValue?.shipping_name ?? "",
    shipping_address: initialValue?.shipping_address ?? EMPTY_ADDRESS,
    billing_same_as_shipping: initialValue?.billing_same_as_shipping ?? true,
    billing_country: initialValue?.billing_country ?? "US",
    consent_granted: initialValue?.consent_granted ?? false,
    autopurchase_enabled: initialValue?.autopurchase_enabled ?? false,
    max_order_total: initialValue?.max_order_total ?? defaultBudget,
    max_monthly_total: initialValue?.max_monthly_total ?? defaultBudget * 2,
    shop_pay_linked: initialValue?.shop_pay_linked ?? false,
    shop_pay_last_verified_at: initialValue?.shop_pay_last_verified_at ?? null,
    last_payment_authorization_at: initialValue?.last_payment_authorization_at ?? null,
    consent_version: initialValue?.consent_version ?? "v1",
  };
}

function parseOptionalNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

const INPUT_CLASS =
  "h-11 w-full rounded-2xl border border-black/10 bg-[#FBFBFB] px-4 text-[15px] text-black outline-none transition-colors placeholder:text-black/28 focus:border-black/18 focus:bg-white";
