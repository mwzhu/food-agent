import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SupplementStack } from "@/lib/supplement-types";
import { formatMoney, formatLabel } from "@/lib/utils";

type StackRecommendationProps = {
  stack: SupplementStack | null;
};

export function StackRecommendation({ stack }: StackRecommendationProps) {
  if (!stack) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Recommendation
          </p>
          <CardTitle>Recommended supplement stack</CardTitle>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {stack.summary || "The agent assembled a focused first-pass stack from the ranked store results."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {stack.total_monthly_cost !== null ? (
            <Badge variant="secondary">{formatMoney(stack.total_monthly_cost, stack.currency || "USD")}/month</Badge>
          ) : null}
          {stack.within_budget !== null ? (
            <Badge variant={stack.within_budget ? "success" : "outline"}>
              {stack.within_budget ? "Within budget" : "Over budget"}
            </Badge>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {stack.notes.length ? (
          <InfoBlock label="Notes" values={stack.notes} />
        ) : null}
        {stack.warnings.length ? (
          <InfoBlock label="Stack warnings" tone="warning" values={stack.warnings} />
        ) : null}

        {stack.items.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {stack.items.map((item) => (
              <article
                key={`${item.category}-${item.product.store_domain}-${item.product.product_id}`}
                className="rounded-[1.5rem] border border-border bg-background/75 p-5"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[0.72rem] uppercase tracking-[0.16em] text-muted-foreground">
                      {formatLabel(item.category)}
                    </p>
                    <h3 className="mt-2 font-display text-2xl leading-tight">{item.product.title}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">{item.product.store_domain}</p>
                  </div>
                  {item.monthly_cost !== null ? (
                    <Badge variant="secondary">
                      {formatMoney(item.monthly_cost, item.product.price_range.currency || stack.currency || "USD")}
                    </Badge>
                  ) : null}
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <Metric label="Goal" value={item.goal} />
                  <Metric label="Quantity" value={String(item.quantity)} />
                  <Metric label="Dosage" value={item.dosage || "See product label"} />
                  <Metric label="Cadence" value={item.cadence || "As directed"} />
                </div>

                <p className="mt-4 text-sm leading-6 text-muted-foreground">
                  {item.rationale || "Selected as the best fit from the ranked comparison set."}
                </p>

                {item.cautions.length ? (
                  <div className="mt-4 rounded-[1.2rem] border border-border/70 bg-card/60 p-3">
                    <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Cautions</p>
                    <ul className="mt-2 space-y-2 text-sm leading-6 text-accent-foreground">
                      {item.cautions.map((caution) => (
                        <li key={caution}>{caution}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="mt-5">
                  <Button asChild size="sm" variant="outline">
                    <a href={item.product.url} rel="noreferrer" target="_blank">
                      Open product page
                    </a>
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No stack items are available yet. Keep this page open while analysis finishes.
          </p>
        )}
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

function InfoBlock({
  label,
  values,
  tone = "default",
}: {
  label: string;
  values: string[];
  tone?: "default" | "warning";
}) {
  return (
    <div className="rounded-[1.3rem] border border-border bg-background/70 p-4">
      <p className="text-sm font-semibold text-foreground">{label}</p>
      <ul className={`mt-2 space-y-2 text-sm leading-6 ${tone === "warning" ? "text-accent-foreground" : "text-muted-foreground"}`}>
        {values.map((value) => (
          <li key={`${label}-${value}`}>{value}</li>
        ))}
      </ul>
    </div>
  );
}
