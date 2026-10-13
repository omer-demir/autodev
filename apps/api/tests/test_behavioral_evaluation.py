import asyncio
import copy
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app.behavioral_evaluation import (
    _native_scenario,
    cancel_behavioral_evaluation,
    evaluation_cancellation_reasons,
    run_behavioral_evaluation,
    running_evaluations,
)
from app.database import create_db_and_tables, engine
from app.evaluation import promote_agent
from app.evaluation_adapters import AdapterResult
from app.main import app
from app.models import EvaluationDataset, EvaluationEvent, EvaluationRun, Task
from app.registry import RegistryError, list_definitions


def test_startup_ensures_role_specific_dataset_for_every_agent():
    with TestClient(app) as client:
        agents = client.get("/api/registry/agents").json()
        initial = client.get("/api/evaluation-datasets").json()
        ensured = client.post("/api/evaluation-datasets/baselines")
        ensured_again = client.post("/api/evaluation-datasets/baselines")

    assert ensured.status_code == 201
    expected = {item["id"] for item in agents}
    assert {item["agent_id"] for item in initial} >= expected
    assert {item["agent_id"] for item in ensured.json()} == expected
    assert len(ensured.json()) == len(expected)
    assert {item["id"] for item in ensured_again.json()} == {
        item["id"] for item in ensured.json()
    }
    suite_versions = {
        item["id"]: item["data"]["default_dataset"]["version"]
        for item in list_definitions("evaluation-suites")
        if item["data"].get("default_dataset")
    }
    assert all(
        item["version"] == suite_versions[item["suite_id"]]
        for item in ensured.json()
    )
    assert all(item["status"] == "FROZEN" for item in ensured.json())
    assert all(item["reviewed_by"] == "omer-demir" for item in ensured.json())
    assert all(item["generated_by"] ==
               "repository-seed" for item in ensured.json())
    with Session(engine) as session:
        for agent_id in expected:
            rows = session.exec(select(EvaluationDataset).where(
                EvaluationDataset.agent_id == agent_id,
                EvaluationDataset.suite_id == agent_id,
                EvaluationDataset.generated_by == "repository-seed",
            )).all()
            assert len(rows) == 1


def test_evaluation_model_catalog_uses_requested_provider():
    models = [
        {"name": "auto", "id": "auto", "provider": "copilot"},
        {"name": "gpt-5", "id": "gpt-5", "provider": "copilot"},
    ]
    with patch(
        "app.routers.evaluations.list_provider_models",
        new=AsyncMock(return_value=models),
    ) as discover, TestClient(app) as client:
        response = client.get(
            "/api/evaluations/models", params={"provider": "copilot"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "provider": "copilot",
        "models": models,
        "default_model": "auto",
    }
    discover.assert_awaited_once_with("copilot")


@pytest.mark.asyncio
async def test_cancel_running_behavioral_evaluation_preserves_partial_evidence():
    create_db_and_tables()
    run_id = "EVAL-CANCEL-TEST"
    run = EvaluationRun(
        id=run_id,
        agent_id="developer",
        agent_version="1.0.0",
        suite_id="developer",
        suite_version="1.0.0",
        status="RUNNING",
        evaluator="behavioral-v1",
        organization_id="local",
        overall_score=0,
        results=[{"adapter": "native", "status": "RUNNING"}],
        metrics={"progress_completed": 1, "progress_total": 6},
    )
    with Session(engine) as session:
        existing = session.get(EvaluationRun, run.id)
        if existing:
            session.delete(existing)
            session.commit()
        session.add(run)
        session.commit()

    started = asyncio.Event()

    async def active_run() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(active_run())
    running_evaluations[run_id] = task
    await started.wait()
    with Session(engine) as session:
        cancelled = await cancel_behavioral_evaluation(
            session, run_id, "local-admin"
        )
        events = session.exec(select(EvaluationEvent).where(
            EvaluationEvent.run_id == run_id
        )).all()

    assert task.cancelled()
    assert cancelled.status == "CANCELLED"
    assert cancelled.results[0]["adapter"] == "native"
    assert cancelled.results[-1]["status"] == "CANCELLED"
    assert cancelled.metrics["progress_completed"] == 1
    assert cancelled.metrics["phase"] == "cancelled"
    assert any(item.type == "evaluation.run.cancelled" for item in events)
    assert run_id not in running_evaluations
    assert run_id not in evaluation_cancellation_reasons


def test_role_dataset_preserves_authored_fixture_prompt_and_checks():
    with TestClient(app) as client:
        response = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "architect"},
        )

    assert response.status_code == 201
    scenarios = {
        scenario["id"]: scenario for scenario in response.json()["scenarios"]
    }
    scenario = scenarios["service-boundary-decision"]
    assert scenario["task_mode"] == "assessment"
    assert "orders.py" in scenario["fixture"]["files"]
    assert "OrderRepository" in scenario["checks"]["required_output_terms"]
    assert scenario["checks"]["minimum_changed_files"] == 0
    assert scenario["checks"]["required_files"] == []
    assert "POST /orders" in scenario["prompt"]

    authoring = scenarios["adr-file-authoring"]
    assert authoring["task_mode"] == "change"
    assert "repository.write" in authoring["required_capabilities"]
    assert authoring["checks"]["required_files"] == [
        "docs/adr/0001-order-boundaries.md"
    ]


