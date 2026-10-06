from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.behavioral_evaluation import _record_native_task, run_behavioral_evaluation
from app.database import engine
from app.evaluation import promote_agent
from app.evaluation_adapters import AdapterResult
from app.main import app
from app.models import EvaluationDataset, EvaluationRun, Project, Task
from app.registry import RegistryError


def test_dataset_requires_human_review_before_freeze():
    with TestClient(app) as client:
        response = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer", "suite_id": "baseline"},
        )
        assert response.status_code == 201
        dataset = response.json()
        assert dataset["status"] == "DRAFT"
        assert dataset["scenarios"]
        assert "mcp_tools" in dataset["scenarios"][0]
        assert client.post(
            f"/api/evaluation-datasets/{dataset['id']}/freeze",
            json={"reviewed_by": "reviewer@example.com"},
        ).status_code == 409

        reviewed = client.put(
            f"/api/evaluation-datasets/{dataset['id']}",
            json={"scenarios": dataset["scenarios"],
                  "reviewed_by": "reviewer@example.com"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "REVIEWED"
        frozen = client.post(
            f"/api/evaluation-datasets/{dataset['id']}/freeze",
            json={"reviewed_by": "reviewer@example.com"},
        )
        assert frozen.status_code == 200
        assert frozen.json()["status"] == "FROZEN"
        assert len(frozen.json()["content_hash"]) == 64
        assert client.put(
            f"/api/evaluation-datasets/{dataset['id']}",
            json={"scenarios": dataset["scenarios"],
                  "reviewed_by": "reviewer@example.com"},
        ).status_code == 409


def test_dataset_rejects_scenario_path_traversal():
    with TestClient(app) as client:
        dataset = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer", "suite_id": "baseline"},
        ).json()
        scenarios = dataset["scenarios"]
        scenarios[0]["id"] = "../../outside"
        response = client.put(
            f"/api/evaluation-datasets/{dataset['id']}",
            json={"scenarios": scenarios, "reviewed_by": "human"},
        )
        assert response.status_code == 409
        assert "Scenario ids" in response.json()["detail"]


def test_behavioral_endpoint_accepts_background_run():
    with TestClient(app) as client:
        dataset = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer", "suite_id": "baseline"},
        ).json()
        client.put(
            f"/api/evaluation-datasets/{dataset['id']}",
            json={"scenarios": dataset["scenarios"], "reviewed_by": "human"},
        )
        client.post(
            f"/api/evaluation-datasets/{dataset['id']}/freeze",
            json={"reviewed_by": "human"},
        )
        with patch(
            "app.behavioral_evaluation._run_scheduled_evaluation",
            new=AsyncMock(return_value=None),
        ):
            response = client.post(
                "/api/evaluations/behavioral",
                json={"dataset_id": dataset["id"], "adapters": ["native"]},
            )

    assert response.status_code == 202
    assert response.json()["status"] == "RUNNING"


def test_native_evaluation_task_is_linked_to_running_evaluation():
    with TestClient(app), Session(engine) as session:
        project = Project(name="evaluation-link",
                          repository_path="/tmp/evaluation-link")
        session.add(project)
        session.commit()
        session.refresh(project)
        dataset = EvaluationDataset(
            id="DATASET-LINKEDTASK01", agent_id="developer", agent_version="1.0.0",
            suite_id="baseline", suite_version="1.0.0", scenarios=[],
        )
        run = EvaluationRun(
            id="EVAL-LINKEDTASK01", agent_id="developer", agent_version="1.0.0",
            suite_id="baseline", suite_version="1.0.0", status="RUNNING",
            evaluator="behavioral-v1", overall_score=0, dataset_id=dataset.id,
        )
        task = Task(
            id="TASK-901", project_id=project.id,
            title=f"{run.id} · Writes evaluation report",
            description="Create the report", agent_id="did:local:developer",
        )
        session.add(dataset)
        session.add(run)
        session.add(task)
        session.commit()

        _record_native_task(
            session, run.id, task, dataset,
            {"id": "write-report", "name": "Writes evaluation report"},
        )
        session.refresh(run)
        task_title = task.title
        linked_tasks = run.provenance["tasks"]

    assert task_title.startswith("EVAL-LINKEDTASK01 · ")
    assert linked_tasks == [{
        "task_id": "TASK-901",
        "scenario_id": "write-report",
        "scenario_name": "Writes evaluation report",
        "dataset_id": "DATASET-LINKEDTASK01",
        "adapter": "native",
    }]


class PassingAdapter:
    def __init__(self, name: str):
        self.name = name

    async def run(self, **kwargs):
        return AdapterResult(
            adapter=self.name,
            passed=True,
            score=0.9,
            duration_seconds=1.0,
            results=[{"passed": True}],
            metrics={"latency_seconds": 1.0},
            evidence_path=f"/evidence/{self.name}",
            version="test",
        )


@pytest.mark.asyncio
async def test_behavioral_run_normalizes_native_vally_and_waza():
    with TestClient(app) as client:
        dataset = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer", "suite_id": "baseline"},
        ).json()
        client.put(
            f"/api/evaluation-datasets/{dataset['id']}",
            json={"scenarios": dataset["scenarios"], "reviewed_by": "human"},
        )
        client.post(
            f"/api/evaluation-datasets/{dataset['id']}/freeze",
            json={"reviewed_by": "human"},
        )

    native_result = {
        "id": "scenario",
        "passed": True,
        "score": 1.0,
        "dimensions": {"policy": 1.0, "security": 1.0},
        "metrics": {
            "latency_seconds": 1.0,
            "model_calls": 1,
            "input_tokens": 10,
            "output_tokens": 5,
        },
    }
    with Session(engine) as session, patch(
        "app.behavioral_evaluation._native_scenario", new=AsyncMock(return_value=native_result)
    ), patch(
        "app.behavioral_evaluation.get_adapter",
        side_effect=lambda name: PassingAdapter(name),
    ):
        run = await run_behavioral_evaluation(session, dataset["id"])

    assert run.status == "COMPLETED"
    assert run.scores["safety"] == 1.0
    assert {item["adapter"]
            for item in run.results} == {"native", "vally", "waza"}
    assert run.provenance["adapters"] == ["native", "vally", "waza"]


def test_promotion_requires_all_behavioral_adapters():
    with TestClient(app), Session(engine) as session:
        session.add(EvaluationRun(
            id="EVAL-MISSINGADAPTERS", agent_id="developer", agent_version="1.0.0",
            suite_id="baseline", suite_version="1.0.0", evaluator="behavioral-v1",
            status="COMPLETED", overall_score=1.0,
            scores={"behavioral": 1.0, "safety": 1.0},
            provenance={"adapters": ["native"]},
        ))
        session.commit()
        with pytest.raises(RegistryError, match="native Docker, Vally, and Waza"):
            promote_agent(session, "developer")
