"""Errors raised by a single job source. They must not stop other sources."""


class JobSourceError(Exception):
    def __init__(self, source: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.source = source
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"{self.source}: HTTP {self.status_code} — {self.message}"
        return f"{self.source}: {self.message}"
