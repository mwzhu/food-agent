"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Loader2, X } from "lucide-react";

import type { PaymentCredentials } from "@/lib/supplement-types";
import { cn } from "@/lib/utils";

const EMPTY_PAYMENT_CREDENTIALS: PaymentCredentials = {
  card_number: "",
  card_expiry: "",
  card_cvv: "",
  card_name: "",
};

type PaymentCredentialsModalProps = {
  errorMessage: string | null;
  open: boolean;
  saving: boolean;
  onClose: () => void;
  onSubmit: (payload: { payment_credentials: PaymentCredentials; simulate_success: boolean }) => Promise<void>;
};

export function PaymentCredentialsModal({
  errorMessage,
  open,
  saving,
  onClose,
  onSubmit,
}: PaymentCredentialsModalProps) {
  const [draft, setDraft] = useState<PaymentCredentials>(EMPTY_PAYMENT_CREDENTIALS);
  const [simulateSuccess, setSimulateSuccess] = useState(true);

  useEffect(() => {
    if (!open) {
      setDraft(EMPTY_PAYMENT_CREDENTIALS);
      setSimulateSuccess(true);
    }
  }, [open]);

  if (!open) {
    return null;
  }

  const handleClose = () => {
    setDraft(EMPTY_PAYMENT_CREDENTIALS);
    setSimulateSuccess(true);
    onClose();
  };

  const submit = async () => {
    await onSubmit({ payment_credentials: draft, simulate_success: simulateSuccess });
    setDraft(EMPTY_PAYMENT_CREDENTIALS);
    setSimulateSuccess(true);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/35 backdrop-blur-[1px]">
      <div className="grid min-h-full place-items-center px-4 py-8">
        <div className="w-full max-w-lg overflow-hidden rounded-[2rem] bg-[#FBFBFC] shadow-[0_24px_80px_rgba(0,0,0,0.22)]">
          <div className="flex items-center justify-between border-b border-black/8 px-5 py-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-black/42">Agent checkout</p>
              <h2 className="mt-1 text-[1.35rem] font-semibold tracking-tight text-black">
                Enter card details for this run
              </h2>
            </div>
            <button
              className="rounded-full p-2 text-black/55 transition-colors hover:bg-black/5 hover:text-black"
              onClick={handleClose}
              type="button"
            >
              <X className="size-5" strokeWidth={1.8} />
            </button>
          </div>

          <div className="space-y-5 px-5 py-5">
            <p className="rounded-2xl border border-black/8 bg-white px-4 py-3 text-sm leading-6 text-black/68">
              These card details are used only to drive the browser-agent checkout for this one run. They stay in
              local component state and are never persisted.
            </p>

            <label className="flex items-start gap-3 rounded-[1.4rem] border border-[#D7EAD9] bg-[#F5FBF6] px-4 py-3 text-sm text-[#235331]">
              <input
                checked={simulateSuccess}
                className="mt-1 h-4 w-4 rounded border-[#235331]/30"
                onChange={(event) => setSimulateSuccess(event.target.checked)}
                type="checkbox"
              />
              <span>
                <span className="block font-semibold">Demo mode: simulate payment success</span>
                <span className="mt-1 block leading-6 text-[#235331]/78">
                  The browser fills checkout up to the final payment step, stops before any real charge, then shows a
                  simulated confirmation in chat.
                </span>
              </span>
            </label>

            <div className="space-y-4 rounded-[1.6rem] border border-black/8 bg-white p-4">
              <Field label="Card number">
                <input
                  autoComplete="cc-number"
                  className={INPUT_CLASS}
                  inputMode="numeric"
                  onChange={(event) => setDraft((current) => ({ ...current, card_number: event.target.value }))}
                  placeholder="4242 4242 4242 4242"
                  value={draft.card_number}
                />
              </Field>

              <div className="grid gap-4 sm:grid-cols-[0.8fr_0.8fr]">
                <Field label="Expiry">
                  <input
                    autoComplete="cc-exp"
                    className={INPUT_CLASS}
                    inputMode="numeric"
                    onChange={(event) => setDraft((current) => ({ ...current, card_expiry: event.target.value }))}
                    placeholder="MM/YY"
                    value={draft.card_expiry}
                  />
                </Field>
                <Field label="CVV">
                  <input
                    autoComplete="cc-csc"
                    className={INPUT_CLASS}
                    inputMode="numeric"
                    onChange={(event) => setDraft((current) => ({ ...current, card_cvv: event.target.value }))}
                    placeholder="123"
                    value={draft.card_cvv}
                  />
                </Field>
              </div>

              <Field label="Name on card">
                <input
                  autoComplete="cc-name"
                  className={INPUT_CLASS}
                  onChange={(event) => setDraft((current) => ({ ...current, card_name: event.target.value }))}
                  placeholder="Full name"
                  value={draft.card_name}
                />
              </Field>
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
              onClick={handleClose}
              type="button"
            >
              Cancel
            </button>
            <button
              className={cn(
                "flex min-w-[188px] items-center justify-center gap-2 rounded-full bg-black px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-[#222]",
                saving && "opacity-80",
              )}
              disabled={saving}
              onClick={() => void submit()}
              type="button"
            >
              {saving ? <Loader2 className="size-4 animate-spin" strokeWidth={2} /> : null}
              Start agent checkout
            </button>
          </div>
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

const INPUT_CLASS =
  "h-11 w-full rounded-2xl border border-black/10 bg-[#FBFBFB] px-4 text-[15px] text-black outline-none transition-colors placeholder:text-black/28 focus:border-black/18 focus:bg-white";
