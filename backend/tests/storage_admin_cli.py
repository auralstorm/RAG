"""POC-only official RustFS CLI bridge for admin responses unsupported by minio-py.

Credentials travel via stdin to a private temporary file, never Docker command arguments.
Returned text masks supplied credentials; the application S3 client is unaffected.
"""

import json
import subprocess
from dataclasses import dataclass

from app.core.config import Settings
from pydantic import JsonValue, SecretStr

SCRIPT = r"""
set -eu
umask 077
temporary_dir=$(mktemp -d)
trap 'rm -rf "$temporary_dir"' EXIT
cat > "$temporary_dir/request.json"
caller_key=$(jq -r .caller_key "$temporary_dir/request.json")
caller_secret=$(jq -r .caller_secret "$temporary_dir/request.json")
export RC_HOST_poc="http://${caller_key}:${caller_secret}@127.0.0.1:9000"
operation=$(jq -r .operation "$temporary_dir/request.json")
target_key=$(jq -r .target_key "$temporary_dir/request.json")
case "$operation" in
  create)
    target_secret=$(jq -r .target_secret "$temporary_dir/request.json")
    target_user=$(jq -r '.target_user // ""' "$temporary_dir/request.json")
    jq .policy "$temporary_dir/request.json" > "$temporary_dir/policy.json"
    if [ -n "$target_user" ]; then
      rc --json admin service-account create poc "$target_key" "$target_secret" --policy "$temporary_dir/policy.json" --user "$target_user"
    else
      rc --json admin service-account create poc "$target_key" "$target_secret" --policy "$temporary_dir/policy.json"
    fi
    ;;
  update)
    jq .policy "$temporary_dir/request.json" > "$temporary_dir/policy.json"
    rc --json admin service-account update poc "$target_key" --policy "$temporary_dir/policy.json"
    ;;
  *) exit 2 ;;
esac
"""


@dataclass(frozen=True)
class AdminResult:
    returncode: int
    summary: str


def service_account(
    settings: Settings,
    *,
    container: str,
    operation: str,
    target_key: str,
    policy: dict[str, JsonValue],
    target_secret: SecretStr | None = None,
    target_user: str | None = None,
) -> AdminResult:
    """Invoke only the isolated POC container; mask credentials before returning CLI diagnostics."""
    caller_key = settings.object_storage_access_key.get_secret_value()
    caller_secret = settings.object_storage_secret_key.get_secret_value()
    secret = target_secret.get_secret_value() if target_secret is not None else ""
    result = subprocess.run(
        ["docker", "exec", "-i", container, "sh", "-ec", SCRIPT],
        input=json.dumps(
            {
                "caller_key": caller_key,
                "caller_secret": caller_secret,
                "operation": operation,
                "target_key": target_key,
                "target_secret": secret,
                "target_user": target_user,
                "policy": policy,
            }
        ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    summary = result.stdout + result.stderr
    for value in (caller_key, caller_secret, secret, target_key, target_user):
        if value:
            summary = summary.replace(value, "[redacted]")
    return AdminResult(result.returncode, summary)
