import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { HealthProfile } from "@/lib/supplement-types";
import { formatLabel, formatMoney } from "@/lib/utils";

type ProfileConfirmedCardProps = {
  profile: HealthProfile;
};

export function ProfileConfirmedCard({ profile }: ProfileConfirmedCardProps) {
  return (
    <Card>
      <CardHeader>
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
          Profile confirmed
        </p>
        <CardTitle>{profile.age} years old - {formatLabel(profile.sex)}</CardTitle>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Working within {formatMoney(profile.monthly_budget)} per month and screening for medications, conditions,
          and allergies before checkout.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <DetailRow label="Weight" value={`${profile.weight_lbs} lb`} />
        <DetailRow label="Budget" value={formatMoney(profile.monthly_budget)} />
        <TagGroup emptyLabel="No goals provided." label="Goals" values={profile.health_goals} />
        <TagGroup emptyLabel="No allergies reported." label="Allergies" values={profile.allergies} />
        {profile.current_supplements.length ? (
          <TagGroup
            emptyLabel="No current supplements reported."
            label="Current supplements"
            values={profile.current_supplements}
          />
        ) : null}
      </CardContent>
    </Card>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[1.1rem] border border-border/70 bg-background/65 px-4 py-3">
      <span className="text-sm text-muted-foreground">{label}</span>
      <strong className="text-sm text-foreground">{value}</strong>
    </div>
  );
}

function TagGroup({
  label,
  values,
  emptyLabel,
}: {
  label: string;
  values: string[];
  emptyLabel: string;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-foreground">{label}</p>
      {values.length ? (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => (
            <Badge key={`${label}-${value}`} variant="secondary">
              {value}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">{emptyLabel}</p>
      )}
    </div>
  );
}
