"use client";

import Link from "next/link";

import { useCurrentUser } from "@/components/layout/providers";
import { InventoryManager } from "@/components/inventory/inventory-manager";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function InventoryPage() {
  const { userId, isHydrated } = useCurrentUser();

  if (!isHydrated) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading your fridge workspace...</p>
      </section>
    );
  }

  if (!userId) {
    return (
      <section className="space-y-6">
        <Card>
          <CardHeader>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Inventory</p>
            <CardTitle>Select a profile before editing the fridge.</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm leading-6 text-muted-foreground">
              Inventory is tied to the active user profile so each planner run can diff against the right kitchen.
            </p>
            <Button asChild>
              <Link href="/onboarding">Create a profile</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Phase 3 inventory</p>
          <CardTitle className="text-4xl md:text-5xl">Fridge inventory for {userId}</CardTitle>
          <p className="max-w-3xl text-base leading-7 text-muted-foreground">
            Keep staples, expiring produce, and frozen backups up to date so future runs can strike through what you
            already own instead of sending you shopping for duplicates.
          </p>
        </CardHeader>
      </Card>

      <InventoryManager userId={userId} />
    </section>
  );
}
