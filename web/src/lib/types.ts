export type Sex = "female" | "male" | "other";
export type ActivityLevel =
  | "sedentary"
  | "lightly_active"
  | "moderately_active"
  | "very_active"
  | "extra_active";
export type Goal = "cut" | "maintain" | "bulk";
export type CookingSkill = "beginner" | "intermediate" | "advanced";
export type MealType = "breakfast" | "lunch" | "dinner";
export type RunStatus = "running" | "completed";

export interface UserProfileBase {
  age: number;
  weight_lbs: number;
  height_in: number;
  sex: Sex;
  activity_level: ActivityLevel;
  goal: Goal;
  dietary_restrictions: string[];
  allergies: string[];
  budget_weekly: number;
  household_size: number;
  cooking_skill: CookingSkill;
  schedule_json: Record<string, string>;
}

export interface UserProfileCreate extends UserProfileBase {
  user_id: string;
}

export type UserProfileUpdate = Partial<UserProfileBase>;

export interface UserProfileRead extends UserProfileBase {
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface NutritionPlan {
  tdee: number;
  daily_calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  goal: Goal;
  applied_restrictions: string[];
  notes: string;
}

export interface MealSlot {
  day: string;
  meal_type: MealType;
  recipe_id: string;
  recipe_name: string;
  prep_time_min: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
}

export interface ContextMetadata {
  node_name: string;
  tokens_used: number;
  token_budget: number;
  fields_included: string[];
  fields_dropped: string[];
  retrieved_memory_ids: string[];
}

export interface PlannerStateSnapshot {
  run_id: string;
  user_id: string;
  user_profile: Record<string, unknown>;
  nutrition_plan: NutritionPlan | null;
  selected_meals: MealSlot[];
  context_metadata: ContextMetadata[];
  status: "pending" | "completed";
  current_node: "created" | "supervisor" | "planning_subgraph";
  trace_metadata: Record<string, string | undefined>;
}

export interface RunCreateRequest {
  user_id: string;
  profile: UserProfileBase;
}

export interface RunRead {
  run_id: string;
  user_id: string;
  status: RunStatus;
  state_snapshot: PlannerStateSnapshot;
  created_at: string;
  updated_at: string;
}

export interface RunTraceRead {
  run_id: string;
  kind: string | null;
  project: string | null;
  trace_id: string | null;
  source: string | null;
  url: string | null;
}