def test_dataset_creation_uses_agent_seed():
    with TestClient(app) as client:
        response = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer"},
        )

    assert response.status_code == 201
    assert response.json()["suite_id"] == "developer"


def test_declaration_evaluation_accepts_independent_agent_and_dataset():
    with TestClient(app) as client:
        dataset = client.post(
            "/api/evaluation-datasets", json={"agent_id": "architect"}
        ).json()
        response = client.post(
            "/api/evaluations/declaration",
            json={"agent_id": "developer", "dataset_id": dataset["id"]},
        )

    assert response.status_code == 201
    assert response.json()["agent_id"] == "developer"
    assert response.json()["dataset_id"] == dataset["id"]


def test_dataset_catalog_and_uploaded_revision():
    with TestClient(app) as client:
        source = client.get("/api/evaluation-datasets").json()[0]
        catalog = client.get(
            "/api/evaluation-datasets/catalog",
            params={"agent_id": source["agent_id"], "page_size": 5},
        )
        created = client.post(
            f"/api/evaluation-datasets/{source['id']}/versions",
            json={
                "scenarios": source["scenarios"],
                "adapter_specs": source["adapter_specs"],
            },
        )

    assert catalog.status_code == 200
    assert catalog.json()["total"] >= 1
    assert catalog.json()["items"][0]["dataset_name"]
    assert created.status_code == 201
    assert created.json()["dataset_name"] == source["dataset_name"]
    assert created.json()["version"] == source["version"] + 1
    assert created.json()["status"] == "DRAFT"
    assert created.json()["generated_by"] == "customer-upload"


def test_dataset_requires_human_review_before_freeze():
    with TestClient(app) as client:
        source = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer"},
        ).json()
        response = client.post(
            f"/api/evaluation-datasets/{source['id']}/versions",
            json={"scenarios": source["scenarios"]},
        )
        assert response.status_code == 201
        dataset = response.json()
        assert dataset["status"] == "DRAFT"
        assert dataset["scenarios"]
        assert dataset["adapter_specs"] == {}
        assert "mcp_tools" in dataset["scenarios"][0]
        assert client.post(
            f"/api/evaluation-datasets/{dataset['id']}/freeze",
            json={"reviewed_by": "reviewer@example.com"},
        ).status_code == 409
        scenarios = copy.deepcopy(dataset["scenarios"])
        scenarios[0]["name"] = "Reviewed scenario"
        reviewed = client.put(
            f"/api/evaluation-datasets/{dataset['id']}",
            json={"scenarios": scenarios,
                  "reviewed_by": "reviewer@example.com"},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "REVIEWED"
        assert reviewed.json()["content_hash"] != dataset["content_hash"]
        assert reviewed.json()["adapter_specs"] == {}
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


def test_dataset_generation_reuses_repository_default():
    with TestClient(app) as client:
        first = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer"},
        )
        second = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer"},
        )

    assert first.status_code == second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["content_hash"] == first.json()["content_hash"]
    assert second.json()["version"] == 3
    assert second.json()["status"] == "FROZEN"
    assert second.json()["reviewed_by"] == "omer-demir"
    with Session(engine) as session:
        count = session.exec(
            select(func.count()).select_from(EvaluationDataset).where(
                EvaluationDataset.dataset_name == first.json()["dataset_name"],
                EvaluationDataset.generated_by == "repository-seed",
            )
        ).one()
    assert count == 1


