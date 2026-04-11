"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
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

type IntakeFormValues = z.infer<typeof healthFormSchema>;

type IntakeFormCompactProps = {
  userId: string;
  initialValues?: Partial<HealthProfile>;
  onSubmit: (payload: HealthProfile) => Promise<void>;
};

const selectClassName =
  "flex h-12 w-full rounded-3xl border border-border bg-background/80 px-4 py-3 text-sm text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-[border-color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-60";

export function IntakeFormCompact({
  userId,
  initialValues,
  onSubmit,
}: IntakeFormCompactProps) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<IntakeFormValues>({
    resolver: zodResolver(healthFormSchema),
    defaultValues: buildDefaults(initialValues),
  });

  useEffect(() => {
    reset(buildDefaults(initialValues));
  }, [initialValues, reset]);

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
    <form className="space-y-4 rounded-[1.75rem] border border-border bg-card/95 p-5 shadow-soft" onSubmit={submit}>
      <div className="space-y-2">
        <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
          Quick intake
        </p>
        <p className="text-sm leading-6 text-muted-foreground">
          Confirm the basics so I can compare verified supplement options for <strong className="text-foreground">{userId}</strong>.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
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
      </div>

      <Field
        error={errors.health_goals_text?.message}
        hint="Comma or line separated. Example: better sleep, muscle recovery."
        label="Health goals"
      >
        <Textarea {...register("health_goals_text")} className="min-h-24" rows={3} />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          error={errors.current_supplements_text?.message}
          hint="Optional. Helps avoid overlap."
          label="Current supplements"
        >
          <Textarea {...register("current_supplements_text")} className="min-h-20" rows={3} />
        </Field>
        <Field
          error={errors.medications_text?.message}
          hint="Optional. The safety critic will screen these."
          label="Medications"
        >
          <Textarea {...register("medications_text")} className="min-h-20" rows={3} />
        </Field>
        <Field
          error={errors.conditions_text?.message}
          hint="Optional. Example: thyroid condition."
          label="Conditions"
        >
          <Textarea {...register("conditions_text")} className="min-h-20" rows={3} />
        </Field>
        <Field
          error={errors.allergies_text?.message}
          hint="Optional. Hard safety exclusions."
          label="Allergies"
        >
          <Textarea {...register("allergies_text")} className="min-h-20" rows={3} />
        </Field>
      </div>

      <Field error={errors.monthly_budget?.message} label="Monthly budget">
        <Input {...register("monthly_budget")} min={0} step="1" type="number" />
      </Field>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/80 pt-4">
        <p className="text-xs leading-5 text-muted-foreground">
          Stored under this local profile handle so the run stays grouped in your browser.
        </p>
        <Button disabled={isSubmitting} type="submit">
          {isSubmitting ? "Finding your stack..." : "Find My Stack"}
        </Button>
      </div>
    </form>
  );
}

function buildDefaults(initialValues?: Partial<HealthProfile>): IntakeFormValues {
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
