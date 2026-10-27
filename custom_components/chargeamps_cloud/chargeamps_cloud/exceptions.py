"""Exceptions raised by the Charge Amps Cloud client."""

from __future__ import annotations


class ChargeAmpsError(Exception):
    """Base class for all Charge Amps errors."""


class ChargeAmpsConnectionError(ChargeAmpsError):
    """The API could not be reached."""


class ChargeAmpsAuthError(ChargeAmpsError):
    """The credentials or the API key were rejected."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)


class ChargeAmpsForbiddenError(ChargeAmpsError):
    """The account is authenticated but not allowed to perform the action."""


class ChargeAmpsNotFoundError(ChargeAmpsError):
    """The requested resource does not exist."""


class ChargeAmpsRateLimitError(ChargeAmpsError):
    """The API rate limit was hit."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ChargeAmpsApiError(ChargeAmpsError):
    """The API returned an unexpected error."""

    def __init__(
        self,
        status: int,
        message: str,
        *,
        method: str | None = None,
        url: str | None = None,
    ) -> None:
        self.status = status
        self.message = message
        self.method = method
        self.url = url
        detail = f"HTTP {status}"
        if method and url:
            detail = f"{method} {url} returned HTTP {status}"
        super().__init__(f"{detail}: {message}" if message else detail)
