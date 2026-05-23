from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException


def days_until(value: Optional[date]) -> Optional[int]:
    if value is None:
        return None

    return (value - date.today()).days


def format_date(value: Optional[date]) -> str:
    if value is None:
        return "-"

    return value.strftime("%d/%m/%Y")


def format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return "-"

    return value.strftime("%d/%m/%Y %H:%M")


def parse_form_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).date()
        except ValueError:
            continue

    raise HTTPException(
        status_code=422,
        detail="Dates must use dd/mm/yyyy format",
    )
