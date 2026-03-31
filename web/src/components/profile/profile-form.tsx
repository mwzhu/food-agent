"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { UserProfileCreate, UserProfileRead, UserProfileUpdate } from "@/lib/types";
import { cn, formatLabel, joinList, splitListInput } from "@/lib/utils";

const SEX_OPTIONS = ["female", "male", "other"] as const;
const ACTIVITY_OPTIONS = [
  "sedentary",
  "lightly_active",
  "moderately_active",
  "very_active",
  "extra_active",
] as const;
const GOAL_OPTIONS = ["cut", "maintain", "bulk"] as const;
const COOKING_OPTIONS = ["beginner", "intermediate", "advanced"] as const;

const profileFormSchema = z.object({
  user_id: z.string().trim().min(1, "Choose a profile name.").max(64),
  age: z.coerce.number().int().min(13).max(120),
  weight_lbs: z.coerce.number().positive(),
  height_in: z.coerce.number().positive(),
  sex: z.enum(SEX_OPTIONS),
  activity_level: z.enum(ACTIVITY_OPTIONS),
  goal: z.enum(GOAL_OPTIONS),
  dietary_restrictions_text: z.string().default(""),
  allergies_text: z.string().default(""),
  budget_weekly: z.coerce.number().positive(),
  household_size: z.coerce.number().int().min(1),
  cooking_skill: z.enum(COOKING_OPTIONS),
  weekday_dinners: z.string().default(""),
  weekend_cooking: z.string().default(""),
  schedule_notes: z.string().default(""),
});

type ProfileFormValues = z.infer<typeof profileFormSchema>;

type ProfileFormProps = {
  mode: "create" | "edit";
  initialUser?: UserProfileRead;
  submitLabel: string;
  onSubmit: (payload: UserProfileCreate | UserProfileUpdate) => Promise<void>;
};

const STEP_FIELDS: Array<Array<keyof ProfileFormValues>> = [
  ["user_id", "age", "weight_lbs", "height_in", "sex", "activity_level"],
  ["goal", "dietary_restrictions_text", "allergies_text"],
  ["budget_weekly", "household_size", "cooking_skill"],
  ["weekday_dinners", "weekend_cooking", "schedule_notes"],
];

const STEP_TITLES = ["Basics", "Goals", "Household", "Rhythm"];

const selectClassName =
  "flex h-12 w-full rounded-3xl border border-border bg-background/80 px-4 py-3 text-sm text-foreground shadow-[inset_0_1px_0_rgba(255,255,255,0.45)] transition-[border-color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/15 disabled:cursor-not-allowed disabled:opacity-60";

function buildDefaults(initialUser?: UserProfileRead): ProfileFormValues {
  return {
    user_id: initialUser?.user_id ?? "",
    age: initialUser?.age ?? 29,
    weight_lbs: initialUser?.weight_lbs ?? 170,
    height_in: initialUser?.height_in ?? 68,
    sex: initialUser?.sex ?? "female",
    activity_level: initialUser?.activity_level ?? "moderately_active",
    goal: initialUser?.goal ?? "maintain",
    dietary_restrictions_text: joinList(initialUser?.dietary_restrictions ?? []),
    allergies_text: joinList(initialUser?.allergies ?? []),
    budget_weekly: initialUser?.budget_weekly ?? 140,
    household_size: initialUser?.household_size ?? 1,
    cooking_skill: initialUser?.cooking_skill ?? "intermediate",
    weekday_dinners: initialUser?.schedule_json.weekday_dinners ?? "",
    weekend_cooking: initialUser?.schedule_json.weekend_cooking ?? "",
    schedule_notes: initialUser?.schedule_json.notes ?? "",
  };
}

