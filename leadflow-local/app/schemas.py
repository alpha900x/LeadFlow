from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LeadAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    industry: str = Field(min_length=1, max_length=120)
    niche: str = Field(min_length=1, max_length=160)
    lead_score: int = Field(ge=1, le=100)
    summary: str = Field(min_length=1, max_length=1200)
    outreach_email: str = Field(min_length=1, max_length=4000)


class CsvImportInput(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)


class CompanyOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    website_url: str
    company_name: str | None
    status: str
    lead_score: int | None
    industry: str | None
    niche: str | None
    summary: str | None
    outreach_email: str | None
    page_title: str | None
    meta_description: str | None
    headings: list[str]
    pricing_page_found: bool
    emails: list[str]
    phones: list[str]
    internal_links: list[str]
    ai_provider: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ImportResult(BaseModel):
    imported: int
    skipped: int
    companies: list[CompanyOutput]


class DashboardOutput(BaseModel):
    total_companies: int
    pending: int
    processing: int
    completed: int
    failed: int
    average_score: float | None
    recent_companies: list[CompanyOutput]


class HealthOutput(BaseModel):
    status: str
    ai_configured: bool
    ai_provider: str | None
