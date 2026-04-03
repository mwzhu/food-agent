"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAddInventoryItem, useDeleteInventoryItem, useInventory } from "@/hooks/use-inventory";
import type { FridgeItemCreate, FridgeItemRead, InventoryCategory } from "@/lib/types";
import { cn, formatDate, formatLabel, formatQuantity, inventoryExpiryTone } from "@/lib/utils";

const CATEGORY_OPTIONS: Array<{ value: InventoryCategory; label: string }> = [
  { value: "produce", label: "Produce" },
  { value: "dairy", label: "Dairy" },
  { value: "meat", label: "Meat" },
  { value: "pantry", label: "Pantry" },
  { value: "frozen", label: "Frozen" },
];

const EMPTY_FORM: FridgeItemCreate = {
  name: "",
  quantity: 1,
  unit: "",
  category: "produce",
  expiry_date: "",
};

type InventoryManagerProps = {
  userId: string;
};

export function InventoryManager({ userId }: InventoryManagerProps) {
  const inventoryQuery = useInventory(userId);
  const addItemMutation = useAddInventoryItem(userId);
  const deleteItemMutation = useDeleteInventoryItem(userId);
  const [activeFilter, setActiveFilter] = useState<"all" | InventoryCategory>("all");
  const [formState, setFormState] = useState<FridgeItemCreate>(EMPTY_FORM);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const items = inventoryQuery.data ?? [];
  const filteredItems = useMemo(
    () => items.filter((item) => activeFilter === "all" || item.category === activeFilter),
    [activeFilter, items],
  );

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage(null);

    try {
      await addItemMutation.mutateAsync({
        ...formState,
        name: formState.name.trim(),
        unit: formState.unit?.trim() || null,
        expiry_date: formState.expiry_date || null,
      });
      setFormState(EMPTY_FORM);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not add that fridge item.");
    }
  };

  const removeItem = async (item: FridgeItemRead) => {
    if (!window.confirm(`Remove ${item.name} from the fridge inventory?`)) {
      return;
    }
    setErrorMessage(null);
    try {
      await deleteItemMutation.mutateAsync(item.item_id);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not delete that fridge item.");
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Add item</p>
          <CardTitle>Keep the planner honest about what you already have</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 md:grid-cols-2 xl:grid-cols-[1.4fr_0.7fr_0.7fr_0.9fr_0.9fr_auto]" onSubmit={onSubmit}>
            <Input
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
              placeholder="Greek yogurt"
              required
              value={formState.name}
            />
            <Input
              min="0.1"
              onChange={(event) =>
                setFormState((current) => ({ ...current, quantity: Number(event.target.value) || 0 }))
              }
              required
              step="0.1"
              type="number"
              value={formState.quantity}
            />
            <Input
              onChange={(event) => setFormState((current) => ({ ...current, unit: event.target.value }))}
              placeholder="cup"
              value={formState.unit ?? ""}
            />
            <select
              className="flex h-12 w-full rounded-3xl border border-border bg-background/80 px-4 py-3 text-sm text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] outline-none focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/15"
              onChange={(event) =>
                setFormState((current) => ({
                  ...current,
                  category: event.target.value as InventoryCategory,
                }))
              }
              value={formState.category}
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <Input
              onChange={(event) => setFormState((current) => ({ ...current, expiry_date: event.target.value }))}
              type="date"
              value={formState.expiry_date ?? ""}
            />
            <Button disabled={addItemMutation.isPending} type="submit">
              {addItemMutation.isPending ? "Saving..." : "Add item"}
            </Button>
          </form>
          {errorMessage ? <p className="mt-3 text-sm font-medium text-accent-foreground">{errorMessage}</p> : null}
        </CardContent>
      </Card>

      <Tabs onValueChange={(value) => setActiveFilter(value as "all" | InventoryCategory)} value={activeFilter}>
        <TabsList className="grid-cols-3 md:grid-cols-6">
          <TabsTrigger value="all">All</TabsTrigger>
          {CATEGORY_OPTIONS.map((option) => (
            <TabsTrigger key={option.value} value={option.value}>
              {option.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={activeFilter}>
          <Card>
            <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Fridge inventory</p>
                <CardTitle>
                  {inventoryQuery.isLoading ? "Loading items..." : `${filteredItems.length} tracked items`}
                </CardTitle>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="secondary">{items.length} total</Badge>
                <Badge variant="outline">{formatLabel(activeFilter === "all" ? "all categories" : activeFilter)}</Badge>
              </div>
            </CardHeader>
            <CardContent>
              {inventoryQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">Loading fridge inventory...</p>
              ) : null}

              {!inventoryQuery.isLoading && !filteredItems.length ? (
                <div className="rounded-[1.4rem] border border-dashed border-border bg-background/60 p-5 text-sm text-muted-foreground">
                  No items match this filter yet.
                </div>
              ) : null}

              {filteredItems.length ? (
                <div className="grid gap-3">
                  {filteredItems.map((item) => {
                    const tone = inventoryExpiryTone(item);
                    return (
                      <article
                        key={item.item_id}
                        className={cn(
                          "grid gap-3 rounded-[1.35rem] border border-border bg-background/80 p-4 md:grid-cols-[1.4fr_0.7fr_0.7fr_0.9fr_auto]",
                          tone === "warning" && "border-[color:rgba(212,131,70,0.45)] bg-[rgba(212,131,70,0.08)]",
                          tone === "danger" && "border-primary/35 bg-accent/35",
                        )}
                      >
                        <div>
                          <p className="font-medium">{item.name}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <Badge variant="outline">{formatLabel(item.category)}</Badge>
                            {item.expiry_date ? (
                              <Badge variant={tone === "danger" ? "default" : tone === "warning" ? "secondary" : "outline"}>
                                {tone === "danger"
                                  ? "Expired"
                                  : tone === "warning"
                                    ? `Use by ${formatDate(item.expiry_date)}`
                                    : `Fresh until ${formatDate(item.expiry_date)}`}
                              </Badge>
                            ) : null}
                          </div>
                        </div>
                        <div className="text-sm text-muted-foreground">
                          <p className="font-semibold text-foreground">{formatQuantity(item.quantity)}</p>
                          <p>Quantity</p>
                        </div>
                        <div className="text-sm text-muted-foreground">
                          <p className="font-semibold text-foreground">{item.unit || "No unit"}</p>
                          <p>Unit</p>
                        </div>
                        <div className="text-sm text-muted-foreground">
                          <p className="font-semibold text-foreground">
                            {item.expiry_date ? formatDate(item.expiry_date) : "Not set"}
                          </p>
                          <p>Expiry</p>
                        </div>
                        <div className="flex items-start justify-end">
                          <Button
                            disabled={deleteItemMutation.isPending}
                            onClick={() => void removeItem(item)}
                            size="sm"
                            type="button"
                            variant="ghost"
                          >
                            Delete
                          </Button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
