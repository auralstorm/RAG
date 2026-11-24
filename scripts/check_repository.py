"""Check repository links and common accidental secret formats without external services."""

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\((?:<([^>\n]+)>|([^\s)]+))\)")
PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
API_KEY = re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")


def main() -> None:
    """Fail on missing local links, tracked environment files or common private keys."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = sorted({ROOT / name for name in result.stdout.split("\0") if name})
    errors: list[str] = []
    links = 0
    documents = 0
    for source in paths:
        if not source.is_file():
            continue
        relative = source.relative_to(ROOT)
        if source.name == ".env" or (source.name.startswith(".env.") and source.name != ".env.example"):
            errors.append(f"Environment file must remain untracked: {relative}")
        try:
            text = source.read_text()
        except UnicodeDecodeError:
            continue
        if PRIVATE_KEY.search(text) or API_KEY.search(text):
            errors.append(f"Possible secret in {relative}; remove it before committing")
        if source.suffix != ".md":
            continue
        documents += 1
        for match in LINK.finditer(text):
            target = match[1] or match[2]
            if re.match(r"^(?:https?://|mailto:|#)", target):
                continue
            filename = re.split(r":(?=\d+$)|[?#]", target, maxsplit=1)[0]
            destination = (source.parent / unquote(filename)).resolve()
            if not destination.exists():
                errors.append(f"Missing link in {relative}: {target}")
            links += 1
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Repository checks passed: {documents} documents, {links} local links, common secret patterns checked.")


if __name__ == "__main__":
    main()
