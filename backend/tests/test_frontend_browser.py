"""Run portable production-browser acceptance against isolated HTTP/PostgreSQL services."""

import os
import re
import socket
import subprocess
import threading
import time
from contextlib import ExitStack
from pathlib import Path

import httpx2
import pytest
import uvicorn
from app.adapters.postgres import postgres_conninfo
from app.main import create_app
from psycopg import Connection
from tests.test_auth_postgres import auth as auth
from tests.test_auth_postgres import postgres_settings as postgres_settings
from tests.test_rbac_postgres import RbacFixture
from tests.test_rbac_postgres import rbac as rbac

pytestmark = [pytest.mark.infrastructure, pytest.mark.frontend_e2e]
ROOT = Path(__file__).resolve().parents[2]


def available_port() -> int:
    """Select an unprivileged loopback port; startup fails clearly if it is claimed."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def wait_for_server(url: str) -> None:
    with httpx2.Client(trust_env=False, timeout=1) as client:
        for _ in range(100):
            try:
                if client.get(url).status_code == 200:
                    return
            except httpx2.RequestError:
                pass
            time.sleep(0.1)
    raise AssertionError(f"Isolated browser test server did not become ready: {url}")


def test_admin_production_browser(rbac: RbacFixture, tmp_path: Path) -> None:
    nginx_version = subprocess.run(["nginx", "-V"], capture_output=True, text=True, check=True)
    conf_path = re.search(r"--conf-path=(\S+)", nginx_version.stderr)
    assert conf_path is not None, "nginx -V must report its configuration path"
    mime_path = Path(conf_path.group(1)).parent / "mime.types"
    assert mime_path.is_file(), "Install the Nginx MIME types alongside nginx.conf"
    api_port, chat_port, admin_port = available_port(), available_port(), available_port()
    chat_origin, admin_origin = f"http://127.0.0.1:{chat_port}", f"http://127.0.0.1:{admin_port}"
    settings = rbac.auth.settings.model_copy(
        update={"auth_chat_origins": [chat_origin], "auth_admin_origins": [admin_origin], "telemetry_enabled": False}
    )
    with Connection.connect(postgres_conninfo(settings)) as connection:
        connection.execute("DELETE FROM kb_resource_grants WHERE purpose='chat'")
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=api_port,
            log_config=None,
            access_log=False,
            proxy_headers=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    with ExitStack() as stack:
        thread.start()

        def stop_api() -> None:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive(), "Browser test API did not stop"

        stack.callback(stop_api)
        for application, port, original_port in (("chat", chat_port, 4173), ("admin", admin_port, 4174)):
            build = ROOT / "frontend" / "apps" / application / "dist"
            assert (build / "index.html").is_file(), "Run pnpm build before make frontend-e2e"
            configuration = (ROOT / "infra" / "frontend" / f"{application}.conf").read_text()
            configuration = (
                configuration.replace(f".poc-results/frontend/{application}.pid", str(tmp_path / f"{application}.pid"))
                .replace("include mime.types;", f'include "{mime_path}";')
                .replace(f"127.0.0.1:{original_port}", f"127.0.0.1:{port}")
                .replace(f"root frontend/apps/{application}/dist;", f'root "{build}";')
                .replace("127.0.0.1:8000", f"127.0.0.1:{api_port}")
            )
            config_path = tmp_path / f"{application}.conf"
            config_path.write_text(configuration)
            log = stack.enter_context((tmp_path / f"{application}.log").open("wb"))
            process = subprocess.Popen(
                ["nginx", "-p", str(ROOT) + "/", "-c", str(config_path), "-g", "daemon off;"],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            stack.callback(stop_process, process)
        for url in (f"http://127.0.0.1:{api_port}/health/live", f"{chat_origin}/login", f"{admin_origin}/login"):
            wait_for_server(url)
        subprocess.run(
            ["pnpm", "exec", "playwright", "test", "--config", "frontend/e2e/playwright.config.ts"],
            cwd=ROOT,
            env={
                **os.environ,
                "ENTERPRISE_RAG_E2E_CHAT_ORIGIN": chat_origin,
                "ENTERPRISE_RAG_E2E_ADMIN_ORIGIN": admin_origin,
            },
            check=True,
            timeout=180,
        )
