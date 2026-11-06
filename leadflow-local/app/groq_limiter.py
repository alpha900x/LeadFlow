"""Conservative, process-wide request and token limits for Groq's free tier."""

import asyncio
import os
import re
import time
from collections import deque
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def _limit_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer.") from error
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


class GroqBudgetExceeded(RuntimeError):
    """Raised before sending a request that would exceed LeadFlow's safety budget."""


class GroqRateLimiter:
    """Sliding-window RPM/TPM limits plus conservative UTC-day budgets."""

    def __init__(
        self,
        *,
        requests_per_minute: int = 20,
        requests_per_day: int = 900,
        tokens_per_minute: int = 6_500,
        tokens_per_day: int = 180_000,
        window_seconds: float = 60.0,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.requests_per_day = requests_per_day
        self.tokens_per_minute = tokens_per_minute
        self.tokens_per_day = tokens_per_day
        self.window_seconds = window_seconds
        self._lock = asyncio.Lock()
        self._minute_usage: deque[tuple[float, int]] = deque()
        self._utc_day = datetime.now(timezone.utc).date()
        self._daily_requests = 0
        self._daily_tokens = 0
        self._cooldown_until = 0.0

    def _roll_utc_day(self) -> None:
        current_day = datetime.now(timezone.utc).date()
        if current_day != self._utc_day:
            self._utc_day = current_day
            self._daily_requests = 0
            self._daily_tokens = 0

    def _reset_minute_window(self, now: float) -> None:
        while self._minute_usage and now - self._minute_usage[0][0] >= self.window_seconds:
            self._minute_usage.popleft()

    def _daily_limit_message(self) -> str:
        now = datetime.now(timezone.utc)
        reset_at = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return (
            "LeadFlow's conservative Groq daily budget has been reached. "
            f"No additional model request was sent; the local budget resets at "
            f"{reset_at:%Y-%m-%d %H:%M UTC}. Retry this company after the reset."
        )

    async def acquire(self, estimated_tokens: int) -> None:
        if estimated_tokens <= 0:
            raise ValueError("The estimated Groq token count must be positive.")
        if estimated_tokens > self.tokens_per_minute:
            raise GroqBudgetExceeded(
                "This website's analysis is larger than LeadFlow's safe Groq "
                "per-minute token budget. No model request was sent."
            )

        while True:
            wait_seconds = 0.0
            async with self._lock:
                self._roll_utc_day()
                now = time.monotonic()
                self._reset_minute_window(now)

                if (
                    self._daily_requests >= self.requests_per_day
                    or self._daily_tokens + estimated_tokens > self.tokens_per_day
                ):
                    raise GroqBudgetExceeded(self._daily_limit_message())

                if now < self._cooldown_until:
                    wait_seconds = self._cooldown_until - now
                elif len(self._minute_usage) >= self.requests_per_minute:
                    wait_seconds = (
                        self._minute_usage[0][0] + self.window_seconds - now
                    )
                else:
                    minute_tokens = sum(tokens for _, tokens in self._minute_usage)
                    if minute_tokens + estimated_tokens > self.tokens_per_minute:
                        remaining_tokens = minute_tokens
                        for requested_at, tokens in self._minute_usage:
                            remaining_tokens -= tokens
                            if remaining_tokens + estimated_tokens <= self.tokens_per_minute:
                                wait_seconds = (
                                    requested_at + self.window_seconds - now
                                )
                                break
                    else:
                        self._minute_usage.append((now, estimated_tokens))
                        self._daily_requests += 1
                        self._daily_tokens += estimated_tokens
                        return

            await asyncio.sleep(max(wait_seconds, 0.05))

    async def pause_for(self, seconds: float) -> None:
        async with self._lock:
            self._cooldown_until = max(
                self._cooldown_until,
                time.monotonic() + min(max(seconds, 1.0), 86_400.0),
            )


def retry_delay_seconds(headers: Mapping[str, str], default: float = 60.0) -> float:
    """Read Groq's Retry-After or reset headers, with a safe default."""
    for name in (
        "retry-after",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset-requests",
    ):
        raw = headers.get(name)
        if not raw:
            continue
        value = str(raw).strip()
        try:
            seconds = float(value)
        except ValueError:
            seconds = 0.0
            for amount, unit in re.findall(
                r"(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)", value.lower()
            ):
                seconds += float(amount) * {
                    "ms": 0.001,
                    "s": 1,
                    "m": 60,
                    "h": 3_600,
                    "d": 86_400,
                }[unit]
            if seconds == 0:
                try:
                    reset_at = parsedate_to_datetime(value)
                    if reset_at.tzinfo is None:
                        reset_at = reset_at.replace(tzinfo=timezone.utc)
                    seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    continue
        if seconds > 0:
            return min(seconds, 86_400.0)
    return default


groq_rate_limiter = GroqRateLimiter(
    requests_per_minute=_limit_from_env("GROQ_SAFE_RPM", 20),
    requests_per_day=_limit_from_env("GROQ_SAFE_RPD", 900),
    tokens_per_minute=_limit_from_env("GROQ_SAFE_TPM", 6_500),
    tokens_per_day=_limit_from_env("GROQ_SAFE_TPD", 180_000),
)

