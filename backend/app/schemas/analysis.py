from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..tools.github_client import parse_repo_url

DEFAULT_TASK = "Find bugs in this repository, fix the most critical issue, and create tests to verify the fix."


class InspectRequest(BaseModel):
    repository_url: str

    @field_validator("repository_url")
    @classmethod
    def _valid_url(cls, v: str) -> str:
        parse_repo_url(v)  # raises ValueError -> HTTP 422
        return v.strip()


class AnalysisRequest(InspectRequest):
    task: str = Field(default=DEFAULT_TASK, max_length=1000)


class ApprovalRequest(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=500)


Severity = Literal["critical", "high", "medium", "low", "info"]


class Finding(BaseModel):
    id: str
    title: str
    severity: Severity
    category: str
    path: str
    line: int
    details: str
    evidence: str = ""
    rule_id: str = ""
    source: Literal["ast", "ruff", "bandit"]
    confirmed: bool = False  # True only when the tool proves it (e.g. a syntax error)
    next_step: str = ""
    priority_score: float = 0.0
    ml_severity: str | None = None
    llm_verdict: Literal["likely_bug", "possible_false_positive", "style_only"] | None = None
    llm_explanation: str | None = None
