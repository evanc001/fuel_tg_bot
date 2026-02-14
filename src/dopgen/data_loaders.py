from __future__ import annotations

import base64
import json
import os
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
    clients_json_b64 = (os.getenv("CLIENTS_JSON_B64") or "").strip()
    if clients_json_b64:
        padded = clients_json_b64 + ("=" * (-len(clients_json_b64) % 4))
        try:
            decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            data = json.loads(decoded)
        except Exception as exc:
            raise ValueError("CLIENTS_JSON_B64 is not valid base64 JSON payload.") from exc
        if not isinstance(data, dict):
            raise ValueError("CLIENTS_JSON_B64 must decode to a JSON object.")
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}

    fernet = load_fernet_from_env("CLIENTS_KEY")
    data = decrypt_clients_file(enc_path, fernet)
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}
