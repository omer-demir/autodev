import importlib.util
import io
import tarfile

from fastapi.testclient import TestClient


def _load_server(tmp_path):
    path = __import__("pathlib").Path("docker/azure-session/app.py").resolve()
    spec = importlib.util.spec_from_file_location(
        "autodev_azure_session", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WORKSPACE = tmp_path / "workspace"
    return module


def _archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_azure_session_image_imports_executes_and_exports_workspace(tmp_path):
    server = _load_server(tmp_path)
    with TestClient(server.app) as client:
        imported = client.post(
            "/workspace/import",
            content=_archive({"input.txt": b"hello"}),
            headers={
                "Content-Type": "application/gzip",
                "X-Autodev-Workspace-Access": "read-write",
                "X-Autodev-Environment": '{"BUILD_MODE":"test"}',
            },
        )
        executed = client.post(
            "/execute",
            json={
                "command": [
                    "python3", "-c",
                    "import os,pathlib; pathlib.Path('output.txt').write_text(os.environ['BUILD_MODE'])",
                ],
                "timeoutMs": 10_000,
            },
        )
        exported = client.get("/workspace/export")

    assert imported.status_code == 204
    assert executed.status_code == 200
    assert executed.json()["exitCode"] == 0
    with tarfile.open(fileobj=io.BytesIO(exported.content), mode="r:gz") as archive:
        output = archive.extractfile("output.txt")
        assert output and output.read() == b"test"


def test_azure_session_image_rejects_unsafe_archive_and_sensitive_environment(tmp_path):
    server = _load_server(tmp_path)
    with TestClient(server.app) as client:
        unsafe_path = client.post(
            "/workspace/import", content=_archive({"../escape.txt": b"no"})
        )
        sensitive_environment = client.post(
            "/workspace/import",
            content=_archive({"safe.txt": b"yes"}),
            headers={"X-Autodev-Environment": '{"API_TOKEN":"secret"}'},
        )

    assert unsafe_path.status_code == 400
    assert sensitive_environment.status_code == 400
