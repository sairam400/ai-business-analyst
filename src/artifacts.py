"""Pydantic models for everything that crosses an agent-stage boundary.
These get serialized straight to the run directory, so a run is fully
inspectable after the fact -- and they're what the verifier re-checks
the writer's prose against."""
from typing import Literal

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    sql_type: Literal["integer", "float", "text", "date"]
    null_count: int
    null_pct: float
    distinct_count: int
    sample_values: list = Field(default_factory=list)
    is_id_like: bool = False


class TableProfile(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnProfile]


class DatasetProfile(BaseModel):
    tables: list[TableProfile]
    detected_relationships: list[str] = Field(default_factory=list)
    data_quality_notes: list[str] = Field(default_factory=list)
    suggested_analyses: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    id: str
    question: str
    method: Literal["sql", "python"]
    query: str
    value: float | int | str
    unit: str = ""
    chart_id: str | None = None


class AnalystArtifact(BaseModel):
    profile: DatasetProfile
    findings: list[Finding]
    failed_tasks: list[str] = Field(default_factory=list)


class ReportSection(BaseModel):
    heading: str
    body: str  # prose with inline footnote markers like [F1]


class Draft(BaseModel):
    executive_summary: str
    sections: list[ReportSection]


class VerifierVerdict(BaseModel):
    finding_id: str
    claimed_value: float | int | str
    recomputed_value: float | int | str | None
    passed: bool
    reason: str = ""


class RemovedClaim(BaseModel):
    finding_id: str
    reason: str


class VerifiedReport(BaseModel):
    executive_summary: str
    sections: list[ReportSection]
    findings: list[Finding]
    verdicts: list[VerifierVerdict]
    removed_claims: list[RemovedClaim] = Field(default_factory=list)
