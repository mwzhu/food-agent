import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type PhaseStepperProps = {
  runStatus: "running" | "completed";
};

const PHASES = ["Planning", "Shopping", "Checkout"];

export function PhaseStepper({ runStatus }: PhaseStepperProps) {
  return (
    <div className="grid gap-3 md:grid-cols-3" aria-label="Run progress">
      {PHASES.map((phase, index) => {
        const state =
          index === 0
            ? runStatus === "completed"
              ? "done"
              : "active"
            : "locked";

        return (
          <Card
            key={phase}
            className={cn(
              "flex flex-row items-center gap-4 rounded-[1.4rem] border px-4 py-4 shadow-none",
              state === "active" && "bg-accent/70",
              state === "done" && "bg-success-soft",
              state === "locked" && "opacity-65",
            )}
          >
            <span className="grid h-9 w-9 place-items-center rounded-full border border-border bg-background text-sm font-semibold">
              {index + 1}
            </span>
            <div>
              <p className="font-medium">{phase}</p>
              <small className="text-muted-foreground">
                {state === "done"
                  ? "Complete"
                  : state === "active"
                    ? "In progress"
                    : "Phase 1 later"}
              </small>
            </div>
            <Badge
              className="ml-auto"
              variant={state === "done" ? "success" : state === "active" ? "default" : "outline"}
            >
              {state}
            </Badge>
          </Card>
        );
      })}
    </div>
  );
}
