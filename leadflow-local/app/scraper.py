import asyncio
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

from playwright.async_api import async_playwright

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
PRICING_PATTERN = re.compile(r"pricing|price|plans|packages|quote|subscription|rates", re.I)
MAX_INTERNAL_LINKS = 30


def website_access_error(status_code: int | None) -> str | None:
    if status_code is None:
        return "The website did not return an HTTP response."
    if status_code == 401:
        return "The website requires authorization; LeadFlow only researches public pages."
    if status_code == 403:
        return (
            "The site denied automated access (HTTP 403). LeadFlow will not bypass "
            "that restriction, so research for this company stopped."
        )
    if status_code == 429:
        return "The website rate-limited the request (HTTP 429). Retry this company later."
    if status_code >= 400:
        return f"The website returned HTTP {status_code}."
    return None


async def _public_http_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return False

    hostname = parts.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        return False

    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except (OSError, ValueError):
        return False

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            return False
    return bool(addresses)


def _root_host(hostname: str) -> str:
    return hostname.lower().removeprefix("www.").rstrip(".")


async def scrape_website(website_url: str) -> dict:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context(
                user_agent="LeadFlowBot/1.0 (+public company website research)"
            )

            async def guard_request(route):
                request = route.request
                if request.resource_type in {"image", "media", "font"}:
                    await route.abort()
                elif await _public_http_url(request.url):
                    await route.continue_()
                else:
                    await route.abort()

            await context.route("**/*", guard_request)
            page = await context.new_page()
            response = await page.goto(
                website_url, wait_until="domcontentloaded", timeout=18_000
            )
            access_error = website_access_error(
                response.status if response is not None else None
            )
            if access_error:
                raise RuntimeError(access_error)

            title = (await page.title()).strip()[:500] or None
            meta_locator = page.locator('meta[name="description"]')
            meta_description = None
            if await meta_locator.count():
                meta_description = (
                    (await meta_locator.first.get_attribute("content") or "").strip()[:2000]
                    or None
                )

            heading_nodes = await page.locator("h1, h2").all()
            headings: list[str] = []
            for node in heading_nodes[:24]:
                heading = " ".join((await node.inner_text()).split())
                if heading:
                    tag = await node.evaluate("(element) => element.tagName")
                    headings.append(f"{tag}: {heading[:250]}")

            body_text = ""
            try:
                body_text = (await page.locator("body").inner_text(timeout=4_000))[:18_000]
            except Exception:
                body_text = " ".join(headings)

            anchors = await page.locator("a[href]").evaluate_all(
                """nodes => nodes.slice(0, 500).map(node => ({
                    href: node.href,
                    text: (node.innerText || node.getAttribute('aria-label') || '').trim()
                }))"""
            )
            current_host = urlsplit(page.url).hostname or urlsplit(website_url).hostname or ""
            root_host = _root_host(current_host)
            internal_links: list[str] = []
            pricing_found = False
            emails = set(EMAIL_PATTERN.findall(body_text))
            phones = set(PHONE_PATTERN.findall(body_text))

            for anchor in anchors:
                href = str(anchor.get("href", "")).strip()
                text = str(anchor.get("text", "")).strip()
                if PRICING_PATTERN.search(f"{href} {text}"):
                    pricing_found = True
                if href.lower().startswith("mailto:"):
                    emails.update(EMAIL_PATTERN.findall(href[7:]))
                if href.lower().startswith("tel:"):
                    phone = href[4:].strip()
                    if phone:
                        phones.add(phone)

                target = urljoin(page.url, href)
                target_parts = urlsplit(target)
                target_host = target_parts.hostname or ""
                if (
                    target_parts.scheme in {"http", "https"}
                    and target_host
                    and (_root_host(target_host) == root_host or _root_host(target_host).endswith(f".{root_host}"))
                    and target not in internal_links
                ):
                    internal_links.append(target)
                    if len(internal_links) >= MAX_INTERNAL_LINKS:
                        break

            return {
                "page_title": title,
                "meta_description": meta_description,
                "headings": headings,
                "pricing_page_found": pricing_found,
                "emails": sorted(emails)[:20],
                "phones": sorted(phones)[:20],
                "internal_links": internal_links,
                "website_text": body_text,
                "final_url": page.url,
            }
        finally:
            await browser.close()
