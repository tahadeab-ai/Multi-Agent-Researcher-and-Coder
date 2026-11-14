"""Retry mechanics for LLM calls with custom Retry-After wait strategy (A1, N3)."""

from __future__ import annotations

import contextlib
import random

from tenacity import (
    RetryCallState,
    retry_if_exception_type,
)

from src.errors import ProviderError, ProviderTimeoutError, RateLimitError

_RETRYABLE_EXCEPTIONS = (RateLimitError, ProviderTimeoutError)


def is_retryable_exception(exc: BaseException) -> bool:
    """Check if exception qualifies for retry under A1 taxonomy.

    Retryable:
    - RateLimitError (429)
    - ProviderTimeoutError
    - ProviderError with status_code >= 500

    Non-retryable:
    - ProviderError with 4xx status_code except 429
    - Any other exception
    """
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, ProviderTimeoutError):
        return True
    if isinstance(exc, ProviderError) and exc.status_code is not None:
        return exc.status_code >= 500

    # SDK direct exceptions translation / matching
    # OpenAI: RateLimitError (429), APITimeoutError, APIConnectionError, InternalServerError (>=500)
    try:
        import openai

        if isinstance(exc, openai.RateLimitError):
            return True
        if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
            return True
        if isinstance(exc, openai.InternalServerError):
            return True
        if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
            return True
        if isinstance(exc, openai.APIStatusError) and exc.status_code < 500:
            return False
    except ImportError:
        pass

    # Anthropic: RateLimitError (429), APITimeoutError, APIConnectionError, InternalServerError
    try:
        import anthropic

        if isinstance(exc, anthropic.RateLimitError):
            return True
        if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
            return True
        if isinstance(exc, anthropic.InternalServerError):
            return True
        if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
            return True
        if isinstance(exc, anthropic.APIStatusError) and exc.status_code < 500:
            return False
    except ImportError:
        pass

    return False


class retry_if_phoenix_retryable(retry_if_exception_type):  # noqa: N801
    """Tenacity retry predicate for PHOENIX retryable errors."""

    def __init__(self) -> None:
        super().__init__(Exception)

    def __call__(self, retry_state: RetryCallState) -> bool:
        if retry_state.outcome is None:
            return False
        exc = retry_state.outcome.exception()
        if exc is None:
            return False
        return is_retryable_exception(exc)


class WaitRetryAfterOrExponential:
    """Custom tenacity wait strategy honoring Retry-After or exponential backoff + jitter."""

    def __init__(
        self,
        initial: float = 1.0,
        max_wait: float = 60.0,
        jitter: float = 1.0,
        multiplier: float = 2.0,
    ) -> None:
        self.initial = initial
        self.max_wait = max_wait
        self.jitter = jitter
        self.multiplier = multiplier

    def __call__(self, retry_state: RetryCallState) -> float:
        if retry_state.outcome is not None:
            exc = retry_state.outcome.exception()
            if isinstance(exc, RateLimitError) and exc.retry_after is not None:
                return min(exc.retry_after, self.max_wait)

            # Extract Retry-After from SDK exceptions if present
            if exc is not None:
                retry_after = getattr(exc, "retry_after", None)
                if retry_after is None and hasattr(exc, "response") and exc.response is not None:
                    headers = getattr(exc.response, "headers", {})
                    ra_header = headers.get("retry-after") or headers.get("Retry-After")
                    if ra_header:
                        with contextlib.suppress(ValueError):
                            retry_after = float(ra_header)
                if retry_after is not None:
                    return min(float(retry_after), self.max_wait)

        # Standard exponential backoff + jitter
        attempt = retry_state.attempt_number
        exp = self.initial * (self.multiplier ** (attempt - 1))
        jit = random.uniform(0, self.jitter)
        return min(exp + jit, self.max_wait)
