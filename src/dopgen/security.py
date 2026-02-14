from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
import os
from pathlib import Path


class SecurityError(RuntimeError):
    """Raised when encryption or decryption cannot be completed."""


def load_fernet_from_env(env_key_name: str = "CLIENTS_KEY") -> Fernet:
    key = os.getenv(env_key_name)
    if not key:
        raise SecurityError(f"Environment variable {env_key_name} is required.")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise SecurityError("CLIENTS_KEY has invalid format for Fernet.") from exc


def decrypt_clients_file(path: Path, fernet: Fernet) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise SecurityError(f"Encrypted clients file not found: {path}")

    encrypted = path.read_bytes()
    try:
        decrypted = fernet.decrypt(encrypted)
    except InvalidToken as exc:
        raise SecurityError("Unable to decrypt clients.enc: invalid CLIENTS_KEY.") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise SecurityError("Unexpected decryption error.") from exc

    import json

    try:
        data = json.loads(decrypted.decode("utf-8"))
    except Exception as exc:
        raise SecurityError("Decrypted clients payload is not valid UTF-8 JSON.") from exc

    if not isinstance(data, dict):
        raise SecurityError("Decrypted clients payload must be a JSON object.")
    return data


def encrypt_clients_payload(payload: bytes, fernet: Fernet) -> bytes:
    return fernet.encrypt(payload)
