from __future__ import annotations

import json
from pathlib import Path

from .security import decrypt_clients_file, load_fernet_from_env


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    with path.open("r", encoding="utf-8-sig") as fp:
        data = json.load(fp)
    if not isinstance(data, dict):
        raise ValueError(f"JSON object expected in {path}")
    return data


def load_aliases(path: Path) -> dict[str, str]:
    data = load_json(path)
    companies = data.get("companies")
    if not isinstance(companies, dict):
        raise ValueError("aliases.json must contain object field 'companies'.")
    return {str(k): str(v) for k, v in companies.items()}


def load_products(path: Path) -> dict[str, str]:
    data = load_json(path)
    return {str(k): str(v) for k, v in data.items()}


def load_locations(path: Path) -> dict[str, str]:
    data = load_json(path)
    return {str(k): str(v) for k, v in data.items()}


def load_clients_encrypted(enc_path: Path) -> dict[str, dict[str, str]]:
    fernet = load_fernet_from_env("CLIENTS_KEY")
    data = decrypt_clients_file(enc_path, fernet)
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}
