"""Run POC-01 in its disposable ES project and save non-secret functional evidence."""

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
    output = ROOT / ".poc-results/search"
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    environment_file = output / "environment.json"
    environment_file.unlink(missing_ok=True)
    junit_file = output / "results.xml"
    junit_file.unlink(missing_ok=True)
    started = datetime.now(UTC)
    result = subprocess.run(
        [
            "uv",
            "run",
            "--locked",
            "pytest",
            "-m",
            "poc",
            "backend/tests/test_search_poc.py",
            "-v",
            f"--junitxml={junit_file}",
        ],
        cwd=ROOT,
    )
    cases = ElementTree.parse(junit_file).findall(".//testcase") if junit_file.exists() else []
    failed = [case.get("name") for case in cases if case.find("failure") is not None or case.find("error") is not None]
    skipped = [case.get("name") for case in cases if case.find("skipped") is not None]
    environment = (
        RootModel[dict[str, JsonValue]].model_validate_json(environment_file.read_text()).root
        if environment_file.exists()
        else {}
    )
    passed = result.returncode == 0 and bool(cases) and bool(environment) and not failed and not skipped
    dataset = ROOT / "backend/tests/fixtures/search-poc.json"
    docker = subprocess.check_output(
        [
            "docker",
            "info",
            "--format",
            "{{.Architecture}} {{.NCPU}} {{.MemTotal}}",
        ],
        text=True,
    ).strip()
    report = {
        "poc_id": "POC-01",
        "status": "FUNCTIONAL_PASS" if passed else "FAIL",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "git_head_before_changes": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "image": dotenv_values(ROOT / "infra/compose/images.env").get("ELASTICSEARCH_IMAGE"),
        "docker_arch_cpu_memory_bytes": docker,
        "environment": environment,
        "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
        "dataset_kind": "synthetic, fixed 3-dimensional vectors; not business Golden Dataset",
        "configuration": {"dimensions": 3, "rrf_rank_constant": 60, "candidate_k": 40, "top_k": 3},
        "test_count": len(cases),
        "failed": failed,
        "skipped": skipped,
        "tests": [case.get("name") for case in cases],
        "qualification": "Real-service functional checks only; business quality, load, identity integration and independent security review pending.",
    }
    report_file = output / "report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"POC-01 {report['status']}; evidence: {report_file.relative_to(ROOT)}")
    raise SystemExit(0 if passed else result.returncode or 1)


if __name__ == "__main__":
    main()
