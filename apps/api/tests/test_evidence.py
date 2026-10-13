from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.evidence import EvidenceProvider


def test_blob_evidence_round_trip_contract(tmp_path):
    settings = SimpleNamespace(
        evidence_provider="azure_blob",
        evidence_dir=str(tmp_path),
        evidence_container="autodev-evidence",
        azure_storage_connection_string="UseDevelopmentStorage=true",
        azure_storage_account_url=None,
    )
    container = MagicMock()
    container.list_blobs.return_value = [
        SimpleNamespace(name="tasks/TASK-001/task.json")
    ]
    container.download_blob.return_value.readall.return_value = b'{"status":"done"}'

    with (
        patch("app.evidence.get_settings", return_value=settings),
        patch("app.evidence.BlobServiceClient") as service_type,
    ):
        service_type.from_connection_string.return_value.get_container_client.return_value = (
            container
        )
        provider = EvidenceProvider()
        provider.write("TASK-001", "task", {"status": "done"})
        bundle = provider.bundle("TASK-001")
        provider.delete_task("TASK-001")

    container.upload_blob.assert_called_once_with(
        "tasks/TASK-001/task.json",
        b'{\n  "status": "done"\n}',
        overwrite=True,
    )
    assert bundle == {"task": {"status": "done"}}
    container.delete_blob.assert_called_once_with("tasks/TASK-001/task.json")


def test_local_evidence_deletes_all_task_files(tmp_path):
    settings = SimpleNamespace(
        evidence_provider="local",
        evidence_dir=str(tmp_path),
        evidence_container="unused",
        azure_storage_connection_string=None,
        azure_storage_account_url=None,
    )

    with patch("app.evidence.get_settings", return_value=settings):
        provider = EvidenceProvider()
        provider.write("TASK-LOCAL", "task", {"status": "done"})
        provider.write("TASK-LOCAL", "changes", {"files": []})
        provider.delete_task("TASK-LOCAL")

    assert not (tmp_path / "TASK-LOCAL").exists()
