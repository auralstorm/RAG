"""Copy existing platform keys into a new private file without rotating keys or changing identities."""

import argparse
import json
import os
from pathlib import Path

from app.modules.iam.infrastructure.local_identity import read_private_config
from app.modules.iam.infrastructure.platform_config import PlatformAuthConfig


def separate(local_path: Path, platform_path: Path) -> None:
    local = read_private_config(local_path)
    if local.signing_key is None:
        raise ValueError("The legacy source contains no platform signing key to preserve")
    platform = PlatformAuthConfig(signing_key=local.signing_key, pseudonymization_key=local.pseudonymization_key)
    # Parent directory must already exist. Never overwrite an existing file or follow a symlink.
    descriptor = os.open(platform_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(platform.private_payload(), output)
    except BaseException:
        platform_path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-config", type=Path, required=True)
    parser.add_argument("--platform-config", type=Path, required=True)
    args = parser.parse_args()
    separate(args.local_config, args.platform_config)
    print("Platform keys copied. Set ENTERPRISE_RAG_AUTH_PLATFORM_CONFIG_REF and restart the API; source unchanged.")


if __name__ == "__main__":
    main()
