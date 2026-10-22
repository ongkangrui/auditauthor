from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "1.1"
SCHEMA_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Theme(str, Enum):
    ACCESS = "access management"
    PRIVILEGED = "privileged access"
    LOGGING = "logging/monitoring"
    CHANGE = "change management"
    RESILIENCE = "resilience"
    APPLICATION = "application controls"
    DATA = "data protection"
    THIRD_PARTY = "third-party technology risk"
    OTHER = "other IT controls"


class Evidence(StrictModel):
    page: int = Field(ge=1)
    excerpt: str = Field(min_length=20)


class Observation(StrictModel):
    title: str = Field(min_length=3)
    agency: str | None
    system: str | None
    theme: Theme
    weakness: str
    risk: str | None
    reported_remediation: str | None
    evidence: list[Evidence] = Field(min_length=1)
    source_kind: Literal["detail", "overview"]


class Extraction(StrictModel):
    observations: list[Observation]


class Finding(Observation):
    id: str
    report_id: str


class InsightDraft(StrictModel):
    theme: Theme
    weakness: str
    audit_implication: str
    observation_ids: list[str] = Field(min_length=1)


class Consolidation(StrictModel):
    insights: list[InsightDraft]
    duplicate_groups: list[list[str]]


class AnalysisRequest(StrictModel):
    report_ids: list[str] = Field(min_length=1, max_length=20)


class ReportSummary(StrictModel):
    id: str
    sha256: str
    name: str
    source_url: str | None
    page_count: int


class PageText(StrictModel):
    number: int = Field(ge=1)
    text: str
    warning: str | None


class Report(ReportSummary):
    pages: list[PageText]


class Coverage(StrictModel):
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    total_pages: int = 0
    page_warnings: list[dict] = Field(default_factory=list)


class AnalysisSummary(StrictModel):
    id: str
    report_ids: list[str]
    status: Literal["queued", "running", "complete", "partial", "failed", "interrupted"]
    created_at: str
    updated_at: str
    model: str
    resolved_models: list[str]
    prompt_version: str
    schema_version: str
    chunk_chars: int
    overlap_chars: int
    errors: list[dict]
    history: list[dict]
    coverage: Coverage


class Insight(InsightDraft):
    id: str
    report_ids: list[str]
    report_count: int
    agencies: list[str]
    agency_count: int
    recurring: bool
    cross_agency: bool
    repeated_entities: list[dict[str, str | None]]
