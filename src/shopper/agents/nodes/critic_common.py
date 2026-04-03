from __future__ import annotations

from typing import Iterable, List, Literal

from pydantic import BaseModel, Field

from shopper.schemas import CriticFinding


class CriticAssessment(BaseModel):
    passed: bool = True
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    repair_instructions: List[str] = Field(default_factory=list)


def build_findings(
    code: str,
    messages: Iterable[str],
    *,
    severity: Literal["issue", "warning"],
) -> list[CriticFinding]:
    return [
        CriticFinding(code=code, severity=severity, message=message)
        for message in messages
        if message
    ]


def dedupe_strings(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def dedupe_findings(findings: Iterable[CriticFinding]) -> list[CriticFinding]:
    deduped: dict[tuple[str, str, str], CriticFinding] = {}
    for finding in findings:
        deduped[(finding.code, finding.severity, finding.message)] = finding
    return list(deduped.values())
