"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { CheckoutLinks } from "@/components/supplements/checkout-links";
import { ProductComparison } from "@/components/supplements/product-comparison";
import { SupplementRunProgress } from "@/components/supplements/run-progress";
import { StackRecommendation } from "@/components/supplements/stack-recommendation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSupplementRun, useSupplementRunStream } from "@/hooks/use-supplement-run";
import type {
  CategoryDiscoveryResult,
  HealthProfile,
  SupplementCriticVerdict,
  SupplementRunLifecycleStatus,
} from "@/lib/supplement-types";
import { formatDateTime, formatLabel, formatMoney, joinList } from "@/lib/utils";

export default function SupplementRunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const runQuery = useSupplementRun(runId, true);
  const stream = useSupplementRunStream(runId);

  if (runQuery.isLoading && !runQuery.data) {
    return (
      <section className="grid min-h-[220px] place-items-center rounded-[1.75rem] border border-border bg-card/90 p-8 shadow-soft">
        <p className="text-muted-foreground">Loading supplement run...</p>
      </section>
    );
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Supplement run
          </p>
          <CardTitle>That supplement run could not be loaded.</CardTitle>
        </CardHeader>
        <CardContent>
          <Button asChild>
            <Link href="/supplements">Back to supplements</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const run = runQuery.data;
  const snapshot = run.state_snapshot;
  const readyCartCount = snapshot.store_carts.filter((cart) => cart.checkout_url).length;
  const criticVerdict = snapshot.critic_verdict;

  return (
    <section className="space-y-6">
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Supplement run
          </p>
          <CardTitle className="text-4xl md:text-5xl">Stack build {run.run_id.slice(0, 8)}</CardTitle>
          <p className="max-w-3xl text-base leading-7 text-muted-foreground">
            Created {formatDateTime(run.created_at)} for {run.user_id}. This page streams the supplement graph as it
            discovers products, ranks options, prepares carts, and waits for approval.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
            {criticVerdict ? <Badge variant={decisionVariant(criticVerdict.decision)}>{criticVerdict.decision}</Badge> : null}
            <Button asChild size="sm" variant="ghost">
              <Link href="/supplements">Back to intake</Link>
            </Button>
          </div>
        </CardHeader>
      </Card>

      <SupplementRunProgress
        currentPhase={snapshot.current_phase}
        events={stream.events}
        isStreaming={stream.isStreaming}
        phaseStatuses={snapshot.phase_statuses}
        readyCartCount={readyCartCount}
        runStatus={run.status}
      />

      <div className="grid gap-5 xl:grid-cols-[1.35fr_0.9fr]">
        <div className="space-y-5">
          <DiscoveryResultsCard
            discoveryResults={snapshot.discovery_results}
            isRunning={run.status === "running"}
          />

          {snapshot.product_comparisons.length ? (
            <ProductComparison comparisons={snapshot.product_comparisons} />
          ) : run.status === "running" ? (
            <WaitingCard
              label="Comparison"
              title="Waiting for ranked product comparisons"
              body="The agent will compare dosage, form, and value as soon as discovery finishes."
            />
          ) : null}

          {snapshot.recommended_stack ? (
            <StackRecommendation stack={snapshot.recommended_stack} />
          ) : run.status === "running" ? (
            <WaitingCard
              label="Recommendation"
              title="Waiting for the stack builder"
              body="The recommendation card will populate once the comparison phase assembles a final stack."
            />
          ) : null}

          {snapshot.store_carts.length || run.status === "awaiting_approval" || snapshot.approved_store_domains.length ? (
            <CheckoutLinks
              approvedStoreDomains={snapshot.approved_store_domains}
              runId={runId}
              runStatus={run.status}
              storeCarts={snapshot.store_carts}
            />
          ) : null}

          {run.status === "failed" ? (
            <Card>
              <CardHeader>
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Run error</p>
                <CardTitle>The supplement run stopped early.</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-6 text-muted-foreground">
                  {snapshot.latest_error ?? "The graph did not return a more specific failure message."}
                </p>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <div className="space-y-5">
          <IntakeSnapshotCard healthProfile={snapshot.health_profile} />
          <CriticVerdictCard runStatus={run.status} verdict={criticVerdict} />
          <TraceCard
            approvedStoreDomains={snapshot.approved_store_domains}
            currentNode={snapshot.current_node}
            traceMetadata={snapshot.trace_metadata}
          />
        </div>
      </div>
    </section>
  );
}

function DiscoveryResultsCard({
  discoveryResults,
  isRunning,
}: {
  discoveryResults: CategoryDiscoveryResult[];
  isRunning: boolean;
}) {
  if (!discoveryResults.length) {
    if (!isRunning) {
      return null;
    }
    return (
      <WaitingCard
        label="Discovery"
        title="Searching verified stores"
        body="The agent is translating the intake into supplement categories and querying each store for candidates."
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Discovery</p>
        <CardTitle>Store search results by category</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {discoveryResults.map((result) => {
          const productCount = result.store_results.reduce((total, storeResult) => total + storeResult.products.length, 0);
          return (
            <article
              key={result.category}
              className="rounded-[1.5rem] border border-border bg-background/75 p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[0.72rem] uppercase tracking-[0.16em] text-muted-foreground">
                    {formatLabel(result.category)}
                  </p>
                  <h3 className="mt-2 font-display text-2xl leading-tight">{result.goal}</h3>
                </div>
                <Badge variant="secondary">{productCount} total matches</Badge>
              </div>

              {result.search_queries.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {result.search_queries.map((query) => (
                    <Badge key={`${result.category}-${query}`} variant="outline">
                      {query}
                    </Badge>
                  ))}
                </div>
              ) : null}

              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {result.store_results.map((storeResult) => (
                  <div
                    key={`${result.category}-${storeResult.store_domain}`}
                    className="rounded-[1.2rem] border border-border/70 bg-card/60 p-3"
                  >
                    <p className="text-sm font-medium text-foreground">{storeResult.store_domain}</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {storeResult.products.length} product{storeResult.products.length === 1 ? "" : "s"} for "{storeResult.query}"
                    </p>
                  </div>
                ))}
              </div>
            </article>
          );
        })}
      </CardContent>
    </Card>
  );
}

function IntakeSnapshotCard({ healthProfile }: { healthProfile: HealthProfile }) {
  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Intake snapshot</p>
        <CardTitle>User health profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <MetricCard label="Age" value={String(healthProfile.age)} />
          <MetricCard label="Weight" value={`${healthProfile.weight_lbs} lb`} />
          <MetricCard label="Sex" value={formatLabel(healthProfile.sex)} />
          <MetricCard label="Budget" value={formatMoney(healthProfile.monthly_budget)} />
        </div>

        <TextGroup label="Health goals" values={healthProfile.health_goals} />
        <TextGroup label="Current supplements" values={healthProfile.current_supplements} />
        <TextGroup label="Medications" values={healthProfile.medications} />
        <TextGroup label="Conditions" values={healthProfile.conditions} />
        <TextGroup label="Allergies" values={healthProfile.allergies} />
      </CardContent>
    </Card>
  );
}

function CriticVerdictCard({
  verdict,
  runStatus,
}: {
  verdict: SupplementCriticVerdict | null;
  runStatus: SupplementRunLifecycleStatus;
}) {
  if (!verdict) {
    return (
      <WaitingCard
        label="Critic"
        title="Waiting for critic findings"
        body="Safety, goal alignment, and budget checks will appear here once analysis finishes."
      />
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Critic</p>
          <CardTitle>{verdict.summary}</CardTitle>
        </div>
        <Badge variant={decisionVariant(verdict.decision)}>{verdict.decision}</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {verdict.issues.length ? <TextGroup label="Issues" tone="warning" values={verdict.issues} /> : null}
        {verdict.warnings.length ? <TextGroup label="Warnings" tone="warning" values={verdict.warnings} /> : null}
        {!verdict.issues.length && !verdict.warnings.length ? (
          <p className="text-sm text-muted-foreground">No additional critic findings were recorded.</p>
        ) : null}
        {verdict.decision === "manual_review_needed" && runStatus === "completed" ? (
          <p className="text-sm leading-6 text-muted-foreground">
            Checkout was intentionally skipped because this stack needs a clinician or pharmacist review first.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function TraceCard({
  traceMetadata,
  currentNode,
  approvedStoreDomains,
}: {
  traceMetadata: {
    kind: string | null;
    project: string | null;
    trace_id: string | null;
    source: string | null;
  };
  currentNode: string;
  approvedStoreDomains: string[];
}) {
  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Trace</p>
        <CardTitle>Execution metadata</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-3 text-sm leading-6 text-muted-foreground">
          <li>
            <strong className="text-foreground">Current node:</strong> {formatLabel(currentNode)}
          </li>
          <li>
            <strong className="text-foreground">Trace kind:</strong> {traceMetadata.kind ?? "Unavailable"}
          </li>
          <li>
            <strong className="text-foreground">Project:</strong> {traceMetadata.project ?? "Unavailable"}
          </li>
          <li>
            <strong className="text-foreground">Trace id:</strong> {traceMetadata.trace_id ?? "Unavailable"}
          </li>
          <li>
            <strong className="text-foreground">Source:</strong> {traceMetadata.source ?? "Unavailable"}
          </li>
          <li>
            <strong className="text-foreground">Approved stores:</strong>{" "}
            {approvedStoreDomains.length ? joinList(approvedStoreDomains) : "None yet"}
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}

function WaitingCard({
  label,
  title,
  body,
}: {
  label: string;
  title: string;
  body: string;
}) {
  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-6 text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.2rem] border border-border bg-background/75 p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <strong className="mt-1 block text-xl">{value}</strong>
    </div>
  );
}

function TextGroup({
  label,
  values,
  tone = "default",
}: {
  label: string;
  values: string[];
  tone?: "default" | "warning";
}) {
  return (
    <div>
      <p className="text-sm font-semibold text-foreground">{label}</p>
      {values.length ? (
        <ul className={`mt-2 space-y-2 text-sm leading-6 ${tone === "warning" ? "text-accent-foreground" : "text-muted-foreground"}`}>
          {values.map((value) => (
            <li key={`${label}-${value}`}>{value}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-muted-foreground">None reported.</p>
      )}
    </div>
  );
}

function decisionVariant(decision: string) {
  if (decision === "passed") {
    return "success";
  }
  if (decision === "manual_review_needed") {
    return "secondary";
  }
  return "outline";
}

function statusVariant(status: SupplementRunLifecycleStatus) {
  if (status === "completed") {
    return "success";
  }
  if (status === "awaiting_approval") {
    return "secondary";
  }
  if (status === "failed") {
    return "outline";
  }
  return "default";
}
