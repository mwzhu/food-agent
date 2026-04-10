from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Sex = Literal["female", "male", "other"]


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("value must be a list of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


class SupplementNeed(BaseModel):
    category: str
    goal: str
    rationale: str = ""
    search_queries: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("search_queries", mode="before")
    @classmethod
    def _normalize_search_queries(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


class HealthProfile(BaseModel):
    age: int = Field(ge=0, le=130)
    weight_lbs: float = Field(gt=0)
    sex: Sex
    health_goals: list[str] = Field(min_length=1)
    current_supplements: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    monthly_budget: float = Field(ge=0)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator(
        "health_goals",
        "current_supplements",
        "medications",
        "conditions",
        "allergies",
        mode="before",
    )
    @classmethod
    def _normalize_lists(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)
