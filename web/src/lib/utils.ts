import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import type { MealSlot, UserProfileBase, UserProfileRead } from "@/lib/types";

const DAY_ORDER = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

const MEAL_ORDER = ["breakfast", "lunch", "dinner"];

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
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

export function scheduleValue(
  schedule: Record<string, string>,
  key: string,
): string {
  return schedule[key] ?? "";
}
