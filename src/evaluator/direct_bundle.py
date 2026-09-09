"""Versioned AES-256-GCM/scrypt direct registry, separate from .vfaeval."""

import argparse
import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.evaluator.bundle import _canonical, _key, secure_prompt
from src.evaluator.direct_registry import DirectCredentialRegistry, from_owner_staging

MAX_BYTES = 65536
HEADER = {
    "format": "vfa-direct-credentials",
    "format_version": 1,
    "profile": "investor-alpha",
    "payload_schema": "direct-provider-registry/v1",
    "crypto": {"cipher": "AES-256-GCM", "kdf": "scrypt", "n": 32768, "r": 8, "p": 1, "length": 32},
}


class DirectBundleError(ValueError):
    def __init__(self, code="DIRECT_CREDENTIAL_AUTHENTICATION_FAILED"):
        self.code = code
        super().__init__(code)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DirectBundleError()
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique)


def encrypt_direct_bundle(registry, password):
    salt, nonce = os.urandom(16), os.urandom(12)
    header = {
        **HEADER,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
    }
    ciphertext = AESGCM(_key(password, salt)).encrypt(
        nonce, _canonical(registry.secret_payload()), _canonical(header)
    )
    result = _canonical({**header, "ciphertext": base64.b64encode(ciphertext).decode()})
    if len(result) > MAX_BYTES:
        raise DirectBundleError()
    return result


def decrypt_direct_bundle(raw, password):
    try:
        if len(raw) > MAX_BYTES:
            raise DirectBundleError()
        obj = strict_json(raw)
        if not isinstance(obj, dict) or set(obj) != set(HEADER) | {"salt", "nonce", "ciphertext"}:
            raise DirectBundleError("DIRECT_CREDENTIAL_FORMAT_UNSUPPORTED")
        # Canonical equality also rejects booleans/floats masquerading as integer KDF values.
        if _canonical({k: obj[k] for k in HEADER}) != _canonical(HEADER):
            raise DirectBundleError("DIRECT_CREDENTIAL_FORMAT_UNSUPPORTED")
        salt, nonce, ct = (
            base64.b64decode(obj[k], validate=True) for k in ("salt", "nonce", "ciphertext")
        )
        if len(salt) != 16 or len(nonce) != 12 or len(ct) < 16:
            raise DirectBundleError()
        header = {k: v for k, v in obj.items() if k != "ciphertext"}
        plain = AESGCM(_key(password, salt)).decrypt(nonce, ct, _canonical(header))
        return DirectCredentialRegistry.model_validate(strict_json(plain))
    except DirectBundleError:
        raise
    except Exception:
        # Wrong password and corrupted authentication are intentionally indistinguishable.
        raise DirectBundleError() from None


def read_direct_bundle(path):
    try:
        path = Path(path)
        if path.is_symlink() or path.suffix != ".vfacred":
            raise DirectBundleError()
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise DirectBundleError()
        return raw
    except DirectBundleError:
        raise
    except OSError:
        raise DirectBundleError("DIRECT_CREDENTIAL_NOT_FOUND") from None


def main():
    parser = argparse.ArgumentParser(description="Owner-only encrypted direct bundle creation")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        target = Path(args.output)
        if target.suffix != ".vfacred" or target.exists() or target.is_symlink():
            raise DirectBundleError()
        password = secure_prompt("Credential passphrase: ")
        confirmation = secure_prompt("Confirm credential passphrase: ")
        if password != confirmation:
            raise DirectBundleError("DIRECT_CREDENTIAL_UNLOCK_FAILED")
        registry = from_owner_staging(strict_json(Path(args.registry).read_bytes()))
        raw = encrypt_direct_bundle(registry, password)
        if decrypt_direct_bundle(raw, password) != registry:
            raise DirectBundleError()
        del registry, password, confirmation
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        print("ACTIVE_VFACRED_CREATE=PASS; ENCRYPTION_ROUND_TRIP=PASS")
    except Exception:
        print("Credential bundle creation failed; no plaintext credentials were persisted.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
