from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.dopgen.security import encrypt_clients_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Encrypt clients.json into clients.enc")
    parser.add_argument("--in", dest="in_path", default="data/clients.json", help="Input JSON path")
    parser.add_argument("--out", dest="out_path", default="data/clients.enc", help="Output ENC path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")

    key = os.getenv("CLIENTS_KEY")
    if not key:
        key = Fernet.generate_key().decode("utf-8")
        print("CLIENTS_KEY was not set. Generated new key:")
        print(key)

    fernet = Fernet(key.encode("utf-8"))

    raw_text = in_path.read_text(encoding="utf-8-sig")
    json.loads(raw_text)
    encrypted = encrypt_clients_payload(raw_text.encode("utf-8"), fernet)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(encrypted)
    print(f"Encrypted clients written to: {out_path}")


if __name__ == "__main__":
    main()