export function ProfileForm({
  mode,
  initialUser,
  submitLabel,
  onSubmit,
}: ProfileFormProps) {
  const [currentStep, setCurrentStep] = useState(0);
  const {
    register,
    handleSubmit,
    reset,
    trigger,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: buildDefaults(initialUser),
  });

  useEffect(() => {
    reset(buildDefaults(initialUser));
  }, [initialUser, reset]);

  const values = watch();

  const handleNext = async () => {
    const isValid = await trigger(STEP_FIELDS[currentStep], { shouldFocus: true });
    if (isValid) {
      setCurrentStep((step) => Math.min(step + 1, STEP_FIELDS.length - 1));
    }
  };

  const submit = handleSubmit(async (formValues) => {
    const payload = {
      age: formValues.age,
      weight_lbs: formValues.weight_lbs,
      height_in: formValues.height_in,
      sex: formValues.sex,
      activity_level: formValues.activity_level,
      goal: formValues.goal,
      dietary_restrictions: splitListInput(formValues.dietary_restrictions_text),
      allergies: splitListInput(formValues.allergies_text),
      budget_weekly: formValues.budget_weekly,
      household_size: formValues.household_size,
      cooking_skill: formValues.cooking_skill,
      schedule_json: {
        ...(formValues.weekday_dinners ? { weekday_dinners: formValues.weekday_dinners } : {}),
        ...(formValues.weekend_cooking ? { weekend_cooking: formValues.weekend_cooking } : {}),
        ...(formValues.schedule_notes ? { notes: formValues.schedule_notes } : {}),
      },
    };

    if (mode === "create") {
      await onSubmit({
        user_id: formValues.user_id.trim(),
        ...payload,
      });
      return;
    }

    await onSubmit(payload);
  });

  return (
    <div className="space-y-4">
      <Tabs
        className="space-y-4"
        onValueChange={(value) => setCurrentStep(Number(value))}
        value={String(currentStep)}
      >
        <TabsList className="grid w-full grid-cols-2 gap-2 md:grid-cols-4">
          {STEP_TITLES.map((title, index) => (
            <TabsTrigger key={title} className="justify-start" value={String(index)}>
              <span className="grid h-7 w-7 place-items-center rounded-full border border-border bg-background text-xs font-semibold">
                {index + 1}
              </span>
              {title}
            </TabsTrigger>
          ))}
        </TabsList>

        <form className="grid gap-4 xl:grid-cols-[1.6fr_0.85fr]" onSubmit={submit}>
          <Card>
            <CardContent className="p-5 md:p-6">
              <TabsContent className="mt-0" value="0">
                <section className="grid gap-4 md:grid-cols-2">
                  <Field
                    disabled={mode === "edit"}
                    error={errors.user_id?.message}
                    hint="Used as the local profile handle for this phase."
                    label="Profile name"
                  >
                    <Input
                      {...register("user_id")}
                      disabled={mode === "edit"}
                      placeholder="michael"
                    />
                  </Field>
                  <Field error={errors.age?.message} label="Age">
                    <Input {...register("age")} min={13} type="number" />
                  </Field>
                  <Field error={errors.weight_lbs?.message} label="Weight (lb)">
                    <Input {...register("weight_lbs")} min={1} step="0.1" type="number" />
                  </Field>
                  <Field error={errors.height_in?.message} label="Height (in)">
                    <Input {...register("height_in")} min={1} step="0.1" type="number" />
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
                  <Field error={errors.activity_level?.message} label="Activity level">
                    <select {...register("activity_level")} className={selectClassName}>
                      {ACTIVITY_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {formatLabel(option)}
                        </option>
                      ))}
                    </select>
                  </Field>
                </section>
              </TabsContent>

              <TabsContent className="mt-0" value="1">
                <section className="grid gap-4 md:grid-cols-2">
                  <Field error={errors.goal?.message} label="Primary goal">
                    <select {...register("goal")} className={selectClassName}>
                      {GOAL_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {formatLabel(option)}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field
                    className="md:col-span-2"
                    error={errors.dietary_restrictions_text?.message}
                    hint="Comma-separated, like vegetarian, halal."
                    label="Dietary restrictions"
                  >
                    <Textarea {...register("dietary_restrictions_text")} rows={4} />
                  </Field>
                  <Field
                    className="md:col-span-2"
                    error={errors.allergies_text?.message}
                    hint="Comma-separated hard exclusions."
                    label="Allergies"
                  >
                    <Textarea {...register("allergies_text")} rows={4} />
                  </Field>
                </section>
              </TabsContent>

              <TabsContent className="mt-0" value="2">
                <section className="grid gap-4 md:grid-cols-2">
                  <Field error={errors.budget_weekly?.message} label="Weekly grocery budget">
                    <Input {...register("budget_weekly")} min={1} step="1" type="number" />
                  </Field>
                  <Field error={errors.household_size?.message} label="Household size">
                    <Input {...register("household_size")} min={1} type="number" />
                  </Field>
                  <Field className="md:col-span-2" error={errors.cooking_skill?.message} label="Cooking comfort">
                    <select {...register("cooking_skill")} className={selectClassName}>
                      {COOKING_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {formatLabel(option)}
                        </option>
                      ))}
                    </select>
                  </Field>
                </section>
              </TabsContent>

              <TabsContent className="mt-0" value="3">
                <section className="grid gap-4">
                  <Field
                    error={errors.weekday_dinners?.message}
                    hint="Example: 30 minutes, meal prep, quick skillet."
                    label="Weekday dinner style"
                  >
                    <Input {...register("weekday_dinners")} placeholder="30 minutes max" />
                  </Field>
                  <Field
                    error={errors.weekend_cooking?.message}
                    hint="Example: longer prep, family-style, flexible."
                    label="Weekend cooking style"
                  >
                    <Input {...register("weekend_cooking")} placeholder="Flexible and fun" />
                  </Field>
                  <Field
                    error={errors.schedule_notes?.message}
                    hint="Anything the planner should remember this week."
                    label="Weekly notes"
                  >
                    <Textarea {...register("schedule_notes")} rows={4} />
                  </Field>
                </section>
              </TabsContent>

              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Button
                  disabled={currentStep === 0 || isSubmitting}
                  onClick={() => setCurrentStep((step) => Math.max(step - 1, 0))}
                  type="button"
                  variant="outline"
                >
                  Back
                </Button>
                {currentStep < STEP_FIELDS.length - 1 ? (
                  <Button disabled={isSubmitting} onClick={handleNext} type="button">
                    Next step
                  </Button>
                ) : (
                  <Button disabled={isSubmitting} type="submit">
                    {isSubmitting ? "Saving..." : submitLabel}
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          <Card className="h-fit">
            <CardContent className="space-y-5 p-5 md:p-6">
              <div className="space-y-2">
                <p className="text-[0.72rem] uppercase tracking-[0.18em] text-muted-foreground">
                  Live summary
                </p>
                <h3 className="font-display text-3xl">{values.user_id || "New profile"}</h3>
                <p className="text-sm leading-6 text-muted-foreground">
                  Phase 1 uses this profile to calculate calories, macros, and a seven-day
                  starter meal plan.
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <SummaryMetric label="Goal" value={formatLabel(values.goal)} />
                <SummaryMetric label="Activity" value={formatLabel(values.activity_level)} />
                <SummaryMetric label="Budget" value={`$${values.budget_weekly || 0}/wk`} />
                <SummaryMetric label="Household" value={String(values.household_size)} />
              </div>

              <div className="space-y-3 rounded-[1.5rem] border border-border bg-background/70 p-4">
                <p className="text-sm font-semibold">Preview signals</p>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="secondary">{formatLabel(values.goal)}</Badge>
                  <Badge variant="outline">{formatLabel(values.cooking_skill)}</Badge>
                  {splitListInput(values.dietary_restrictions_text).slice(0, 2).map((item) => (
                    <Badge key={item}>{item}</Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </form>
      </Tabs>
    </div>
  );
}

type FieldProps = {
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  error?: string;
  hint?: string;
  label: string;
};

function Field({ children, className, disabled, error, hint, label }: FieldProps) {
  return (
    <div className={cn("space-y-2", className)}>
      <Label className={disabled ? "opacity-70" : undefined}>{label}</Label>
      {children}
      {hint ? <p className="text-sm leading-6 text-muted-foreground">{hint}</p> : null}
      {error ? <p className="text-sm font-medium text-accent-foreground">{error}</p> : null}
    </div>
  );
}

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1.4rem] border border-border bg-background/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
      <span className="block text-sm text-muted-foreground">{label}</span>
      <strong className="mt-1 block text-lg">{value}</strong>
    </div>
  );
}
