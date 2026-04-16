"use client";

type PaymentSetupBannerProps = {
  onOpenBuyerProfile: () => void;
};

export function PaymentSetupBanner({ onOpenBuyerProfile }: PaymentSetupBannerProps) {
  return (
    <div className="rounded-[1.5rem] border border-[#E8D7B7] bg-[#FFF9EE] px-4 py-4 text-sm text-[#6B4B10]">
      <p className="font-medium text-[#4B3410]">Before I buy, I need your shipping details and spending caps.</p>
      <p className="mt-1 leading-6">
        The order flow stays in Shopper when possible, but I still need the buyer setup you want me to use.
      </p>
      <button
        className="mt-3 rounded-full bg-[#4B3410] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#5B4015]"
        onClick={onOpenBuyerProfile}
        type="button"
      >
        Add buyer setup
      </button>
    </div>
  );
}
