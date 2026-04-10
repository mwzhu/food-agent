"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { HealthProfile } from "@/lib/supplement-types";
import { cn, formatLabel, joinList, splitListInput } from "@/lib/utils";

const SEX_OPTIONS = ["female", "male", "other"] as const;

const healthFormSchema = z.object({
  age: z.coerce.number().int().min(13).max(120),
  weight_lbs: z.coerce.number().positive(),
  sex: z.enum(SEX_OPTIONS),
  health_goals_text: z.string().trim().min(1, "Add at least one health goal."),
  current_supplements_text: z.string().default(""),
  medications_text: z.string().default(""),
  conditions_text: z.string().default(""),
  allergies_text: z.string().default(""),
  monthly_budget: z.coerce.number().min(0),
});

type HealthFormValues = z.infer<typeof healthFormSchema>;

type HealthFormProps = {
  userId: string;
  initialValues?: Partial<HealthProfile>;
  submitLabel: string;
  onSubmit: (payload: HealthProfile) => Promise<void>;
};

const selectClassName =
  "flex h-12 w-full rounded-3xl border border-border bg-background/80 px-4 py-3 text-sm text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-[border-color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-60";

function buildDefaults(initialValues?: Partial<HealthProfile>): HealthFormValues {
  return {
    age: initialValues?.age ?? 32,
    weight_lbs: initialValues?.weight_lbs ?? 165,
    sex: initialValues?.sex ?? "female",
    health_goals_text: joinList(initialValues?.health_goals ?? ["better sleep", "stress support"]),
    current_supplements_text: joinList(initialValues?.current_supplements ?? []),
    medications_text: joinList(initialValues?.medications ?? []),
    conditions_text: joinList(initialValues?.conditions ?? []),
    allergies_text: joinList(initialValues?.allergies ?? []),
    monthly_budget: initialValues?.monthly_budget ?? 90,
  };
}

export function HealthForm({
  userId,
  initialValues,
  submitLabel,
  onSubmit,
}: HealthFormProps) {
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<HealthFormValues>({
    resolver: zodResolver(healthFormSchema),
    defaultValues: buildDefaults(initialValues),
  });

  useEffect(() => {
    reset(buildDefaults(initialValues));
  }, [initialValues, reset]);

  const values = watch();
  const parsedGoals = splitListInput(values.health_goals_text);
  const parsedConditions = splitListInput(values.conditions_text);
  const parsedMedications = splitListInput(values.medications_text);
  const parsedAllergies = splitListInput(values.allergies_text);

  const submit = handleSubmit(async (formValues) => {
    await onSubmit({
      age: formValues.age,
      weight_lbs: formValues.weight_lbs,
      sex: formValues.sex,
      health_goals: splitListInput(formValues.health_goals_text),
      current_supplements: splitListInput(formValues.current_supplements_text),
      medications: splitListInput(formValues.medications_text),
      conditions: splitListInput(formValues.conditions_text),
      allergies: splitListInput(formValues.allergies_text),
      monthly_budget: formValues.monthly_budget,
    });
  });

  return (
    <form className="grid gap-5 xl:grid-cols-[1.45fr_0.85fr]" onSubmit={submit}>
      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Health intake
          </p>
          <CardTitle>Tell the supplement agent what it needs to optimize around.</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <section className="grid gap-4 md:grid-cols-3">
            <Field error={errors.age?.message} label="Age">
              <Input {...register("age")} min={13} type="number" />
            </Field>
            <Field error={errors.weight_lbs?.message} label="Weight (lb)">
              <Input {...register("weight_lbs")} min={1} step="0.1" type="number" />
            </Field>
            <Field error={errors.sex?.message} label="Sex">
              <select {...register("sex")} className={selectClassName}>
                {SEX_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {formatLabel(option)}
                  </option>
                ))}
              </select>
            </Field>
          </section>

          <section className="grid gap-4">
            <Field
              error={errors.health_goals_text?.message}
              hint="Comma or line separated. Example: better sleep, muscle recovery, stress support."
              label="Health goals"
            >
              <Textarea {...register("health_goals_text")} rows={4} />
            </Field>
            <Field
              error={errors.current_supplements_text?.message}
              hint="Current regimen so the stack builder can avoid unnecessary overlap."
              label="Current supplements"
            >
              <Textarea {...register("current_supplements_text")} rows={3} />
            </Field>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <Field
              error={errors.medications_text?.message}
              hint="The critic will flag these for manual review if interaction risk is unclear."
              label="Medications"
            >
              <Textarea {...register("medications_text")} rows={4} />
            </Field>
            <Field
              error={errors.conditions_text?.message}
              hint="Examples: pregnancy, thyroid condition, kidney issues."
              label="Conditions"
            >
              <Textarea {...register("conditions_text")} rows={4} />
            </Field>
            <Field
              error={errors.allergies_text?.message}
              hint="Hard safety exclusions, not preferences."
              label="Allergies"
            >
              <Textarea {...register("allergies_text")} rows={4} />
            </Field>
            <Field error={errors.monthly_budget?.message} label="Monthly budget">
              <Input {...register("monthly_budget")} min={0} step="1" type="number" />
            </Field>
          </section>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/80 pt-4">
            <p className="text-sm text-muted-foreground">
              This run will be stored under <strong className="text-foreground">{userId}</strong>.
            </p>
            <Button disabled={isSubmitting} type="submit">
              {isSubmitting ? "Finding your stack..." : submitLabel}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
            Run preview
          </p>
          <CardTitle>What the agent will emphasize</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <PreviewBlock
            emptyLabel="No goals added yet."
            label="Primary goals"
            values={parsedGoals}
            variant="secondary"
          />
          <PreviewBlock
            emptyLabel="No conditions listed."
            label="Conditions"
            values={parsedConditions}
          />
          <PreviewBlock
            emptyLabel="No medications listed."
            label="Medications"
            values={parsedMedications}
          />
          <PreviewBlock
            emptyLabel="No allergies listed."
            label="Allergies"
            values={parsedAllergies}
          />

          <div className="rounded-[1.4rem] border border-border bg-background/70 p-4">
            <p className="text-sm font-semibold text-foreground">Budget posture</p>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              The stack builder will try to stay within <strong className="text-foreground">${values.monthly_budget || 0}</strong>{" "}
              per month while keeping the stack compact and practical.
            </p>
          </div>
        </CardContent>
      </Card>
    </form>
  );
}

function Field({
  label,
  error,
  hint,
  className,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label>{label}</Label>
      {children}
      {hint ? <p className="text-xs leading-5 text-muted-foreground">{hint}</p> : null}
      {error ? <p className="text-xs font-medium text-accent-foreground">{error}</p> : null}
    </div>
  );
}

function PreviewBlock({
  label,
  values,
  emptyLabel,
  variant = "outline",
}: {
  label: string;
  values: string[];
  emptyLabel: string;
  variant?: "default" | "secondary" | "success" | "outline";
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-foreground">{label}</p>
      {values.length ? (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => (
            <Badge key={value} variant={variant}>
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
