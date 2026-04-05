"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GroceryItem, PurchaseOrder, StoreQuote, StoreSummary } from "@/lib/types";
import { cn, formatCurrency, formatLabel, formatQuantity } from "@/lib/utils";

type PriceTableProps = {
  items: GroceryItem[];
  quotes: StoreQuote[];
  summaries: StoreSummary[];
  purchaseOrders: PurchaseOrder[];
};

export function PriceTable({ items, quotes, summaries, purchaseOrders }: PriceTableProps) {
  const pricedItems = items.filter((item) => !item.already_have && item.shopping_quantity > 0);
  const stores = summaries.length
    ? summaries.map((summary) => summary.store)
    : Array.from(new Set(quotes.map((quote) => quote.store))).sort();

  if (!pricedItems.length || !stores.length) {
    return null;
  }

  const quoteLookup = new Map(quotes.map((quote) => [`${quote.store}::${quote.item_name}`, quote] as const));
  const summaryLookup = new Map(summaries.map((summary) => [summary.store, summary] as const));
  const selectionLookup = new Map(
    purchaseOrders.flatMap((order) =>
      order.items.map((item) => [item.name, { store: order.store, channel: order.channel }] as const),
    ),
  );

  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Price comparison</p>
        <CardTitle>Store-by-store basket pricing</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto rounded-[1.25rem] border border-border bg-background/70">
          <table className="min-w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 border-b border-border bg-background/95 px-4 py-3 text-left font-semibold">
                  Item
                </th>
                {stores.map((store) => (
                  <th key={store} className="border-b border-border px-4 py-3 text-left font-semibold">
                    {store}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pricedItems.map((item) => {
                const inStockQuotes = stores
                  .map((store) => quoteLookup.get(`${store}::${item.name}`))
                  .filter((quote): quote is StoreQuote => Boolean(quote?.in_stock));
                const cheapestPrice = inStockQuotes.length
                  ? Math.min(...inStockQuotes.map((quote) => quote.price))
                  : null;

                return (
                  <tr key={item.name}>
                    <td className="sticky left-0 z-10 border-b border-border bg-background/95 px-4 py-4 align-top">
                      <div className="space-y-1">
                        <p className="font-medium text-foreground">{item.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatQuantity(item.shopping_quantity)}
                          {item.unit ? ` ${item.unit}` : ""} to buy
                        </p>
                      </div>
                    </td>
                    {stores.map((store) => {
                      const quote = quoteLookup.get(`${store}::${item.name}`);
                      const selection = selectionLookup.get(item.name);
                      const isSelected = selection?.store === store;
                      const isCheapest = quote?.in_stock && cheapestPrice !== null && Math.abs(quote.price - cheapestPrice) < 0.001;

                      return (
                        <td key={`${item.name}-${store}`} className="border-b border-border px-4 py-4 align-top">
                          {!quote ? (
                            <span className="text-muted-foreground">-</span>
                          ) : (
                            <div
                              className={cn(
                                "rounded-[1rem] border border-transparent p-3 transition-colors",
                                isCheapest && "border-success/30 bg-success-soft/60",
                                isSelected && "border-primary/35 bg-accent/55",
                                !quote.in_stock && "border-border bg-muted/50",
                              )}
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                {!quote.in_stock ? (
                                  <Badge variant="outline">Out of stock</Badge>
                                ) : (
                                  <Badge variant={isCheapest ? "success" : "secondary"}>
                                    {formatCurrency(quote.price, { minimumFractionDigits: 2 })}
                                  </Badge>
                                )}
                                {isSelected ? (
                                  <Badge variant="outline">
                                    {selection.channel === "online" ? "Buy online" : "Buy in store"}
                                  </Badge>
                                ) : null}
                              </div>
                              <p className="mt-2 text-xs text-muted-foreground">
                                {quote.in_stock
                                  ? `${formatCurrency(quote.unit_price, { minimumFractionDigits: 2 })} per ${
                                      quote.requested_unit ?? "item"
                                    }`
                                  : "No current stock"}
                              </p>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <td className="sticky left-0 z-10 bg-background/95 px-4 py-4 font-semibold text-foreground">
                  Store totals
                </td>
                {stores.map((store) => {
                  const summary = summaryLookup.get(store);
                  return (
                    <td key={`total-${store}`} className="px-4 py-4 align-top">
                      {summary ? (
                        <div className="rounded-[1rem] border border-border bg-card/80 p-3">
                          <p className="font-semibold text-foreground">
                            {formatCurrency(summary.total, { minimumFractionDigits: 2 })}
                          </p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            Subtotal {formatCurrency(summary.subtotal, { minimumFractionDigits: 2 })}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            Fee {formatCurrency(summary.delivery_fee, { minimumFractionDigits: 2 })}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <Badge variant={summary.all_items_available ? "success" : "outline"}>
                              {summary.available_item_count}/{summary.item_count} items
                            </Badge>
                            {!summary.meets_min_order ? (
                              <Badge variant="outline">Min {formatCurrency(summary.min_order)}</Badge>
                            ) : null}
                          </div>
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted-foreground">
          Green cells are the cheapest in-stock quote for that item. Highlighted badges show the currently recommended
          store and channel from the selected purchase plan.
        </p>
      </CardContent>
    </Card>
  );
}