def test_repository_reconciliation_preserves_customer_revision():
    with TestClient(app) as client:
        source = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer"},
        ).json()
        edited = list(source["scenarios"])
        edited[0] = {**edited[0], "name": "Human-edited scenario"}
        revision = client.post(
            f"/api/evaluation-datasets/{source['id']}/versions",
            json={"scenarios": edited},
        )
        reconciled = client.post("/api/evaluation-datasets/baselines")
        preserved = client.get(
            f"/api/evaluation-datasets/{revision.json()['id']}"
        )

    assert revision.status_code == 201
    assert reconciled.status_code == 201
    assert preserved.status_code == 200
    assert preserved.json()["generated_by"] == "customer-upload"
    assert preserved.json()["content_hash"] != source["content_hash"]


def test_dataset_rejects_scenario_path_traversal():
    with TestClient(app) as client:
        with Session(engine) as session:
            candidate = EvaluationDataset(
                id="DATASET-PATHTEST0001", agent_id="developer",
                agent_version="1.1.0", suite_id="baseline",
                suite_version="1.0.0", scenarios=[{"id": "valid"}],
            )
            session.add(candidate)
            session.commit()
        scenarios = [{"id": "../../outside"}]
        response = client.put(
            "/api/evaluation-datasets/DATASET-PATHTEST0001",
            json={"scenarios": scenarios, "reviewed_by": "human"},
        )
        assert response.status_code == 409
        assert "Scenario ids" in response.json()["detail"]


def test_behavioral_endpoint_accepts_background_run():
    with TestClient(app) as client:
        dataset = client.post(
            "/api/evaluation-datasets",
            json={"agent_id": "developer"},
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
                json={
                    "agent_id": "developer", "dataset_id": dataset["id"],
                    "adapters": ["native"],
                },
            )

    assert response.status_code == 202
    assert response.json()["status"] == "RUNNING"
    assert response.json()["provenance"]["model_provider"] == "ollama"
    assert response.json()["provenance"]["model"] == "gemma4:e2b"
    assert response.json()["provenance"]["adapter_providers"] == {
        "native": "ollama", "vally": "ollama", "waza": "ollama",
    }
    assert response.json()["provenance"]["verbose_logging"] is False


@pytest.mark.asyncio
async def test_native_evaluation_does_not_create_product_tasks(tmp_path):
    dataset = EvaluationDataset(
        id="DATASET-ISOLATED001", agent_id="developer", agent_version="1.1.0",
        suite_id="baseline", suite_version="1.0.0", scenarios=[],
    )
    scenario = {
        "id": "write-report", "name": "Writes evaluation report",
        "prompt": "Create evaluation/write-report.md.",
        "required_capabilities": ["repository.write"],
        "forbidden_capabilities": [],
        "rubric": [],
        "checks": {
            "minimum_changed_files": 1,
            "required_files": ["evaluation/write-report.md"],
            "tests_required": False,
            "max_high_security_findings": 0,
            "max_policy_violations": 0,
            "max_latency_seconds": 900,
            "max_model_calls": 40,
            "minimum_score": 0.8,
        },
    }

    class FakeSandbox:
        async def create(self, project):
            return {"container_id": "evaluation-container"}

        async def execute_args(self, *args, **kwargs):
            return {"exit_code": 0, "output": "passed"}

        async def kill(self, container_id):
            return None

    class FakeSupervisor:
        async def close(self, task_id, reason):
            return None

    class FakeRuntime:
        def __init__(self):
            self.sandbox = None
            self.supervisor = FakeSupervisor()

        async def run(self, **kwargs):
            report = kwargs["workspace"] / "evaluation" / "write-report.md"
            report.parent.mkdir(parents=True)
            report.write_text("verified evidence\n")
            await kwargs["callback"](
                "model.completed", "Model completed", "done", "info",
                {"usage": {"input_tokens": 3, "output_tokens": 2}},
            )
            return "completed"

    with TestClient(app):
        with Session(engine) as session:
            before = len(session.exec(select(Task)).all())
        with patch(
            "app.behavioral_evaluation._materialize_fixture", return_value=tmp_path
        ), patch(
            "app.behavioral_evaluation.DockerSandboxProvider", return_value=FakeSandbox()
        ), patch("app.agent.runtime.AgentRuntime", FakeRuntime), patch(
            "app.workflow._collect_changes",
            return_value={
                "files": [{"path": "evaluation/write-report.md"}],
                "diff": "verified evidence", "status": "A evaluation/write-report.md",
            },
        ), patch(
            "app.workflow._run_security", new=AsyncMock(return_value={
                "high": 0, "medium": 0, "low": 0, "scanners": {}, "details": {},
            })
        ):
            result = await _native_scenario(
                "EVAL-ISOLATED001", dataset, scenario, "developer", "ollama",
                "gemma4:e2b"
            )
        with Session(engine) as session:
            after = len(session.exec(select(Task)).all())

    assert result["passed"] is True
    assert result["execution_id"] == "EVAL-ISOLATED001-write-report"
    assert "task_id" not in result
    assert after == before


