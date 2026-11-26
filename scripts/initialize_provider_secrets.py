"""Create a new owner-only AES-GCM key file for encrypted Provider credentials."""

import argparse
import json
import os
from pathlib import Path

from app.core.config import load_settings
from app.modules.model_gateway.infrastructure.provider_secrets import generate_provider_secrets_config


def initialize(path: Path) -> None:
    """Create a private config exactly once; never overwrite active encryption keys."""
    path = path.absolute()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    configuration = generate_provider_secrets_config()
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
    arguments = parser.parse_args()
    settings = load_settings()
    path = arguments.config or settings.provider_secrets_config_ref
    if path is None:
        parser.error("Set ENTERPRISE_RAG_PROVIDER_SECRETS_CONFIG_REF or pass --config")
    initialize(path)
    print(f"Provider encryption keys created at {path}. Keep this file private and configure the API to use it.")


if __name__ == "__main__":
    main()
