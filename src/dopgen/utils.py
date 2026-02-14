from __future__ import annotations

import re


INVALID_WIN_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1F]')


def normalize_text(s: str) -> str:
    return s.lower().strip().replace("ё", "е")


def sanitize_filename(name: str) -> str:
    cleaned = INVALID_WIN_CHARS_RE.sub("_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "document.docx"


def normalize_contract(raw: str) -> str:
    contract = raw.strip()
    if contract.startswith("№"):
        contract = contract[1:].strip()
    return contract


def search_catalog(query: str, data: dict[str, str], limit: int = 10) -> list[tuple[str, str]]:
    q = normalize_text(query)
    if not q:
        return []

    results: list[tuple[str, str]] = []
    seen: set[str] = set()

    for key, value in data.items():
        if normalize_text(key) == q:
            results.append((key, value))
            seen.add(key)

    for key, value in data.items():
        if key in seen:
            continue
        key_norm = normalize_text(key)
        value_norm = normalize_text(value)
        if q in key_norm or q in value_norm:
            results.append((key, value))
            seen.add(key)

    return results[:limit]
