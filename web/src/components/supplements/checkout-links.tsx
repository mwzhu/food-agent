"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useApproveSupplementRun } from "@/hooks/use-supplement-run";
import type { StoreCart, SupplementRunLifecycleStatus } from "@/lib/supplement-types";
import { formatMoney } from "@/lib/utils";

type CheckoutLinksProps = {
  runId: string;
  runStatus: SupplementRunLifecycleStatus;
  storeCarts: StoreCart[];
  approvedStoreDomains: string[];
};

export function CheckoutLinks({
  runId,
  runStatus,
  storeCarts,
  approvedStoreDomains,
}: CheckoutLinksProps) {
  const approveMutation = useApproveSupplementRun();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedStoreDomains, setSelectedStoreDomains] = useState<string[]>([]);

  const readyCarts = storeCarts
    .filter((cart) => Boolean(cart.checkout_url))
    .slice()
    .sort((left, right) => left.store_domain.localeCompare(right.store_domain));
  const issueCarts = storeCarts
    .filter((cart) => !cart.checkout_url || cart.errors.length > 0)
    .slice()
    .sort((left, right) => left.store_domain.localeCompare(right.store_domain));
  const approvedSet = new Set(approvedStoreDomains);
  const readyDomainsKey = readyCarts.map((cart) => cart.store_domain).join("|");
  const approvedDomainsKey = approvedStoreDomains.join("|");

  useEffect(() => {
    if (!readyCarts.length) {
      setSelectedStoreDomains([]);
      return;
    }

    if (approvedStoreDomains.length) {
      setSelectedStoreDomains(approvedStoreDomains);
      return;
    }

    setSelectedStoreDomains(readyCarts.map((cart) => cart.store_domain));
  }, [approvedDomainsKey, readyDomainsKey]);

  const toggleStoreDomain = (storeDomain: string) => {
    setSelectedStoreDomains((current) =>
      current.includes(storeDomain)
        ? current.filter((domain) => domain !== storeDomain)
        : [...current, storeDomain],
    );
  };

  const approveSelectedStores = async () => {
    setErrorMessage(null);

    try {
      await approveMutation.mutateAsync({
        runId,
        payload: {
          approved_store_domains: selectedStoreDomains,
        },
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not approve the selected stores.");
    }
  };

  if (!storeCarts.length) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Checkout
          </p>
          <CardTitle>Store checkout links</CardTitle>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            Review the prebuilt Shopify carts, choose which stores to approve, then jump into the live checkout URLs.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={runStatus === "completed" ? "success" : "secondary"}>
            {readyCarts.length} ready stores
          </Badge>
          {approvedStoreDomains.length ? (
            <Badge variant="outline">{approvedStoreDomains.length} approved</Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {runStatus === "awaiting_approval" ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.3rem] border border-border bg-background/75 p-4">
            <p className="text-sm text-muted-foreground">
              Select at least one store to finish the run and keep only the checkout links you want to use.
            </p>
            <Button
              disabled={!selectedStoreDomains.length || approveMutation.isPending}
              onClick={() => void approveSelectedStores()}
              type="button"
            >
              {approveMutation.isPending ? "Approving..." : "Approve selected stores"}
            </Button>
          </div>
        ) : null}

        {errorMessage ? (
          <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-2">
          {readyCarts.map((cart) => {
            const isApproved = approvedSet.has(cart.store_domain);
            const amount = cart.total_amount ?? cart.subtotal_amount;
            const currency = cart.currency || "USD";

            return (
              <article
                key={cart.store_domain}
                className="rounded-[1.5rem] border border-border bg-background/75 p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display text-2xl leading-tight">{cart.store_domain}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {cart.lines.length} cart line{cart.lines.length === 1 ? "" : "s"} · {cart.total_quantity} total item
                      {cart.total_quantity === 1 ? "" : "s"}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {runStatus === "awaiting_approval" ? (
                      <label className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 px-3 py-2 text-xs font-semibold text-foreground">
                        <input
                          checked={selectedStoreDomains.includes(cart.store_domain)}
                          className="h-4 w-4 accent-[var(--primary)]"
                          onChange={() => toggleStoreDomain(cart.store_domain)}
                          type="checkbox"
                        />
                        Approve
                      </label>
                    ) : null}
                    {isApproved ? <Badge variant="success">Approved</Badge> : null}
                    {!isApproved && runStatus === "completed" ? <Badge variant="outline">Not approved</Badge> : null}
                  </div>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <Metric label="Cart total" value={amount !== null ? formatMoney(amount, currency) : "Unknown"} />
                  <Metric label="Cart id" value={cart.cart_id ?? "Pending"} />
                </div>

                <div className="mt-4 space-y-2">
                  {cart.lines.map((line) => (
                    <div
                      key={`${cart.store_domain}-${line.line_id || line.variant_id}`}
                      className="rounded-[1.1rem] border border-border/70 bg-card/60 p-3"
                    >
                      <p className="text-sm font-medium text-foreground">{line.product_title}</p>
                      <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                        Qty {line.quantity}
                        {line.variant_title ? ` · ${line.variant_title}` : ""}
                      </p>
                    </div>
                  ))}
                </div>

                {cart.instructions ? (
                  <p className="mt-4 text-sm leading-6 text-muted-foreground">{cart.instructions}</p>
                ) : null}

                <div className="mt-5">
                  <Button asChild size="sm" variant={isApproved ? "default" : "outline"}>
                    <a href={cart.checkout_url || "#"} rel="noreferrer" target="_blank">
                      Open checkout
                    </a>
                  </Button>
                </div>
              </article>
            );
          })}
        </div>

        {issueCarts.length ? (
          <div className="space-y-3">
            <p className="text-sm font-semibold text-foreground">Store issues</p>
            {issueCarts.map((cart) => (
              <article
                key={`${cart.store_domain}-issues`}
                className="rounded-[1.3rem] border border-border bg-card/70 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <strong>{cart.store_domain}</strong>
                  {!cart.checkout_url ? <Badge variant="outline">No checkout URL</Badge> : null}
                </div>
                {cart.errors.length ? (
                  <ul className="mt-3 space-y-2 text-sm leading-6 text-accent-foreground">
                    {cart.errors.map((error, index) => (
                      <li key={`${cart.store_domain}-error-${index}`}>
                        {String(error.message ?? "Unknown cart issue.")}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-muted-foreground">
                    This store did not return a checkout-ready cart.
                  </p>
                )}
              </article>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] border border-border/70 bg-card/60 p-3">
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-2 text-sm font-medium text-foreground">{value}</p>
    </div>
  );
}
