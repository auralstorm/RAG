"""Create initial platform signing keys in a new owner-only configuration file."""

import argparse
import json
import os
import secrets
from pathlib import Path

from app.core.config import load_settings
from app.modules.iam.infrastructure.platform_config import PlatformAuthConfig
from pydantic import SecretStr


def initialize(path: Path) -> None:
    """Create a private key file exactly once; never overwrite existing key material."""
    path = path.absolute()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    configuration = PlatformAuthConfig(
        signing_key=SecretStr(secrets.token_hex(48)),
        pseudonymization_key=SecretStr(secrets.token_hex(48)),
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(configuration.private_payload(), output)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    settings = load_settings()
    path = args.config or settings.auth_platform_config_ref
    if path is None:
        parser.error("Set ENTERPRISE_RAG_AUTH_PLATFORM_CONFIG_REF or pass --config")
    initialize(path)
    print(f"Platform authentication keys created at {path}. Keep this file private and configure the API to use it.")


if __name__ == "__main__":
    main()
