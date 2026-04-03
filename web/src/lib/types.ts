export type Sex = "female" | "male" | "other";
export type ActivityLevel =
  | "sedentary"
  | "lightly_active"
  | "moderately_active"
  | "very_active"
  | "extra_active";
export type Goal = "cut" | "maintain" | "bulk";
export type CookingSkill = "beginner" | "intermediate" | "advanced";
export type MealType = "breakfast" | "lunch" | "dinner" | "snack";
export type InventoryCategory = "produce" | "dairy" | "meat" | "pantry" | "frozen";
export type RunEventType =
  | "phase_started"
  | "phase_completed"
  | "node_entered"
  | "node_completed"
  | "run_completed"
  | "error";
export type PhaseName = "memory" | "planning" | "shopping" | "checkout";
export type PhaseStatus = "pending" | "running" | "completed" | "locked" | "failed";
export type RunLifecycleStatus = "pending" | "running" | "completed" | "failed";
export type RunStatus = Exclude<RunLifecycleStatus, "pending">;

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

export interface RecipeIngredient {
  name: string;
  quantity: number | null;
  unit: string | null;
  note: string;
}

export interface RecipeRecord {
  recipe_id: string;
  name: string;
  cuisine: string;
  meal_types: MealType[];
  ingredients: RecipeIngredient[];
  prep_time_min: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  tags: string[];
  instructions: string[];
  source_url: string | null;
}

export interface PreferenceSummary {
  preferred_cuisines: string[];
  avoided_ingredients: string[];
  preferred_meal_types: string[];
  notes: string[];
}

export interface MealSlot {
  day: string;
  meal_type: MealType;
  recipe_id: string;
  recipe_name: string;
  cuisine: string;
  prep_time_min: number;
  serving_multiplier: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  tags: string[];
  macro_fit_score: number;
  recipe: RecipeRecord | null;
}

export interface CriticVerdict {
  passed: boolean;
  issues: string[];
  warnings: string[];
  repair_instructions: string[];
}

export interface GroceryItem {
  name: string;
  quantity: number;
  unit: string | null;
  category: InventoryCategory;
  already_have: boolean;
  shopping_quantity: number;
  quantity_in_fridge: number;
  source_recipe_ids: string[];
}

export interface FridgeItemBase {
  name: string;
  quantity: number;
  unit: string | null;
  category: InventoryCategory;
  expiry_date: string | null;
}

export interface FridgeItemCreate extends FridgeItemBase {}

export type FridgeItemUpdate = Partial<FridgeItemBase>;

export interface FridgeItemSnapshot extends FridgeItemBase {
  item_id: number;
  user_id: string;
}

export interface FridgeItemRead extends FridgeItemSnapshot {
  created_at: string;
  updated_at: string;
}

export interface ContextMetadata {
  node_name: string;
  tokens_used: number;
  token_budget: number;
  fields_included: string[];
  fields_dropped: string[];
  retrieved_memory_ids: string[];
}

export interface MemorySnapshot {
  memory_id: string;
  user_id: string;
  category: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface PhaseStatuses {
  memory: PhaseStatus;
  planning: PhaseStatus;
  shopping: PhaseStatus;
  checkout: PhaseStatus;
}

export interface TraceMetadata {
  kind: string | null;
  project: string | null;
  trace_id: string | null;
  source: string | null;
}

interface BaseRunEvent {
  event_id: string;
  run_id: string;
  message: string;
  phase: PhaseName | null;
  node_name: string | null;
  created_at: string;
  data: Record<string, unknown>;
}

export interface PhaseStartedEvent extends BaseRunEvent {
  event_type: "phase_started";
  phase: PhaseName;
}

export interface PhaseCompletedEvent extends BaseRunEvent {
  event_type: "phase_completed";
  phase: PhaseName;
}

export interface NodeEnteredEvent extends BaseRunEvent {
  event_type: "node_entered";
}

export interface NodeCompletedEvent extends BaseRunEvent {
  event_type: "node_completed";
}

export interface RunCompletedEvent extends BaseRunEvent {
  event_type: "run_completed";
  data: {
    status: Extract<RunLifecycleStatus, "completed" | "failed">;
  };
}

export interface RunErrorEvent extends BaseRunEvent {
  event_type: "error";
}

export type RunEvent =
  | PhaseStartedEvent
  | PhaseCompletedEvent
  | NodeEnteredEvent
  | NodeCompletedEvent
  | RunCompletedEvent
  | RunErrorEvent;

export interface PlannerStateSnapshot {
  run_id: string;
  user_id: string;
  user_profile: UserProfileBase;
  nutrition_plan: NutritionPlan | null;
  selected_meals: MealSlot[];
  grocery_list: GroceryItem[];
  fridge_inventory: FridgeItemSnapshot[];
  user_preferences_learned: PreferenceSummary;
  retrieved_memories: MemorySnapshot[];
  critic_verdict: CriticVerdict | null;
  repair_instructions: string[];
  context_metadata: ContextMetadata[];
  status: RunLifecycleStatus;
  current_node: string;
  current_phase: PhaseName | null;
  phase_statuses: PhaseStatuses;
  replan_count: number;
  latest_error: string | null;
  trace_metadata: TraceMetadata;
}

export interface RunCreateRequest {
  user_id: string;
  profile: UserProfileBase;
}

export interface RunRead {
  run_id: string;
  user_id: string;
  status: RunLifecycleStatus;
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
