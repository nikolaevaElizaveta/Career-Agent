"""Calendar values that can be known only to year or month precision."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class DatePrecision(StrEnum):
    YEAR = "year"
    MONTH = "month"
    DAY = "day"


class PartialDate(BaseModel):
    """A date that does not invent missing day or month values."""

    year: int = Field(ge=1900, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    precision: DatePrecision

    @model_validator(mode="after")
    def precision_matches_fields(self) -> Self:
        if self.precision is DatePrecision.YEAR:
            if self.month is not None or self.day is not None:
                raise ValueError("year precision must not include month or day")
        elif self.precision is DatePrecision.MONTH:
            if self.month is None:
                raise ValueError("month precision requires a month")
            if self.day is not None:
                raise ValueError("month precision must not include a day")
        elif self.precision is DatePrecision.DAY:
            if self.month is None or self.day is None:
                raise ValueError("day precision requires month and day")
        return self

    @classmethod
    def parse(cls, value: Any) -> PartialDate:
        if isinstance(value, PartialDate):
            return value
        if isinstance(value, dict):
            return cls.model_validate(value)
        if isinstance(value, str):
            parts = value.split("-")
            if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) == 4:
                return cls(year=int(parts[0]), precision=DatePrecision.YEAR)
            if len(parts) == 2:
                return cls(
                    year=int(parts[0]),
                    month=int(parts[1]),
                    precision=DatePrecision.MONTH,
                )
            if len(parts) == 3:
                raise ValueError(
                    "Do not store YYYY-MM-DD strings; that invents or implies a day. "
                    "Use a PartialDate object with an explicit precision."
                )
        raise ValueError("Unsupported date value")

    def as_text(self) -> str:
        if self.precision is DatePrecision.YEAR:
            return f"{self.year:04d}"
        if self.precision is DatePrecision.MONTH:
            return f"{self.year:04d}-{self.month:02d}"
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"
