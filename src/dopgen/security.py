from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
import os
from pathlib import Path


class SecurityError(RuntimeError):
    """Raised when encryption or decryption cannot be completed."""


def load_fernet_from_env(env_key_name: str = "CLIENTS_KEY") -> Fernet:
    key = (os.getenv(env_key_name) or "").strip()
    key_file = (os.getenv(f"{env_key_name}_FILE") or "").strip()

    if not key and key_file:
        path = Path(key_file)
        if not path.exists():
            raise SecurityError(f"{env_key_name}_FILE points to missing file: {path}")
        key = path.read_text(encoding="utf-8-sig").strip()

    if not key:
        raise SecurityError(
            f"Either {env_key_name} or {env_key_name}_FILE environment variable is required."
        )

    key = key.strip().strip('"').strip("'")
    if key.startswith("gAAAAA"):
        raise SecurityError(
            f"{env_key_name} looks like encrypted payload (clients.enc), not Fernet key."
        )

    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise SecurityError(
            f"{env_key_name} has invalid format for Fernet. "
            "Expected URL-safe base64 key (usually 44 chars, ends with '=')."
        ) from exc


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
