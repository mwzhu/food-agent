import { CheckCircle2, Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CategoryDiscoveryResult } from "@/lib/supplement-types";
import { cn, formatLabel } from "@/lib/utils";

type SearchProgressCardProps = {
  results: CategoryDiscoveryResult[];
  isComplete: boolean;
};

export function SearchProgressCard({ results, isComplete }: SearchProgressCardProps) {
  const uniqueStores = Array.from(
    new Set(results.flatMap((result) => result.store_results.map((storeResult) => storeResult.store_domain))),
  );
  const totalProducts = results.reduce(
    (total, result) => total + result.store_results.reduce((innerTotal, storeResult) => innerTotal + storeResult.products.length, 0),
    0,
  );

  return (
    <Card className="overflow-hidden">
      <CardHeader className="gap-4 border-b border-border/70 bg-background/45">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
              Store search
            </p>
            <CardTitle className="mt-1 flex items-center gap-2 text-2xl">
              {isComplete ? <CheckCircle2 className="size-5 text-success" /> : <Search className="size-5 text-secondary-foreground" />}
              {isComplete ? "Discovery complete" : "Searching stores..."}
            </CardTitle>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {isComplete
                ? `Found ${totalProducts} products across ${uniqueStores.length} stores.`
                : "Verified storefronts are being queried and grouped into supplement categories."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={isComplete ? "success" : "secondary"}>{results.length} categories</Badge>
            <Badge variant="outline">{uniqueStores.length} stores</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-6">
        {results.map((result) => {
          const productCount = result.store_results.reduce((total, storeResult) => total + storeResult.products.length, 0);

          return (
            <article
              key={`${result.category}-${result.goal}`}
              className="rounded-[1.35rem] border border-border bg-background/70 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.16em] text-muted-foreground">
                    {formatLabel(result.category)}
                  </p>
                  <h3 className="mt-1 text-lg font-semibold text-foreground">{result.goal}</h3>
                </div>
                <Badge variant="secondary">{productCount} matches</Badge>
              </div>

              {result.search_queries.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {result.search_queries.map((query) => (
                    <Badge key={`${result.category}-${query}`} variant="outline">
                      {query}
                    </Badge>
                  ))}
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2">
                {result.store_results.map((storeResult) => (
                  <span
                    key={`${result.category}-${storeResult.store_domain}`}
                    className={cn(
                      "inline-flex items-center rounded-full border border-border/80 px-3 py-1.5 text-xs font-medium text-muted-foreground",
                      storeResult.products.length > 0 && "bg-success-soft/80 text-success",
                    )}
                  >
                    {storeResult.store_domain}
                    <span className="ml-2 text-[11px] opacity-75">{storeResult.products.length}</span>
                  </span>
                ))}
              </div>
            </article>
          );
        })}
      </CardContent>
    </Card>
  );
}
