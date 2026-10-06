import io
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.model_catalog import _copilot_models, _usd_rate_card, list_runtime_models
from app.providers import AzureContainerAppsSessionProvider, DockerSandboxProvider


def test_sandbox_reports_actionable_missing_docker_error():
    provider = DockerSandboxProvider()

    with patch("app.providers.shutil.which", return_value=None), pytest.raises(
        RuntimeError, match="recreate the API container"
    ):
        provider.executable()


@pytest.mark.asyncio
async def test_sandbox_readiness_distinguishes_unreachable_daemon():
    provider = DockerSandboxProvider()
    completed = __import__("subprocess").CompletedProcess(
        [], 1, "", "daemon unavailable")

    with patch.object(provider, "executable", return_value="/usr/bin/docker"), patch.object(
        provider, "_run", return_value=completed
    ):
        status = await provider.readiness()

    assert status["cli"] is True
    assert status["daemon"] is False
    assert status["ready"] is False


@pytest.mark.asyncio
async def test_sandbox_rejects_mount_outside_workspace_root():
    provider = DockerSandboxProvider()

    with pytest.raises(RuntimeError, match="Sandbox workspace must be inside"):
        await provider._host_path(str(Path.cwd().resolve()))


@pytest.mark.asyncio
async def test_sandbox_execute_args_uses_configured_command_timeout():
    provider = DockerSandboxProvider()
    completed = __import__("subprocess").CompletedProcess([], 0, "ok", "")

    with patch("app.providers.get_settings", return_value=SimpleNamespace(
        sandbox_command_timeout_seconds=1800,
    )), patch.object(provider, "_run", new=AsyncMock(return_value=completed)) as run:
        result = await provider.execute_args("container", ["npm", "run", "build"])

    assert result["exit_code"] == 0
    run.assert_awaited_once_with(
        ["exec", "-i", "container", "npm", "run", "build"], timeout=1800
    )


