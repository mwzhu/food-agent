import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import type {
  FridgeItemRead,
  GroceryItem,
  MealSlot,
  UserProfileBase,
  UserProfileRead,
} from "@/lib/types";

const DAY_ORDER = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

const MEAL_ORDER = ["breakfast", "lunch", "dinner", "snack"];

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatCurrency(
  value: number,
  options: { minimumFractionDigits?: number; maximumFractionDigits?: number } = {},
): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
    maximumFractionDigits: options.maximumFractionDigits ?? 2,
  }).format(value);
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export function formatDate(value: string): string {
  const date = parseDateValue(value);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(date);
}

export function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.round(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (!minutes) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatQuantity(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, "");
}

export function splitListInput(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function joinList(values: string[]): string {
  return values.join(", ");
}

export function toUserProfileBase(user: UserProfileRead): UserProfileBase {
  const { user_id: _userId, created_at: _createdAt, updated_at: _updatedAt, ...profile } = user;
  return profile;
}

export function groupMealsByDay(meals: MealSlot[]): Array<{ day: string; meals: MealSlot[] }> {
  const groups = new Map<string, MealSlot[]>();

  for (const day of DAY_ORDER) {
    groups.set(day, []);
  }

  for (const meal of meals) {
    const current = groups.get(meal.day) ?? [];
    current.push(meal);
    groups.set(meal.day, current);
  }

  return DAY_ORDER.map((day) => ({
    day,
    meals: (groups.get(day) ?? []).sort(
      (left, right) => MEAL_ORDER.indexOf(left.meal_type) - MEAL_ORDER.indexOf(right.meal_type),
    ),
  }));
}

export function groupGroceryItemsByCategory(items: GroceryItem[]): Array<{ category: GroceryItem["category"]; items: GroceryItem[] }> {
  const categoryOrder: GroceryItem["category"][] = ["produce", "dairy", "meat", "pantry", "frozen"];
  return categoryOrder.map((category) => ({
    category,
    items: items.filter((item) => item.category === category),
  }));
}

export function inventoryExpiryTone(item: FridgeItemRead): "default" | "warning" | "danger" {
  if (!item.expiry_date) {
    return "default";
  }
  const expiry = parseDateValue(item.expiry_date);
  const now = new Date();
  const daysUntilExpiry = Math.ceil((expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (daysUntilExpiry < 0) {
    return "danger";
  }
  if (daysUntilExpiry <= 3) {
    return "warning";
  }
  return "default";
}

function parseDateValue(value: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  return new Date(value);
}

export function scheduleValue(
  schedule: Record<string, string>,
  key: string,
): string {
  return schedule[key] ?? "";
}

export function macroFitTone(score: number): {
  badgeLabel: string;
  accentClass: string;
  surfaceClass: string;
} {
  if (score >= 0.82) {
    return {
      badgeLabel: "On target",
      accentClass: "text-success",
      surfaceClass: "border-success/30 bg-success-soft/60",
    };
  }
  if (score >= 0.65) {
    return {
      badgeLabel: "Close",
      accentClass: "text-[color:var(--chart-2)]",
      surfaceClass: "border-[color:rgba(212,131,70,0.35)] bg-[rgba(212,131,70,0.10)]",
    };
  }
  return {
    badgeLabel: "Needs tuning",
    accentClass: "text-accent-foreground",
    surfaceClass: "border-primary/25 bg-accent/55",
  };
}
