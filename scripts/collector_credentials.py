"""Save an already-issued collector token without command arguments, echo or overwrites."""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from app.adapters.telemetry_credentials import CollectorCredentials
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]


def write_credentials(path: Path, token: SecretStr) -> None:
    """Local provisioning stays under ignored work files; existing secrets are never overwritten."""
    if not path.resolve().is_relative_to((ROOT / ".poc-results").resolve()):
        raise ValueError("Local collector credentials must remain under .poc-results")
    credentials = CollectorCredentials(bearer_token=token)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        # SecretStr's default serializer masks the value; this is the private, deliberate persistence seam.
        json.dump({"bearer_token": credentials.bearer_token.get_secret_value()}, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".poc-results/observability/collector.json")
    arguments = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Use an interactive terminal so the collector token cannot be echoed")
    write_credentials(arguments.output, SecretStr(getpass.getpass("Collector service token (hidden): ")))
    print("Collector credential reference created. No token is printed; restart the API after configuration changes.")


if __name__ == "__main__":
    main()