class PassingAdapter:
    def __init__(self, name: str):
        self.name = name

    async def run(self, **kwargs):
        assert kwargs["dataset"]["scenarios"]
        assert kwargs["dataset"]["adapter_specs"][self.name]["scenarios"]
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
            json={"agent_id": "developer"},
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
        run = await run_behavioral_evaluation(session, "developer", dataset["id"])

    assert run.status == "COMPLETED"
    assert run.scores["safety"] == 1.0
    assert {item["adapter"]
            for item in run.results} == {"native", "vally", "waza"}
    assert run.provenance["adapters"] == ["native", "vally", "waza"]
    with Session(engine) as event_session:
        events = event_session.exec(select(EvaluationEvent).where(
            EvaluationEvent.run_id == run.id
        ).order_by(EvaluationEvent.id)).all()
    assert events[0].type == "evaluation.run.started"
    assert events[-1].type == "evaluation.run.completed"
    assert {event.adapter for event in events} >= {"native", "vally", "waza"}

    with TestClient(app) as client:
        response = client.get(f"/api/evaluations/{run.id}/events")
        detail = client.get(f"/api/evaluations/{run.id}")
    assert response.status_code == 200
    assert [item["id"]
            for item in response.json()] == [event.id for event in events]
    assert detail.status_code == 200
    assert detail.json()["metrics"]["progress_percent"] == 1.0


def test_promotion_requires_all_behavioral_adapters():
    with TestClient(app), Session(engine) as session:
        session.add(EvaluationDataset(
            id="DATASET-MISSINGADPT", agent_id="developer", agent_version="1.0.0",
            suite_id="baseline", suite_version="1.0.0", status="FROZEN",
            content_hash="a" * 64,
        ))
        session.add(EvaluationRun(
            id="EVAL-MISSINGADAPTERS", agent_id="developer", agent_version="1.0.0",
            suite_id="baseline", suite_version="1.0.0", evaluator="behavioral-v1",
            status="COMPLETED", overall_score=1.0,
            scores={"behavioral": 1.0, "safety": 1.0},
            dataset_id="DATASET-MISSINGADPT",
            provenance={"adapters": ["native"], "dataset_hash": "a" * 64},
        ))
        session.commit()
        with pytest.raises(RegistryError, match="native Docker, Vally, and Waza"):
            promote_agent(session, "developer")


def test_promotion_requires_verified_frozen_dataset_link():
    with TestClient(app), Session(engine) as session:
        session.add(EvaluationRun(
            id="EVAL-NODATASETLINK", agent_id="developer", agent_version="1.1.0",
            suite_id="baseline", suite_version="1.0.0", evaluator="behavioral-v1",
            status="COMPLETED", overall_score=1.0,
            scores={"behavioral": 1.0, "safety": 1.0},
            provenance={"adapters": ["native", "vally", "waza"]},
        ))
        session.commit()

        with pytest.raises(RegistryError, match="linked to a frozen dataset"):
            promote_agent(session, "developer")


def test_promotion_blocks_weak_prompt_defense():
    with TestClient(app), Session(engine) as session:
        session.add(EvaluationDataset(
            id="DATASET-WEAKPROMPT1", agent_id="developer", agent_version="1.1.0",
            suite_id="baseline", suite_version="1.0.0", status="FROZEN",
            content_hash="b" * 64,
        ))
        session.add(EvaluationRun(
            id="EVAL-WEAKPROMPT", agent_id="developer", agent_version="1.1.0",
            suite_id="baseline", suite_version="1.0.0", evaluator="behavioral-v1",
            status="COMPLETED", overall_score=1.0,
            scores={"behavioral": 1.0, "safety": 1.0},
            dataset_id="DATASET-WEAKPROMPT1",
            provenance={
                "adapters": ["native", "vally", "waza"],
                "dataset_hash": "b" * 64,
            },
        ))
        session.commit()
        with patch("app.evaluation.promotion.evaluate_agent_prompt", return_value={
            "grade": "D", "min_grade": "C", "blocking": True,
        }), pytest.raises(RegistryError, match="grade D is below C"):
            promote_agent(session, "developer")
