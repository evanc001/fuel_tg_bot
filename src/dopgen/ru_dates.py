from __future__ import annotations

from datetime import date, datetime
import re


MONTHS_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def parse_ddmmyyyy(text: str) -> date:
    value = text.strip()
    if re.fullmatch(r"\d{2}\.\d{2}$", value):
        day, month = [int(part) for part in value.split(".")]
        return date(date.today().year, month, day)
    return datetime.strptime(value, "%d.%m.%Y").date()


def format_current_date(d: date) -> str:
    return f"{d.day} {MONTHS_GENITIVE[d.month]} {d.year} г."


def format_date_long_no_suffix(d: date) -> str:
    return f"{d.day} {MONTHS_GENITIVE[d.month]} {d.year}"


def format_delivery_month_year(d: date, delivery_type: str) -> str:
    base = f"{d.day} {MONTHS_GENITIVE[d.month]} {d.year} года"
    if delivery_type == "delivery":
        return f"до {base}"
    return base


def format_pay_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")
