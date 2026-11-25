"""Bounded owner-only reads shared by platform keys and identity source configuration."""

import os
import stat
from pathlib import Path


def read_private_bytes(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > 100_000
        ):
            raise ValueError("Authentication configuration requires a private regular file")
        content = source.read(100_001)
        if len(content) > 100_000:
            raise ValueError("Authentication configuration exceeds its size limit")
        return content