@pytest.mark.asyncio
async def test_azure_sandbox_round_trips_workspace_and_stops_session(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".git").write_text("gitdir: /host/worktree\n")
    (workspace / "before.txt").write_text("before")
    requests = []
    remote_archive = b""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal remote_archive
        requests.append(request)
        if request.url.path == "/workspace/import":
            remote_archive = request.content
        if request.url.path == "/execute":
            files: dict[str, bytes] = {}
            with tarfile.open(fileobj=io.BytesIO(remote_archive), mode="r:gz") as imported:
                for member in imported.getmembers():
                    if member.isfile():
                        source = imported.extractfile(member)
                        assert source is not None
                        files[member.name] = source.read()
            files["after.txt"] = b"after"
            exported = io.BytesIO()
            with tarfile.open(fileobj=exported, mode="w:gz") as archive:
                for name, data in files.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            remote_archive = exported.getvalue()
            return httpx.Response(200, json={
                "exitCode": 0, "stdout": "remote-ok\n", "stderr": "",
                "durationMs": 12, "truncated": False,
            })
        if request.url.path == "/workspace/export":
            return httpx.Response(200, content=remote_archive)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AzureContainerAppsSessionProvider(
        endpoint="https://pool.example.azurecontainerapps.io",
        network_mode="bridge",
        pool_profile="python-hyperv-2cpu-2gi-egress",
        cpu_limit=2,
        memory_mb=2048,
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    with patch("app.providers.get_settings", return_value=SimpleNamespace(
        sandbox_command_timeout_seconds=1800,
    )):
        created = await provider.create({
            "workspace": str(workspace),
            "network_mode": "bridge",
            "pool_profile": "python-hyperv-2cpu-2gi-egress",
        })
        (workspace / "host-edit.txt").write_text("host edit")
        result = await provider.execute_args(created["container_id"], ["python", "--version"])
        await provider.kill(created["container_id"])

    assert result["output"] == "remote-ok\n"
    assert (workspace / "after.txt").read_text() == "after"
    assert (workspace / "host-edit.txt").read_text() == "host edit"
    assert (workspace / ".git").read_text() == "gitdir: /host/worktree\n"
    assert [request.url.path for request in requests] == [
        "/workspace/import", "/workspace/import", "/execute", "/workspace/export",
        "/.management/stopSession",
    ]
    assert all(request.headers["Authorization"] ==
               "Bearer test-token" for request in requests)
    assert requests[-1].url.params["api-version"] == "2025-02-02-preview"
    await client.aclose()


@pytest.mark.asyncio
async def test_azure_sandbox_does_not_apply_export_over_newer_host_change(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "source.txt"
    source.write_text("initial")
    requests = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/execute":
            source.write_text("newer host edit")
            return httpx.Response(200, json={"exitCode": 0, "stdout": "", "stderr": ""})
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = AzureContainerAppsSessionProvider(
        endpoint="https://pool.example.azurecontainerapps.io",
        network_mode="none",
        pool_profile="offline",
        cpu_limit=2,
        memory_mb=2048,
        token_provider=AsyncMock(return_value="test-token"),
        client=client,
    )
    with patch("app.providers.get_settings", return_value=SimpleNamespace(
        sandbox_command_timeout_seconds=1800,
    )):
        created = await provider.create({"workspace": str(workspace)})
        with pytest.raises(RuntimeError, match="remote export was not applied"):
            await provider.execute_args(created["container_id"], ["python", "-m", "pytest"])
        await provider.kill(created["container_id"])

    assert source.read_text() == "newer host edit"
    assert [request.url.path for request in requests] == [
        "/workspace/import", "/workspace/import", "/execute", "/.management/stopSession",
    ]
    await client.aclose()


@pytest.mark.asyncio
async def test_azure_sandbox_rejects_unenforceable_network_profile(tmp_path):
    provider = AzureContainerAppsSessionProvider(
        endpoint="https://pool.example.azurecontainerapps.io",
        network_mode="none",
        pool_profile="offline",
        cpu_limit=2,
        memory_mb=2048,
        token_provider=AsyncMock(return_value="test-token"),
    )

    with pytest.raises(RuntimeError, match="network mode is none"):
        await provider.create({"workspace": str(tmp_path), "network_mode": "bridge"})


@pytest.mark.asyncio
async def test_model_catalog_uses_ollama_as_configured_provider():
    settings = SimpleNamespace(model_provider="ollama")
    models = [{"name": "local", "provider": "ollama"}]

    with patch("app.model_catalog.get_settings", return_value=settings), patch(
        "app.model_catalog._ollama_models", new=AsyncMock(return_value=models)
    ) as discover:
        result = await list_runtime_models()

    assert result == models
    discover.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_model_catalog_marks_ollama_models_as_fallback():
    settings = SimpleNamespace(
        model_provider="copilot", model_fallback_provider="ollama"
    )
    fallback = [{"name": "local", "provider": "ollama", "fallback": True}]

    with patch("app.model_catalog.get_settings", return_value=settings), patch(
        "app.model_catalog._copilot_models",
        new=AsyncMock(side_effect=RuntimeError("unavailable")),
    ), patch(
        "app.model_catalog._ollama_models", new=AsyncMock(return_value=fallback)
    ) as discover:
        result = await list_runtime_models()

    assert result == fallback
    discover.assert_awaited_once_with(fallback=True)


@pytest.mark.asyncio
async def test_copilot_catalog_checks_authentication_before_listing_models():
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get_auth_status.return_value = SimpleNamespace(
        isAuthenticated=False)
    settings = SimpleNamespace(
        copilot_home="~/.copilot",
        copilot_cli_path="copilot",
        runtime_discovery_timeout_seconds=10,
    )

    with patch("app.model_catalog.get_settings", return_value=settings), patch(
        "app.model_catalog.shutil.which", return_value="/usr/local/bin/copilot"
    ), patch(
        "app.model_catalog._copilot_model_cache", None
    ), patch(
        "app.model_catalog.CopilotClient", return_value=client
    ), pytest.raises(RuntimeError, match="not authenticated"):
        await _copilot_models()

    client.get_auth_status.assert_awaited_once_with()
    client.list_models.assert_not_awaited()


def test_copilot_billing_metadata_converts_ai_credits_to_usd():
    rate = _usd_rate_card({
        "billing": {
            "discount_percent": None,
            "token_prices": {
                "batch_size": 1_000_000,
                "input_price": 800,
                "output_price": 4000,
                "cache_read_price": 80,
                "cache_write_price": 1000,
                "max_prompt_tokens": 272_000,
                "long_context": {
                    "input_price": 1600,
                    "output_price": 6000,
                    "cache_read_price": 160,
                    "cache_write_price": 2000,
                },
            },
        },
    })

    assert rate is not None
    assert rate["input_per_million_usd"] == 8
    assert rate["output_per_million_usd"] == 40
    assert rate["long_context"]["threshold_input_tokens"] == 272_000
    assert rate["long_context"]["input_per_million_usd"] == 16
