from unittest.mock import Mock, patch
from uuid import uuid4

from sqlmodel import Session

from app.database import engine
from app.models import WorkspaceRevision
from app.workspace_snapshots import (
    AzureBlobSnapshotBackend,
    WorkspaceSnapshotService,
)


def test_azure_blob_backend_uses_connection_string():
    with patch("app.workspace_snapshots.BlobServiceClient") as service_type:
        AzureBlobSnapshotBackend("UseDevelopmentStorage=true", "snapshots")

    service_type.from_connection_string.assert_called_once_with(
        "UseDevelopmentStorage=true"
    )
    service_type.from_connection_string.return_value.get_container_client.assert_called_once_with(
        "snapshots"
    )


def test_azure_blob_backend_uses_default_credential_for_account_url():
    with (
        patch("app.workspace_snapshots.BlobServiceClient") as service_type,
        patch("azure.identity.DefaultAzureCredential") as credential_type,
    ):
        AzureBlobSnapshotBackend(
            None,
            "snapshots",
            "https://autodev.blob.core.windows.net",
        )

    service_type.assert_called_once_with(
        account_url="https://autodev.blob.core.windows.net",
        credential=credential_type.return_value,
    )
    service_type.return_value.get_container_client.assert_called_once_with(
        "snapshots"
    )


def test_snapshot_service_deletes_all_task_revision_objects():
    suffix = uuid4().hex
    task_id = f"TASK-SNAPSHOT-DELETE-{suffix}"
    keys = [f"snapshots/{suffix}/one.tar.gz", f"snapshots/{suffix}/two.tar.gz"]
    with Session(engine) as session:
        for index, key in enumerate(keys):
            session.add(WorkspaceRevision(
                id=f"REV-{suffix}-{index}",
                task_id=task_id,
                organization_id="local",
                digest=f"digest-{index}",
                object_key=key,
                size_bytes=1,
            ))
        session.commit()

    backend = Mock()
    service = WorkspaceSnapshotService(backend=backend)
    service.delete_task(task_id)

    assert {item.args[0] for item in backend.delete.call_args_list} == set(keys)
