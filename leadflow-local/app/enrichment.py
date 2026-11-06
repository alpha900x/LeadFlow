import json
import math
import os

from openai import AsyncOpenAI, RateLimitError
from pydantic import ValidationError

from .groq_limiter import groq_rate_limiter, retry_delay_seconds
from .schemas import LeadAnalysis

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_COMPLETION_TOKENS = 1_500
MAX_WEBSITE_TEXT_CHARACTERS = 8_000


def groq_configured() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


async def analyze_company(company: dict, scraped: dict) -> LeadAnalysis:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Groq is not configured. Set GROQ_API_KEY in the API service environment to enable AI analysis."
        )

    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    source = {
        "domain": company["domain"],
        "website_url": company["website_url"],
        "page_title": scraped.get("page_title"),
        "meta_description": scraped.get("meta_description"),
        "headings": scraped.get("headings", []),
        "pricing_page_found": scraped.get("pricing_page_found", False),
        "website_text": (scraped.get("website_text") or "")[
            :MAX_WEBSITE_TEXT_CHARACTERS
        ],
    }
    messages = [
        {
            "role": "system",
            "content": (
                "You analyze public B2B company websites for a sales team. Use only evidence in "
                "the supplied website data. Return an accurate industry, specific niche, lead "
                "score from 1 to 100 based on how clearly the website signals a real business "
                "and commercial opportunity, a concise factual summary, and one personalized "
                "cold outreach email. Do not invent customers, results, integrations, or facts. "
                "If evidence is sparse, say so in the summary and keep the score conservative. "
                "Address the company team rather than guessing a person's name. Keep the email "
                "professional and concise, with a relevant subject line and a clear low-pressure "
                "call to action. Output exactly the requested structured fields."
            ),
        },
        {"role": "user", "content": json.dumps(source, ensure_ascii=False)},
    ]
    schema = LeadAnalysis.model_json_schema()
    estimated_tokens = (
        math.ceil(len(json.dumps(messages, ensure_ascii=False)) / 2)
        + MAX_COMPLETION_TOKENS
    )
    await groq_rate_limiter.acquire(estimated_tokens)

    async with AsyncOpenAI(
        api_key=api_key, base_url=GROQ_BASE_URL, timeout=45, max_retries=0
    ) as client:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "lead_analysis",
                        "strict": True,
                        "schema": schema,
                    },
                },
            )
        except RateLimitError as error:
            delay = retry_delay_seconds(error.response.headers)
            await groq_rate_limiter.pause_for(delay)
            raise RuntimeError(
                "Groq's organization rate limit was reached. LeadFlow has paused "
                f"new model requests for about {math.ceil(delay)} seconds. "
                "Retry this company after the pause."
            ) from error

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Groq returned an empty analysis.")

    try:
        return LeadAnalysis.model_validate_json(content, strict=True)
    except ValidationError as error:
        raise RuntimeError("Groq returned data that did not match the LeadFlow analysis schema.") from error
