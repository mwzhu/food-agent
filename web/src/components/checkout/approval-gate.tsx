"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useResumeRun } from "@/hooks/use-run";

type ApprovalGateProps = {
  runId: string;
};

export function ApprovalGate({ runId }: ApprovalGateProps) {
  const router = useRouter();
  const resumeMutation = useResumeRun();
  const [reason, setReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const submitDecision = async (decision: "approve" | "reject") => {
    setErrorMessage(null);
    try {
      await resumeMutation.mutateAsync({
        runId,
        payload: {
          decision,
          reason: reason || null,
          edits: [],
        },
      });
      router.push(`/runs/${runId}`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Could not submit approval.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">Approval gate</p>
        <CardTitle>Human approval is required before purchase</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-[1.25rem] border border-amber-400/30 bg-amber-50/60 p-4 text-sm text-amber-950">
          Approving will continue the checkout flow and place the order. Reject if anything looks off.
        </div>

        <div className="space-y-2">
          <Label htmlFor="approval-reason">Reason or note</Label>
          <Textarea
            id="approval-reason"
            onChange={(event) => setReason(event.target.value)}
            placeholder="Optional approval note or rejection reason"
            value={reason}
          />
        </div>

        {errorMessage ? <p className="text-sm font-medium text-accent-foreground">{errorMessage}</p> : null}

        <div className="flex flex-wrap gap-3">
          <Button
            disabled={resumeMutation.isPending}
            onClick={() => void submitDecision("approve")}
            type="button"
          >
            {resumeMutation.isPending ? "Submitting..." : "Approve checkout"}
          </Button>
          <Button
            disabled={resumeMutation.isPending}
            onClick={() => void submitDecision("reject")}
            type="button"
            variant="outline"
          >
            Reject checkout
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
