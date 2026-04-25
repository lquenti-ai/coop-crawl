from __future__ import annotations


class FourXXError(Exception):
    """4xx-class outage — notify once per streak, keep polling."""

    def __init__(self, status: int, url: str, detail: str = "") -> None:
        self.status = status
        self.url = url
        self.detail = detail
        super().__init__(f"{status} on {url}{(': ' + detail) if detail else ''}")


class FiveXXError(Exception):
    """5xx-class outage — log only, keep polling."""

    def __init__(self, status: int, url: str, detail: str = "") -> None:
        self.status = status
        self.url = url
        self.detail = detail
        super().__init__(f"{status} on {url}{(': ' + detail) if detail else ''}")


def classify_status(code: int) -> type[FourXXError] | type[FiveXXError] | None:
    """Map an HTTP status code to the exception class to raise (or None for 2xx/3xx).

    408 and 429 are treated as 4xx per spec §9.
    """
    if 200 <= code < 400:
        return None
    if 400 <= code < 500:
        return FourXXError
    if 500 <= code < 600:
        return FiveXXError
    # Anything outside 2xx-5xx is unexpected; treat as 5xx (transient, log-only).
    return FiveXXError
