from __future__ import annotations

from num2words import num2words


def format_int_with_spaces(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def int_to_words_ru(n: int) -> str:
    return num2words(n, lang="ru")


def build_tons_full(tons: int) -> str:
    return f"{format_int_with_spaces(tons)} ({int_to_words_ru(tons)}) "


def build_price_full(price: int) -> str:
    return f"{format_int_with_spaces(price)} ({int_to_words_ru(price)})"
