"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PurchaseOrder } from "@/lib/types";

type CartReviewProps = {
  order: PurchaseOrder;
};

export function CartReview({ order }: CartReviewProps) {
  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Checkout review</p>
        <CardTitle>{order.store}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Order status: {order.status.replaceAll("_", " ")}</p>
          {order.failure_reason ? <p className="mt-2">{order.failure_reason}</p> : null}
        </div>

        <div className="overflow-hidden rounded-[1.25rem] border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/60 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Item</th>
                <th className="px-4 py-3 font-medium">Qty</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Unit price</th>
                <th className="px-4 py-3 font-medium">Line</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item) => (
                <tr key={`${item.requested_name}-${item.actual_name}`} className="border-t border-border/70">
                  <td className="px-4 py-3">
                    <div className="font-medium text-foreground">{item.actual_name}</div>
                    {item.notes ? <div className="text-xs text-muted-foreground">{item.notes}</div> : null}
                  </td>
                  <td className="px-4 py-3">{item.actual_quantity}</td>
                  <td className="px-4 py-3 capitalize">{item.status.replaceAll("_", " ")}</td>
                  <td className="px-4 py-3">${item.unit_price.toFixed(2)}</td>
                  <td className="px-4 py-3">${item.line_total.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <SummaryMetric label="Subtotal" value={`$${order.subtotal.toFixed(2)}`} />
          <SummaryMetric label="Delivery fee" value={`$${order.delivery_fee.toFixed(2)}`} />
          <SummaryMetric label="Total" value={`$${order.total_cost.toFixed(2)}`} />
        </div>

        <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">
            Verification {order.verification?.passed ? "passed" : "needs review"}
          </p>
          {order.verification?.discrepancies.length ? (
            <ul className="mt-2 space-y-1">
              {order.verification.discrepancies.map((discrepancy) => (
                <li key={`${discrepancy.code}-${discrepancy.item_name ?? discrepancy.message}`}>
                  {discrepancy.message}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2">No discrepancies were recorded for this cart.</p>
          )}
        </div>

        {order.cart_screenshot_path?.startsWith("http") ? (
          <div className="space-y-2">
            <p className="text-sm font-medium text-foreground">Latest cart screenshot</p>
            <img
              alt="Cart screenshot"
              className="w-full rounded-[1.25rem] border border-border object-cover"
              src={order.cart_screenshot_path}
            />
          </div>
        ) : order.cart_screenshot_path ? (
          <div className="rounded-[1.25rem] border border-border bg-background/70 p-4 text-sm text-muted-foreground">
            Screenshot saved at <span className="font-mono text-foreground">{order.cart_screenshot_path}</span>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.25rem] border border-border bg-background/70 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <strong className="mt-1 block text-xl text-foreground">{value}</strong>
    </div>
  );
}
