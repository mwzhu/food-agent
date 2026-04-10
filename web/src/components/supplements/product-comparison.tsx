import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ComparedProduct, ProductComparison as ProductComparisonRecord, ShopifyProduct } from "@/lib/supplement-types";
import { cn, formatLabel, formatMoney, joinList } from "@/lib/utils";

type ProductComparisonProps = {
  comparisons: ProductComparisonRecord[];
};

export function ProductComparison({ comparisons }: ProductComparisonProps) {
  if (!comparisons.length) {
    return null;
  }

  return (
    <section className="space-y-5">
      {comparisons.map((comparison) => (
        <Card key={comparison.category}>
          <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Comparison
              </p>
              <CardTitle>{formatLabel(comparison.category)}</CardTitle>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
                {comparison.summary || `Ranked options for ${comparison.goal}.`}
              </p>
            </div>
            <Badge variant="secondary">{comparison.ranked_products.length} ranked products</Badge>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 xl:grid-cols-3">
              {comparison.ranked_products.slice(0, 3).map((rankedProduct) => {
                const isTopPick =
                  rankedProduct.product.product_id === comparison.top_pick_product_id &&
                  rankedProduct.product.store_domain === comparison.top_pick_store_domain;

                return (
                  <article
                    key={`${rankedProduct.product.store_domain}-${rankedProduct.product.product_id}`}
                    className={cn(
                      "flex h-full flex-col rounded-[1.5rem] border border-border bg-background/75 p-5",
                      isTopPick && "border-success/30 bg-success-soft/60",
                    )}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={isTopPick ? "success" : "outline"}>
                            #{rankedProduct.rank}
                          </Badge>
                          {isTopPick ? <Badge variant="secondary">Top pick</Badge> : null}
                        </div>
                        <h3 className="mt-3 font-display text-2xl leading-tight">
                          {rankedProduct.product.title}
                        </h3>
                        <p className="mt-2 text-sm text-muted-foreground">
                          {rankedProduct.product.store_domain}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <Metric label="Price" value={formatProductPrice(rankedProduct.product)} />
                      <Metric
                        label="Monthly cost"
                        value={
                          rankedProduct.monthly_cost !== null
                            ? formatMoney(rankedProduct.monthly_cost, productCurrency(rankedProduct.product))
                            : "Unknown"
                        }
                      />
                      <Metric
                        label="Price / serving"
                        value={
                          rankedProduct.ingredient_analysis.price_per_serving !== null
                            ? formatMoney(
                                rankedProduct.ingredient_analysis.price_per_serving,
                                productCurrency(rankedProduct.product),
                              )
                            : "Unknown"
                        }
                      />
                      <Metric
                        label="Primary ingredients"
                        value={
                          rankedProduct.ingredient_analysis.primary_ingredients.length
                            ? joinList(rankedProduct.ingredient_analysis.primary_ingredients)
                            : "See notes"
                        }
                      />
                    </div>

                    <p className="mt-4 text-sm leading-6 text-muted-foreground">
                      {rankedProduct.rationale || rankedProduct.product.description || "No rationale provided."}
                    </p>

                    {rankedProduct.ingredient_analysis.dosage_summary ? (
                      <div className="mt-4 rounded-[1.2rem] border border-border/70 bg-card/60 p-3">
                        <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Dosage notes</p>
                        <p className="mt-2 text-sm leading-6 text-foreground">
                          {rankedProduct.ingredient_analysis.dosage_summary}
                        </p>
                      </div>
                    ) : null}

                    <div className="mt-4 space-y-3">
                      <TextList label="Pros" values={rankedProduct.pros} />
                      <TextList label="Cons" values={rankedProduct.cons} />
                      <TextList
                        label="Warnings"
                        tone="warning"
                        values={[
                          ...rankedProduct.warnings,
                          ...rankedProduct.ingredient_analysis.allergens.map(
                            (allergen) => `Potential allergen: ${allergen}`,
                          ),
                        ]}
                      />
                    </div>

                    <div className="mt-5 flex flex-wrap gap-2">
                      <Button asChild size="sm" variant="outline">
                        <a href={rankedProduct.product.url} rel="noreferrer" target="_blank">
                          View product
                        </a>
                      </Button>
                    </div>
                  </article>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ))}
    </section>
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

function TextList({
  label,
  values,
  tone = "default",
}: {
  label: string;
  values: string[];
  tone?: "default" | "warning";
}) {
  if (!values.length) {
    return null;
  }

  return (
    <div>
      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <ul
        className={cn(
          "mt-2 space-y-2 text-sm leading-6 text-muted-foreground",
          tone === "warning" && "text-accent-foreground",
        )}
      >
        {values.map((value) => (
          <li key={`${label}-${value}`}>{value}</li>
        ))}
      </ul>
    </div>
  );
}

function formatProductPrice(product: ShopifyProduct): string {
  const price = productPrice(product);
  if (price === null) {
    return "Unknown";
  }
  return formatMoney(price, productCurrency(product));
}

function productPrice(product: ShopifyProduct): number | null {
  const availableVariant = product.variants.find((variant) => variant.available);
  return (
    availableVariant?.price ??
    product.variants[0]?.price ??
    product.price_range.min_price ??
    product.price_range.max_price ??
    null
  );
}

function productCurrency(product: ShopifyProduct): string {
  const availableVariant = product.variants.find((variant) => variant.available);
  return availableVariant?.currency || product.variants[0]?.currency || product.price_range.currency || "USD";
}
