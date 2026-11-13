"""Stage 5 integration: Docker provisioner + runtime end-to-end. Skip if no docker or no agent_sandbox installed."""

from __future__ import annotations

import shutil
import subprocess as _sp

import pytest

agent_sandbox = pytest.importorskip("agent_sandbox")
shutil.which("docker") or pytest.skip("docker CLI not available", allow_module_level=True)


def _sandbox_image_available() -> bool:
    """True only when the sandbox image is present locally AND the daemon answers.

    (mock sys.modules injections from other collected test files defeat
    importorskip above, so this guard is what actually decides whether these
    end-to-end container tests can run; docker pull itself may be impossible
    offline / via a dead registry mirror)
    """
    try:
        r = _sp.run(["docker", "image", "inspect", "all-in-one-sandbox:latest"],
                    capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


_sandbox_image_available() or pytest.skip(
    "sandbox image 'all-in-one-sandbox:latest' not available (run: docker pull all-in-one-sandbox:latest)",
    allow_module_level=True,
)

from engram.backend.agents.sandbox.docker.local_container_backend import (  # noqa: E402
    LocalContainerBackend,
)
from engram.backend.agents.sandbox.docker.readiness import (  # noqa: E402
    wait_for_sandbox_ready,
)
from engram.backend.agents.sandbox.runtimes.docker_runtime import DockerRuntime  # noqa: E402


@pytest.fixture
def provisioner() -> LocalContainerBackend:
    return LocalContainerBackend(image="all-in-one-sandbox:latest", base_port=18000)


def _await_ready(provisioner: LocalContainerBackend, info) -> None:
    """Poll /v1/sandbox until ready (AIO HTTP server needs startup time)."""
    if not wait_for_sandbox_ready(info.sandbox_url, timeout=60):
        provisioner.destroy(info)
        pytest.skip(f"sandbox {info.sandbox_id} not ready within 60s")


class TestIntegration:
    """End-to-end DockerRuntime SDK calls + file operations against provisioner-created container."""

    def test_create_and_exec(self, provisioner: LocalContainerBackend) -> None:
        info = provisioner.create("test-thread", "01aa2b3c")
        try:
            assert info.sandbox_url
            _await_ready(provisioner, info)
            rt = DockerRuntime(info.sandbox_url)
            try:
                output = rt.exec_command("echo hello")
                assert "hello" in output
            finally:
                rt.close()
        finally:
            provisioner.destroy(info)

    def test_write_and_read(self, provisioner: LocalContainerBackend) -> None:
        info = provisioner.create("test-thread", "02bb4d6e")
        try:
            _await_ready(provisioner, info)
            rt = DockerRuntime(info.sandbox_url)
            try:
                rt.write_file("/mnt/engram/user-data/test.txt", "hello world")
                content = rt.read_file("/mnt/engram/user-data/test.txt")
                assert "hello world" in content
            finally:
                rt.close()
        finally:
            provisioner.destroy(info)

    def test_is_alive_and_discover(self, provisioner: LocalContainerBackend) -> None:
        info = provisioner.create("test-thread", "03cc7f9a")
        try:
            assert provisioner.is_alive(info) is True
            discovered = provisioner.discover("03cc7f9a")
            assert discovered is not None
            assert discovered.sandbox_id == "03cc7f9a"
        finally:
            provisioner.destroy(info)
            assert provisioner.is_alive(info) is False
