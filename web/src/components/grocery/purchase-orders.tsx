"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PurchaseOrder } from "@/lib/types";
import { formatCurrency, formatLabel, formatQuantity } from "@/lib/utils";

type PurchaseOrdersProps = {
  orders: PurchaseOrder[];
  strategy: string | null;
  rationale: string | null;
};

export function PurchaseOrders({ orders, strategy, rationale }: PurchaseOrdersProps) {
  if (!orders.length) {
    return null;
  }

  const combinedTotal = orders.reduce((sum, order) => sum + order.total_cost, 0);

  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Purchase orders</p>
        <CardTitle>Recommended store split</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{orders.length} order{orders.length === 1 ? "" : "s"}</Badge>
          <Badge variant="success">{formatCurrency(combinedTotal, { minimumFractionDigits: 2 })} total</Badge>
          {strategy ? <Badge variant="outline">{formatLabel(strategy)}</Badge> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {rationale ? <p className="text-sm leading-6 text-muted-foreground">{rationale}</p> : null}

        <div className="grid gap-4 lg:grid-cols-2">
          {orders.map((order) => (
            <article key={`${order.store}-${order.channel}`} className="rounded-[1.25rem] border border-border bg-background/75 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-foreground">{order.store}</h3>
                  <p className="text-sm text-muted-foreground">
                    {order.items.length} item{order.items.length === 1 ? "" : "s"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge variant={order.channel === "online" ? "secondary" : "outline"}>
                    {order.channel === "online" ? "Buy online" : "Buy in store"}
                  </Badge>
                  <Badge variant={order.status === "pending" ? "outline" : "success"}>{formatLabel(order.status)}</Badge>
                </div>
              </div>

              <div className="mt-4 grid gap-2 text-sm text-muted-foreground">
                {order.items.map((item) => (
                  <div key={item.name} className="flex items-center justify-between gap-3">
                    <span className="truncate">
                      {item.name} · {formatQuantity(item.quantity)}
                      {item.unit ? ` ${item.unit}` : ""}
                    </span>
                    <strong className="text-foreground">
                      {formatCurrency(item.price, { minimumFractionDigits: 2 })}
                    </strong>
                  </div>
                ))}
              </div>

              <div className="mt-4 space-y-1 border-t border-border pt-4 text-sm text-muted-foreground">
                <div className="flex items-center justify-between">
                  <span>Subtotal</span>
                  <strong className="text-foreground">
                    {formatCurrency(order.subtotal, { minimumFractionDigits: 2 })}
                  </strong>
                </div>
                <div className="flex items-center justify-between">
                  <span>Delivery fee</span>
                  <strong className="text-foreground">
                    {formatCurrency(order.delivery_fee, { minimumFractionDigits: 2 })}
                  </strong>
                </div>
                <div className="flex items-center justify-between text-base">
                  <span>Total</span>
                  <strong className="text-foreground">
                    {formatCurrency(order.total_cost, { minimumFractionDigits: 2 })}
                  </strong>
                </div>
              </div>
            </article>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
