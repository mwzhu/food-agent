export type SupplementSex = "female" | "male" | "other";
export type SupplementRunEventType =
  | "phase_started"
  | "phase_completed"
  | "node_entered"
  | "node_completed"
  | "approval_requested"
  | "approval_resolved"
  | "run_completed"
  | "error";
export type SupplementPhaseName = "memory" | "discovery" | "analysis" | "checkout";
export type SupplementPhaseStatus = "pending" | "running" | "completed" | "locked" | "failed";
export type SupplementRunLifecycleStatus = "pending" | "running" | "awaiting_approval" | "completed" | "failed";
export type SupplementCriticDecision = "passed" | "manual_review_needed" | "failed";
export type SupplementCriticConcern = "safety" | "goal_alignment" | "value";

export interface HealthProfile {
  age: number;
  weight_lbs: number;
  sex: SupplementSex;
  health_goals: string[];
  current_supplements: string[];
  medications: string[];
  conditions: string[];
  allergies: string[];
  monthly_budget: number;
}

export interface SupplementNeed {
  category: string;
  goal: string;
  rationale: string;
  search_queries: string[];
  priority: number;
}

export interface ShopifyPriceRange {
  min_price: number | null;
  max_price: number | null;
  currency: string;
}

export interface ShopifyProductVariant {
  variant_id: string;
  title: string;
  price: number | null;
  currency: string;
  available: boolean;
  image_url: string | null;
}

export interface ShopifyProduct {
  store_domain: string;
  product_id: string;
  title: string;
  description: string;
  url: string;
  image_url: string | null;
  image_alt_text: string | null;
  product_type: string;
  tags: string[];
  price_range: ShopifyPriceRange;
  variants: ShopifyProductVariant[];
}

export interface StoreSearchResult {
  store_domain: string;
  query: string;
  products: ShopifyProduct[];
}

export interface CategoryDiscoveryResult {
  category: string;
  goal: string;
  search_queries: string[];
  store_results: StoreSearchResult[];
}

export interface IngredientAnalysis {
  primary_ingredients: string[];
  dosage_summary: string;
  bioavailability_notes: string[];
  allergens: string[];
  serving_size: string | null;
  servings_per_container: number | null;
  price_per_serving: number | null;
  notes: string[];
}

export interface ComparedProduct {
  product: ShopifyProduct;
  ingredient_analysis: IngredientAnalysis;
  rank: number;
  score: number | null;
  rationale: string;
  pros: string[];
  cons: string[];
  warnings: string[];
  monthly_cost: number | null;
}

export interface ProductComparison {
  category: string;
  goal: string;
  summary: string;
  ranked_products: ComparedProduct[];
  top_pick_product_id: string | null;
  top_pick_store_domain: string | null;
}

export interface StackItem {
  category: string;
  goal: string;
  product: ShopifyProduct;
  quantity: number;
  dosage: string;
  cadence: string;
  monthly_cost: number | null;
  rationale: string;
  cautions: string[];
}

export interface SupplementStack {
  summary: string;
  items: StackItem[];
  total_monthly_cost: number | null;
  currency: string;
  within_budget: boolean | null;
  notes: string[];
  warnings: string[];
}

export interface StoreCartLine {
  line_id: string;
  product_id: string;
  product_title: string;
  variant_id: string;
  variant_title: string;
  quantity: number;
  subtotal_amount: number | null;
  total_amount: number | null;
  currency: string | null;
}

export interface StoreCart {
  store_domain: string;
  cart_id: string | null;
  checkout_url: string | null;
  total_quantity: number;
  subtotal_amount: number | null;
  total_amount: number | null;
  currency: string | null;
  lines: StoreCartLine[];
  errors: Array<Record<string, unknown>>;
  instructions: string | null;
}

export interface SupplementCriticFinding {
  concern: SupplementCriticConcern;
  severity: "issue" | "warning";
  message: string;
}

export interface SupplementCriticVerdict {
  decision: SupplementCriticDecision;
  summary: string;
  issues: string[];
  warnings: string[];
  findings: SupplementCriticFinding[];
  manual_review_reason: string | null;
}

export interface SupplementPhaseStatuses {
  memory: SupplementPhaseStatus;
  discovery: SupplementPhaseStatus;
  analysis: SupplementPhaseStatus;
  checkout: SupplementPhaseStatus;
}

export interface SupplementTraceMetadata {
  kind: string | null;
  project: string | null;
  trace_id: string | null;
  source: string | null;
}

export interface SupplementStateSnapshot {
  run_id: string;
  user_id: string;
  health_profile: HealthProfile;
  identified_needs: SupplementNeed[];
  discovery_results: CategoryDiscoveryResult[];
  product_comparisons: ProductComparison[];
  recommended_stack: SupplementStack | null;
  critic_verdict: SupplementCriticVerdict | null;
  store_carts: StoreCart[];
  approved_store_domains: string[];
  status: SupplementRunLifecycleStatus;
  current_node: string;
  current_phase: SupplementPhaseName | null;
  phase_statuses: SupplementPhaseStatuses;
  replan_count: number;
  latest_error: string | null;
  trace_metadata: SupplementTraceMetadata;
}

export interface SupplementRunCreateRequest {
  user_id: string;
  health_profile: HealthProfile;
}

export interface SupplementRunApproveRequest {
  approved_store_domains: string[];
}

export interface SupplementRunRead {
  run_id: string;
  user_id: string;
  status: SupplementRunLifecycleStatus;
  state_snapshot: SupplementStateSnapshot;
  created_at: string;
  updated_at: string;
}

interface BaseSupplementRunEvent {
  event_id: string;
  run_id: string;
  message: string;
  phase: SupplementPhaseName | null;
  node_name: string | null;
  created_at: string;
  data: Record<string, unknown>;
}

export interface SupplementPhaseStartedEvent extends BaseSupplementRunEvent {
  event_type: "phase_started";
  phase: SupplementPhaseName;
}

export interface SupplementPhaseCompletedEvent extends BaseSupplementRunEvent {
  event_type: "phase_completed";
  phase: SupplementPhaseName;
}

export interface SupplementNodeEnteredEvent extends BaseSupplementRunEvent {
  event_type: "node_entered";
}

export interface SupplementNodeCompletedEvent extends BaseSupplementRunEvent {
  event_type: "node_completed";
}

export interface SupplementApprovalRequestedEvent extends BaseSupplementRunEvent {
  event_type: "approval_requested";
}

export interface SupplementApprovalResolvedEvent extends BaseSupplementRunEvent {
  event_type: "approval_resolved";
}

export interface SupplementRunCompletedEvent extends BaseSupplementRunEvent {
  event_type: "run_completed";
  data: {
    status: Extract<SupplementRunLifecycleStatus, "completed" | "failed">;
    decision?: SupplementCriticDecision;
    approved_store_domains?: string[];
  };
}

export interface SupplementRunErrorEvent extends BaseSupplementRunEvent {
  event_type: "error";
}

export type SupplementRunEvent =
  | SupplementPhaseStartedEvent
  | SupplementPhaseCompletedEvent
  | SupplementNodeEnteredEvent
  | SupplementNodeCompletedEvent
  | SupplementApprovalRequestedEvent
  | SupplementApprovalResolvedEvent
  | SupplementRunCompletedEvent
  | SupplementRunErrorEvent;
