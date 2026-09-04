"""Normalize the non-semantic Mach-O UUID before applying a fixed ad-hoc signature."""

from __future__ import annotations

import hashlib
import os
import struct
import sys
from pathlib import Path

_MACHO_64_LE_MAGIC = bytes.fromhex("cffaedfe")
_LC_UUID = 0x1B
_HEADER_SIZE = 32
_UUID_SIZE = 16


def normalize(path: Path) -> None:
    requested = path.expanduser()
    if requested.is_symlink():
        raise RuntimeError("proof host must not be a symlink")
    resolved = requested.resolve(strict=True)
    if not resolved.is_file():
        raise RuntimeError("proof host must be a regular file")

    payload = bytearray(resolved.read_bytes())
    if len(payload) < _HEADER_SIZE or payload[:4] != _MACHO_64_LE_MAGIC:
        raise RuntimeError("proof host is not a little-endian 64-bit Mach-O")
    load_command_count = struct.unpack_from("<I", payload, 16)[0]
    offset = _HEADER_SIZE
    uuid_offset: int | None = None
    for _ in range(load_command_count):
        if offset + 8 > len(payload):
            raise RuntimeError("invalid Mach-O load command table")
        command, command_size = struct.unpack_from("<II", payload, offset)
        if command_size < 8 or offset + command_size > len(payload):
            raise RuntimeError("invalid Mach-O load command size")
        if command == _LC_UUID:
            if command_size < 8 + _UUID_SIZE or uuid_offset is not None:
                raise RuntimeError("invalid or duplicate Mach-O UUID command")
            uuid_offset = offset + 8
        offset += command_size
    if uuid_offset is None:
        raise RuntimeError("proof host has no Mach-O UUID command")

    payload[uuid_offset : uuid_offset + _UUID_SIZE] = bytes(_UUID_SIZE)
    deterministic_uuid = hashlib.sha256(payload).digest()[:_UUID_SIZE]
    payload[uuid_offset : uuid_offset + _UUID_SIZE] = deterministic_uuid

    flags = os.O_WRONLY | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(resolved, flags)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: normalize_macos_host.py HOST_BINARY")
    normalize(Path(sys.argv[1]))
