"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { SupplementCriticVerdict } from "@/lib/supplement-types";
import { formatLabel } from "@/lib/utils";

type SafetyCardProps = {
  verdict: SupplementCriticVerdict;
};

export function SafetyCard({ verdict }: SafetyCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const findings = verdict.findings.length
    ? verdict.findings
    : [
        ...verdict.issues.map((message) => ({
          concern: "safety" as const,
          severity: "issue" as const,
          message,
        })),
        ...verdict.warnings.map((message) => ({
          concern: "value" as const,
          severity: "warning" as const,
          message,
        })),
      ];

  return (
    <Card>
      <CardHeader className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Safety review
          </p>
          <CardTitle>{verdict.summary}</CardTitle>
          {verdict.manual_review_reason ? (
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {verdict.manual_review_reason}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={decisionVariant(verdict.decision)}>{formatLabel(verdict.decision)}</Badge>
          <Badge variant="outline">{verdict.issues.length} issues</Badge>
          <Badge variant="outline">{verdict.warnings.length} warnings</Badge>
        </div>
      </CardHeader>
      <CardContent>
        {findings.length ? (
          <>
            <Button onClick={() => setIsExpanded((current) => !current)} size="sm" type="button" variant="ghost">
              {isExpanded ? "Hide findings" : `View ${findings.length} findings`}
            </Button>
            {isExpanded ? (
              <div className="mt-4 space-y-3">
                {findings.map((finding, index) => (
                  <article
                    key={`${finding.concern}-${finding.severity}-${index}`}
                    className="rounded-[1.2rem] border border-border bg-background/70 p-4"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={finding.severity === "issue" ? "outline" : "secondary"}>
                        {formatLabel(finding.severity)}
                      </Badge>
                      <span className="text-xs uppercase tracking-[0.14em] text-muted-foreground">
                        {formatLabel(finding.concern)}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-muted-foreground">{finding.message}</p>
                  </article>
                ))}
              </div>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">No additional critic findings were recorded.</p>
        )}
      </CardContent>
    </Card>
  );
}

function decisionVariant(decision: SupplementCriticVerdict["decision"]) {
  if (decision === "passed") {
    return "success";
  }
  if (decision === "manual_review_needed") {
    return "secondary";
  }
  return "outline";
}
