import asyncio
import csv
import io
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Base, SessionLocal, engine, get_session
from .enrichment import analyze_company, groq_configured
from .models import Company
from .schemas import (
    CompanyOutput,
    CsvImportInput,
    DashboardOutput,
    HealthOutput,
    ImportResult,
)
from .scraper import scrape_website

API_PREFIX = "/api/leadflow"
COMPANY_HEADERS = {
    "domain",
    "website",
    "website_url",
    "company_website",
    "company website",
    "url",
    "company_url",
    "domain_name",
}
DOMAIN_LABEL = re.compile(r"^[a-z0-9.-]+$", re.IGNORECASE)
PROCESSING_TASKS: dict[int, asyncio.Task] = {}
PROCESSING_LIMIT = asyncio.Semaphore(3)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        pending = await session.scalars(
            select(Company.id).where(Company.status.in_(["pending", "processing"]))
        )
        pending_ids = list(pending)
        if pending_ids:
            await session.execute(
                update(Company)
                .where(Company.id.in_(pending_ids))
                .values(status="pending", error_message=None)
            )
            await session.commit()
    for company_id in pending_ids:
        schedule_company(company_id)
    yield
    tasks = list(PROCESSING_TASKS.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await engine.dispose()


app = FastAPI(title="LeadFlow API", version="1.0.0", lifespan=lifespan)


def schedule_company(company_id: int) -> None:
    current = PROCESSING_TASKS.get(company_id)
    if current and not current.done():
        return
    task = asyncio.create_task(process_company(company_id))
    PROCESSING_TASKS[company_id] = task

    def remove_finished(done_task: asyncio.Task, key: int = company_id) -> None:
        if PROCESSING_TASKS.get(key) is done_task:
            PROCESSING_TASKS.pop(key, None)

    task.add_done_callback(remove_finished)


async def process_company(company_id: int) -> None:
    try:
        async with PROCESSING_LIMIT:
            async with SessionLocal() as session:
                company = await session.get(Company, company_id)
                if company is None or company.status not in {"pending", "failed"}:
                    return
                company.status = "processing"
                company.error_message = None
                await session.commit()
                company_data = {
                    "id": company.id,
                    "domain": company.domain,
                    "website_url": company.website_url,
                }

            scraped = await scrape_website(company_data["website_url"])
            analysis = await analyze_company(company_data, scraped)

            async with SessionLocal() as session:
                company = await session.get(Company, company_id)
                if company is None:
                    return
                company.company_name = scraped.get("page_title") or company.domain
                company.page_title = scraped.get("page_title")
                company.meta_description = scraped.get("meta_description")
                company.headings = scraped.get("headings", [])
                company.pricing_page_found = scraped.get("pricing_page_found", False)
                company.emails = scraped.get("emails", [])
                company.phones = scraped.get("phones", [])
                company.internal_links = scraped.get("internal_links", [])
                company.lead_score = analysis.lead_score
                company.industry = analysis.industry
                company.niche = analysis.niche
                company.summary = analysis.summary
                company.outreach_email = analysis.outreach_email
                company.ai_provider = f"Groq · {os.getenv('GROQ_MODEL', 'openai/gpt-oss-120b')}"
                company.status = "completed"
                company.error_message = None
                await session.commit()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        error_details = str(error)
        if len(error_details) > 2_500:
            error_details = (
                f"{error_details[:350]}\n… middle omitted …\n{error_details[-2_100:]}"
            )
        async with SessionLocal() as session:
            company = await session.get(Company, company_id)
            if company is not None:
                company.status = "failed"
                company.error_message = error_details[:2_500]
                await session.commit()


def normalize_website(raw_value: str) -> tuple[str, str] | None:
    raw = raw_value.strip().strip("\"'<>")
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return None
    host = parts.hostname.lower().rstrip(".")
    if not DOMAIN_LABEL.fullmatch(host) or "." not in host or len(host) > 253:
        return None
    if host == "localhost" or host.endswith((".localhost", ".local")):
        return None
    domain = host.removeprefix("www.")
    website_url = raw if parts.scheme == "https" else raw.replace("http://", "https://", 1)
    return domain, website_url


def extract_domains(csv_text: str) -> list[tuple[str, str]]:
    try:
        rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"))))
    except csv.Error as error:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {error}") from error
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise HTTPException(status_code=400, detail="The CSV is empty.")

    normalized_headers = [cell.strip().lower().replace(" ", "_") for cell in rows[0]]
    column = next(
        (index for index, header in enumerate(normalized_headers) if header in COMPANY_HEADERS),
        0,
    )
    has_header = any(
        cell.strip().lower().replace(" ", "_") in COMPANY_HEADERS for cell in rows[0]
    )
    data_rows = rows[1:] if has_header else rows
    extracted: list[tuple[str, str]] = []
    for row in data_rows:
        if column < len(row):
            normalized = normalize_website(row[column])
            if normalized:
                extracted.append(normalized)
    if not extracted:
        raise HTTPException(
            status_code=400,
            detail="No valid website domains found. Include a website or domain column.",
        )
    return extracted[:500]


def serialize_company(company: Company) -> CompanyOutput:
    return CompanyOutput.model_validate(company)


@app.get(f"{API_PREFIX}/health", response_model=HealthOutput)
async def health() -> HealthOutput:
    configured = groq_configured()
    return HealthOutput(
        status="ok",
        ai_configured=configured,
        ai_provider="Groq" if configured else None,
    )


@app.get(f"{API_PREFIX}/dashboard", response_model=DashboardOutput)
async def dashboard(session: AsyncSession = Depends(get_session)) -> DashboardOutput:
    totals = (await session.execute(
        select(Company.status, func.count(Company.id)).group_by(Company.status)
    )).all()
    counts = {name: count for name, count in totals}
    total = sum(counts.values())
    average = await session.scalar(
        select(func.avg(Company.lead_score)).where(Company.status == "completed")
    )
    recent = await session.scalars(
        select(Company).order_by(Company.created_at.desc()).limit(6)
    )
    return DashboardOutput(
        total_companies=total,
        pending=counts.get("pending", 0),
        processing=counts.get("processing", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        average_score=round(float(average), 1) if average is not None else None,
        recent_companies=[serialize_company(company) for company in recent],
    )


@app.get(f"{API_PREFIX}/companies", response_model=list[CompanyOutput])
async def list_companies(
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=255),
    session: AsyncSession = Depends(get_session),
) -> list[CompanyOutput]:
    query = select(Company)
    if status_filter:
        if status_filter not in {"pending", "processing", "completed", "failed"}:
            raise HTTPException(status_code=400, detail="Invalid company status.")
        query = query.where(Company.status == status_filter)
    if search:
        needle = f"%{search.strip()}%"
        query = query.where(
            or_(
                Company.domain.ilike(needle),
                Company.company_name.ilike(needle),
                Company.industry.ilike(needle),
                Company.niche.ilike(needle),
            )
        )
    companies = await session.scalars(query.order_by(Company.created_at.desc()))
    return [serialize_company(company) for company in companies]


@app.post(f"{API_PREFIX}/import", response_model=ImportResult, status_code=201)
async def import_csv(
    payload: CsvImportInput,
    background_response: Response,
    session: AsyncSession = Depends(get_session),
) -> ImportResult:
    candidates = extract_domains(payload.csv_text)
    added: list[Company] = []
    seen: set[str] = set()
    skipped = 0
    for domain, website_url in candidates:
        if domain in seen:
            skipped += 1
            continue
        seen.add(domain)
        existing = await session.scalar(select(Company.id).where(Company.domain == domain))
        if existing is not None:
            skipped += 1
            continue
        company = Company(domain=domain, website_url=website_url, status="pending")
        session.add(company)
        added.append(company)

    if not added:
        if skipped:
            raise HTTPException(
                status_code=400,
                detail="Every valid domain in this CSV has already been imported.",
            )
        raise HTTPException(status_code=400, detail="No new domains were imported.")

    await session.commit()
    for company in added:
        await session.refresh(company)
    for company in added:
        schedule_company(company.id)
    background_response.status_code = status.HTTP_201_CREATED
    return ImportResult(
        imported=len(added),
        skipped=skipped,
        companies=[serialize_company(company) for company in added],
    )


@app.get(f"{API_PREFIX}/companies/{{company_id}}", response_model=CompanyOutput)
async def get_company(
    company_id: int, session: AsyncSession = Depends(get_session)
) -> CompanyOutput:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return serialize_company(company)


@app.post(
    f"{API_PREFIX}/companies/{{company_id}}/retry",
    response_model=CompanyOutput,
    status_code=202,
)
async def retry_company(
    company_id: int,
    session: AsyncSession = Depends(get_session),
) -> CompanyOutput:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    if company.status == "processing":
        raise HTTPException(status_code=409, detail="This company is already processing.")
    company.status = "pending"
    company.error_message = None
    await session.commit()
    await session.refresh(company)
    schedule_company(company_id)
    return serialize_company(company)
