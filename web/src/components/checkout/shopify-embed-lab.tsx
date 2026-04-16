"use client";

import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Loader2, ShieldOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { runSupplementCheckoutEmbedSpike } from "@/lib/api";
import type { SupplementCheckoutEmbedSpikeRead, SupplementCheckoutEmbedSpikeRequest } from "@/lib/supplement-types";

const DEFAULT_PROBES: Array<{ label: string; store_domain: string; query: string }> = [
  {
    label: "Transparent Labs",
    store_domain: "transparentlabs.com",
    query: "creatine hmb",
  },
  {
    label: "Momentous",
    store_domain: "livemomentous.com",
    query: "magnesium l-threonate",
  },
];

type FrameStatus = "idle" | "loading" | "loaded" | "timed_out";

export function ShopifyEmbedLab() {
  const [probe, setProbe] = useState<SupplementCheckoutEmbedSpikeRequest>(DEFAULT_PROBES[0]);
  const [result, setResult] = useState<SupplementCheckoutEmbedSpikeRead | null>(null);
  const [desktopFrameStatus, setDesktopFrameStatus] = useState<FrameStatus>("idle");
  const [mobileFrameStatus, setMobileFrameStatus] = useState<FrameStatus>("idle");

  const spikeMutation = useMutation({
    mutationFn: (payload: SupplementCheckoutEmbedSpikeRequest) => runSupplementCheckoutEmbedSpike(payload),
    onSuccess: (nextResult) => {
      setResult(nextResult);
      setDesktopFrameStatus(nextResult.checkout_url ? "loading" : "idle");
      setMobileFrameStatus(nextResult.checkout_url ? "loading" : "idle");
    },
  });

  useEffect(() => {
    if (!result?.checkout_url) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setDesktopFrameStatus((current) => (current === "loaded" ? current : "timed_out"));
      setMobileFrameStatus((current) => (current === "loaded" ? current : "timed_out"));
    }, 4500);
    return () => window.clearTimeout(timeoutId);
  }, [result]);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Phase 0 spike</p>
          <CardTitle>Shopify embed validation</CardTitle>
          <CardDescription className="max-w-3xl text-base">
            Generate a live Shopify checkout URL, inspect the merchant&apos;s real embed headers, and then attempt the
            iframe in desktop and mobile viewports from the same page.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-3">
            {DEFAULT_PROBES.map((candidate) => {
              const active =
                probe.store_domain === candidate.store_domain && probe.query === candidate.query;
              return (
                <Button
                  key={candidate.store_domain}
                  onClick={() => setProbe({ store_domain: candidate.store_domain, query: candidate.query })}
                  type="button"
                  variant={active ? "default" : "outline"}
                >
                  {candidate.label}
                </Button>
              );
            })}
            <Button
              disabled={spikeMutation.isPending}
              onClick={() => spikeMutation.mutate(probe)}
              type="button"
            >
              {spikeMutation.isPending ? "Running spike..." : "Run live merchant probe"}
            </Button>
          </div>

          {spikeMutation.error ? (
            <p className="text-sm font-medium text-destructive">
              {spikeMutation.error instanceof Error ? spikeMutation.error.message : "Could not run the embed spike."}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {result ? (
        <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <Card>
            <CardHeader>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Verdict</p>
              <CardTitle className="flex items-center gap-2">
                {result.iframe_allowed ? null : <ShieldOff className="size-5 text-destructive" strokeWidth={1.8} />}
                {result.iframe_allowed ? "Iframe allowed" : "Iframe blocked"}
              </CardTitle>
              <CardDescription>
                {result.block_reason ??
                  "The merchant response does not currently advertise an iframe block for Shopper origins."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <SummaryRow label="Merchant" value={result.store_domain} />
              <SummaryRow label="Query" value={result.query} />
              <SummaryRow label="Product" value={result.selected_product_title ?? "Unavailable"} />
              <SummaryRow label="HTTP status" value={result.status_code !== null ? String(result.status_code) : "Unknown"} />
              <SummaryRow label="X-Frame-Options" value={result.x_frame_options ?? "Not set"} />
              <SummaryRow
                label="frame-ancestors"
                value={result.frame_ancestors.length ? result.frame_ancestors.join(", ") : "Not set"}
              />
              <SummaryRow
                label="Allowed Shopper origins"
                value={result.allowed_embed_origins.length ? result.allowed_embed_origins.join(", ") : "None configured"}
              />
              <SummaryRow label="Final URL" value={result.final_url ?? "Unavailable"} />

              {result.checkout_url ? (
                <div className="flex flex-wrap gap-3 pt-2">
                  <Button asChild type="button" variant="outline">
                    <a href={result.checkout_url} rel="noreferrer" target="_blank">
                      <ExternalLink className="mr-2 size-4" strokeWidth={1.9} />
                      Open checkout fallback
                    </a>
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <PreviewCard
              checkoutUrl={result.checkout_url}
              description="Desktop-sized iframe surface"
              heightClassName="h-[520px]"
              onLoad={() => setDesktopFrameStatus("loaded")}
              status={desktopFrameStatus}
              title="Desktop preview"
              widthClassName="w-full"
            />
            <PreviewCard
              checkoutUrl={result.checkout_url}
              description="Mobile-sized constrained viewport"
              heightClassName="h-[640px]"
              onLoad={() => setMobileFrameStatus("loaded")}
              status={mobileFrameStatus}
              title="Mobile preview"
              widthClassName="mx-auto w-[390px] max-w-full"
            />
          </div>
        </div>
      ) : null}

      {result && !result.iframe_allowed ? (
        <Card className="border-amber-300 bg-amber-50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-amber-900">
              <AlertTriangle className="size-5" strokeWidth={1.8} />
              Recommendation
            </CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-amber-900/90">
            Default `SHOPIFY_CHECKOUT_EMBED_MODE=auto` should degrade to a controlled external handoff for this
            merchant. The header probe says the live checkout does not allow Shopper origins in `frame-ancestors`.
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.1rem] border border-border bg-background/70 px-4 py-3">
      <p className="text-[0.7rem] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className="mt-1 break-words font-medium text-foreground">{value}</p>
    </div>
  );
}

function PreviewCard({
  checkoutUrl,
  description,
  heightClassName,
  onLoad,
  status,
  title,
  widthClassName,
}: {
  checkoutUrl: string | null;
  description: string;
  heightClassName: string;
  onLoad: () => void;
  status: FrameStatus;
  title: string;
  widthClassName: string;
}) {
  const statusLabel =
    status === "loaded"
      ? "iframe load event fired"
      : status === "timed_out"
        ? "iframe timed out"
        : status === "loading"
          ? "attempting iframe load"
          : "waiting for a checkout URL";

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="rounded-full bg-muted px-3 py-2 text-xs font-medium text-muted-foreground">{statusLabel}</div>
        <div className={`overflow-hidden rounded-[1.5rem] border border-border bg-muted/40 ${widthClassName}`}>
          <div className={`relative ${heightClassName} bg-background`}>
            {checkoutUrl ? (
              <>
                {status === "loading" ? (
                  <div className="absolute inset-0 z-10 grid place-items-center bg-background/85 text-sm text-muted-foreground">
                    <div className="flex items-center gap-2">
                      <Loader2 className="size-4 animate-spin" strokeWidth={2} />
                      Attempting iframe load
                    </div>
                  </div>
                ) : null}
                <iframe
                  className="h-full w-full bg-white"
                  onLoad={onLoad}
                  src={checkoutUrl}
                  title={title}
                />
              </>
            ) : (
              <div className="grid h-full place-items-center text-sm text-muted-foreground">Run the spike first</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
