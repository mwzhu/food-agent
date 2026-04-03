"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { GroceryItem } from "@/lib/types";
import { cn, formatLabel, formatQuantity, groupGroceryItemsByCategory } from "@/lib/utils";

type GroceryListProps = {
  items: GroceryItem[];
};

export function GroceryList({ items }: GroceryListProps) {
  const groupedItems = groupGroceryItemsByCategory(items).filter((group) => group.items.length > 0);
  const alreadyOwnedCount = items.filter((item) => item.already_have).length;
  const itemsToBuyCount = items.length - alreadyOwnedCount;

  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Grocery list</p>
        <CardTitle>Fridge-aware shopping breakdown</CardTitle>
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{itemsToBuyCount} to buy</Badge>
          <Badge variant="outline">{alreadyOwnedCount} already in fridge</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {groupedItems.map((group) => (
          <section key={group.category} className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-semibold">{formatLabel(group.category)}</h3>
              <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                {group.items.length} item{group.items.length === 1 ? "" : "s"}
              </span>
            </div>

            <div className="grid gap-3">
              {group.items.map((item) => {
                const displayQuantity = item.already_have ? item.quantity : item.shopping_quantity || item.quantity;
                return (
                  <article
                    key={`${group.category}-${item.name}`}
                    className={cn(
                      "rounded-[1.25rem] border border-border bg-background/75 p-4 transition-colors",
                      item.already_have && "border-success/30 bg-success-soft/40",
                    )}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-2">
                        <p
                          className={cn(
                            "font-medium text-foreground",
                            item.already_have && "text-muted-foreground line-through",
                          )}
                        >
                          {item.name}
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {item.already_have ? <Badge variant="success">In fridge</Badge> : null}
                          {item.quantity_in_fridge > 0 && !item.already_have ? (
                            <Badge variant="outline">
                              Using {formatQuantity(item.quantity_in_fridge)}
                              {item.unit ? ` ${item.unit}` : ""} from fridge
                            </Badge>
                          ) : null}
                        </div>
                      </div>

                      <div className="text-right text-sm text-muted-foreground">
                        <p className="font-semibold text-foreground">
                          {formatQuantity(displayQuantity)}
                          {item.unit ? ` ${item.unit}` : ""}
                        </p>
                        {item.already_have ? (
                          <p>Needed for plan</p>
                        ) : (
                          <p>
                            {formatQuantity(item.quantity)}
                            {item.unit ? ` ${item.unit}` : ""} total
                          </p>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </CardContent>
    </Card>
  );
}
