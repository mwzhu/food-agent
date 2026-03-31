import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { RunRead } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

type RunCardProps = {
  run: RunRead;
};

export function RunCard({ run }: RunCardProps) {
  return (
    <Link href={`/runs/${run.run_id}`}>
      <Card className="transition-all hover:-translate-y-1 hover:border-primary/30">
        <CardContent className="flex flex-col gap-4 p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                Run {run.run_id.slice(0, 8)}
              </p>
              <h3 className="font-display text-xl">
                {run.state_snapshot.nutrition_plan?.daily_calories ?? 0} calorie plan
              </h3>
            </div>
            <Badge variant={run.status === "completed" ? "success" : "default"}>{run.status}</Badge>
          </div>

          <div className="flex flex-wrap justify-between gap-3 text-sm text-muted-foreground">
            <span>{run.state_snapshot.selected_meals.length} meals</span>
            <span>{formatDateTime(run.created_at)}</span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
