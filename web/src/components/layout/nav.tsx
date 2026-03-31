"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCurrentUser } from "@/components/layout/providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/profile", label: "Profile" },
  { href: "/runs", label: "Run history" },
  { href: "/onboarding", label: "New profile" },
];

export function Nav() {
  const pathname = usePathname();
  const { userId, clearUserId } = useCurrentUser();

  return (
    <header className="mx-auto grid max-w-7xl gap-4 rounded-[2rem] border border-border bg-card/80 px-4 py-4 shadow-soft backdrop-blur-xl md:grid-cols-[1.4fr_1fr_auto] md:items-center md:px-5">
      <div className="flex items-center gap-4">
        <Link
          className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-[linear-gradient(135deg,var(--primary),var(--secondary-foreground))] font-display text-lg font-bold text-primary-foreground"
          href="/"
        >
          Shopper
        </Link>
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Phase 1 planner
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Nutrition-first meal planning with traceable runs.
          </p>
        </div>
      </div>

      <nav className="flex flex-wrap items-center justify-center gap-2 md:justify-center" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            className={cn(
              "rounded-full px-4 py-2 text-sm font-medium text-muted-foreground transition-all hover:-translate-y-0.5 hover:bg-secondary/80 hover:text-secondary-foreground",
              pathname === item.href && "bg-secondary text-secondary-foreground shadow-sm",
            )}
            href={item.href}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="flex flex-wrap items-center justify-start gap-3 md:justify-end">
        <div className="rounded-full border border-border bg-background/80 px-4 py-2 shadow-sm">
          <span className="block text-[0.72rem] uppercase tracking-[0.14em] text-muted-foreground">
            Active profile
          </span>
          <strong>{userId ?? "None selected"}</strong>
        </div>
        {userId ? <Badge variant="secondary">{userId}</Badge> : null}
        {userId ? (
          <Button onClick={clearUserId} size="sm" type="button" variant="ghost">
            Clear
          </Button>
        ) : null}
      </div>
    </header>
  );
}
