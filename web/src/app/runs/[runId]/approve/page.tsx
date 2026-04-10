"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { ApprovalGate } from "@/components/checkout/approval-gate";
import { CartReview } from "@/components/checkout/cart-review";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRun } from "@/hooks/use-run";

export default function CheckoutApprovalPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const runQuery = useRun(runId, true);

  if (runQuery.isLoading || !runQuery.data) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading checkout review...</p>
      </section>
    );
  }

  const run = runQuery.data;
  const order = run.state_snapshot.purchase_orders[0];

  if (!order) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No checkout order was found for this run.</CardTitle>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href={`/runs/${runId}`}>Back to run</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Checkout approval</p>
          <CardTitle className="text-4xl md:text-5xl">Review cart before purchase</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button asChild size="sm" variant="ghost">
            <Link href={`/runs/${runId}`}>Back to run</Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <a href={order.cart_url ?? order.store_url} rel="noreferrer" target="_blank">
              Open cart
            </a>
          </Button>
        </CardContent>
      </Card>

      <CartReview order={order} />
      <ApprovalGate runId={runId} />
    </section>
  );
}
