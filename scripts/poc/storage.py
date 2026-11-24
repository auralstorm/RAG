"""Run POC-08 in disposable RustFS volumes and retain non-secret functional evidence."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

from dotenv import dotenv_values
from pydantic import JsonValue, RootModel

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    output = ROOT / ".poc-results/storage"
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for filename in ("environment.json", "lifecycle.json", "backup.json", "results.xml", "report.json"):
        (output / filename).unlink(missing_ok=True)
    started = datetime.now(UTC)
    result = subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "pytest",
            "-m",
            "poc",
            "backend/tests/test_storage_poc.py",
            "-v",
            "--tb=short",
            f"--junitxml={output / 'results.xml'}",
        ],
        cwd=ROOT,
    )
    junit = output / "results.xml"
    cases = ElementTree.parse(junit).findall(".//testcase") if junit.exists() else []
    failed = [case.get("name") for case in cases if case.find("failure") is not None or case.find("error") is not None]
    skipped = [case.get("name") for case in cases if case.find("skipped") is not None]
    evidence: dict[str, JsonValue] = {}
    for name in ("environment", "lifecycle", "backup"):
        source = output / f"{name}.json"
        if source.exists():
            evidence[name] = RootModel[dict[str, JsonValue]].model_validate_json(source.read_text()).root
    passed = result.returncode == 0 and bool(cases) and len(evidence) == 3 and not failed and not skipped
    inputs = (
        "backend/tests/test_storage_poc.py",
        "backend/tests/storage_admin_cli.py",
        "infra/compose/storage-poc.yaml",
        "infra/compose/compose.yaml",
        "scripts/poc/storage.py",
        "uv.lock",
    )
    report = {
        "poc_id": "POC-08",
        "status": "FUNCTIONAL_PASS" if passed else "FAIL",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "git_head_before_changes": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "image": dotenv_values(ROOT / "infra/compose/images.env").get("RUSTFS_IMAGE"),
        "docker_arch_cpu_memory_bytes": subprocess.check_output(
            ["docker", "info", "--format", "{{.Architecture}} {{.NCPU}} {{.MemTotal}}"], text=True
        ).strip(),
        "input_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in inputs},
        "dataset_kind": "synthetic objects and ephemeral users, service accounts and STS tokens",
        "test_count": len(cases),
        "failed": failed,
        "skipped": skipped,
        "tests": [case.get("name") for case in cases],
        "evidence": evidence,
        "qualification": "Real-service functional evidence only; independent security review, browser CORS, production timing/scale, full backup and upgrade/supply-chain acceptance pending",
    }
    report_file = output / "report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"POC-08 {report['status']}; evidence: {report_file.relative_to(ROOT)}")
    raise SystemExit(0 if passed else result.returncode or 1)


if __name__ == "__main__":
    main()
