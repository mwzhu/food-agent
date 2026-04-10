import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type {
  SupplementPhaseName,
  SupplementPhaseStatuses,
  SupplementRunLifecycleStatus,
} from "@/lib/supplement-types";
import { cn } from "@/lib/utils";

type SupplementPhaseStepperProps = {
  runStatus: SupplementRunLifecycleStatus;
  currentPhase: SupplementPhaseName | null;
  phaseStatuses: SupplementPhaseStatuses;
};

const PHASES = [
  { key: "memory", label: "Intake" },
  { key: "discovery", label: "Discovery" },
  { key: "analysis", label: "Analysis" },
  { key: "checkout", label: "Checkout" },
] as const;

export function SupplementPhaseStepper({
  runStatus,
  currentPhase,
  phaseStatuses,
}: SupplementPhaseStepperProps) {
  return (
    <div className="grid gap-3 lg:grid-cols-4" aria-label="Supplement run progress">
      {PHASES.map((phase, index) => {
        const state = phaseStatuses[phase.key];
        const isCurrent = currentPhase === phase.key;
        const badgeVariant = state === "completed" ? "success" : state === "running" ? "default" : "outline";

        return (
          <Card
            key={phase.key}
            className={cn(
              "flex flex-row items-center gap-4 rounded-[1.4rem] border px-4 py-4 shadow-none",
              state === "running" && "bg-accent/70",
              state === "completed" && "bg-success-soft",
              state === "failed" && "border-primary/30 bg-accent/80",
              state === "locked" && "opacity-65",
            )}
          >
            <span className="grid h-9 w-9 place-items-center rounded-full border border-border bg-background text-sm font-semibold">
              {index + 1}
            </span>
            <div>
              <p className="font-medium">{phase.label}</p>
              <small className="text-muted-foreground">
                {state === "completed"
                  ? "Complete"
                  : state === "running"
                    ? isCurrent
                      ? "In progress"
                      : "Queued"
                    : state === "failed"
                      ? "Needs attention"
                      : "Locked"}
              </small>
            </div>
            <Badge className="ml-auto" variant={badgeVariant}>
              {runStatus === "failed" && phase.key === currentPhase ? "failed" : state}
            </Badge>
          </Card>
        );
      })}
    </div>
  );
}
