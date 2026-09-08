"""Authenticated portable bundle. No provider key or local token persistence."""

import base64
import getpass
import json
import os
import warnings
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from pydantic import SecretStr

from src.evaluator.contracts import EvaluationAuthorizationError, gateway_url


def secure_prompt(label):
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(label)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _key(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ValueError("passphrase length")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())


def encrypt_bundle(token, password, *, url, credential_id, allow_loopback=False):
    url = gateway_url(url, allow_loopback=allow_loopback)
    metadata = {"version": 1, "gateway_url": url, "credential_id": credential_id}
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = AESGCM(_key(password, salt)).encrypt(nonce, token.encode(), _canonical(metadata))
    return _canonical(
        {
            **metadata,
            **{
                k: base64.b64encode(v).decode()
                for k, v in (("salt", salt), ("nonce", nonce), ("ciphertext", ciphertext))
            },
        }
    )


def decrypt_bundle(raw, password, *, allow_loopback=False):
    try:
        if len(raw) > 65536:
            raise ValueError()

        def unique(pairs):
            result = {}
            for k, v in pairs:
                if k in result:
                    raise ValueError()
                result[k] = v
            return result

        obj = json.loads(raw, object_pairs_hook=unique)
        if set(obj) != {"version", "gateway_url", "credential_id", "salt", "nonce", "ciphertext"}:
            raise ValueError()
        if type(obj["version"]) is not int or obj["version"] != 1:
            raise ValueError()
        metadata = {k: obj[k] for k in ("version", "gateway_url", "credential_id")}
        url = gateway_url(obj["gateway_url"], allow_loopback=allow_loopback)
        salt, nonce, ct = (
            base64.b64decode(obj[k], validate=True) for k in ("salt", "nonce", "ciphertext")
        )
        if len(salt) != 16 or len(nonce) != 12 or not 32 <= len(ct) <= 1024:
            raise ValueError()
        token = AESGCM(_key(password, salt)).decrypt(nonce, ct, _canonical(metadata)).decode()
        if not token.startswith("vfa_") or len(token) != 47:
            raise ValueError()
        return url, SecretStr(token), obj["credential_id"]
    except Exception:
        raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_INVALID") from None


def read_bundle(path):
    # Native pathlib paths, including spaces/Unicode; WSL uses /mnt/c rather than C:\\.
    try:
        with Path(path).expanduser().open("rb") as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError()
        return data
    except Exception:
        raise EvaluationAuthorizationError("EVALUATION_CREDENTIAL_INVALID") from None
