import base64
import json
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.main import _conversation_instructions, app
from app.model_catalog.generation import ChatUsage
from app.models import Message, Project, Task, TaskArtifact


def test_standalone_chat_instructions_use_native_image_generation_when_available():
    instructions = _conversation_instructions([], [])

    assert "use a native image-generation tool if one is available" in instructions
    assert "Do not replace an image with an HTML page" in instructions
    assert "use it for current information and cite sources" in instructions
    assert "no repository workspace or filesystem access" in instructions


def test_repository_chat_creation_persists_team_skills_and_initial_message():
    create_db_and_tables()
    insert_order = []
    project_id = None
    with Session(engine) as session:
        project = Project(
            name=f"Chat repo {uuid4().hex[:8]}",
            repository_path="/tmp",
            source_type="local",
            organization_id="local",
            created_by="chat-api-test",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id

    def capture_insert_order(
        connection, cursor, statement, parameters, context, executemany
    ):
        normalized = statement.lstrip().lower()
        if normalized.startswith("insert into task "):
            insert_order.append("task")
        elif normalized.startswith("insert into message "):
            insert_order.append("message")

    event.listen(engine, "before_cursor_execute", capture_insert_order)
    try:
        with TestClient(app) as client, patch(
            "app.main.schedule_task",
            return_value=SimpleNamespace(id="JOB-chat-test"),
        ):
            response = client.post("/api/chats", json={
                "message": f"Remember this chat {uuid4().hex}",
                "project_id": project_id,
                "agent_ids": ["did:local:developer", "did:local:tester"],
                "skill_ids": ["rpi-research"],
                "model_name": "auto",
                "approval_strategy": "agent_policy",
            })

            assert response.status_code == 202, response.text
            body = response.json()
            chat_id = body["chat"]["id"]
            assert body["status"] == "started"
            assert body["execution_job_id"] == "JOB-chat-test"
            assert len(body["chat"]["title"]) < 30
            assert body["chat"]["project_id"] == project_id
            assert body["chat"]["agent_ids"] == [
                "did:local:developer",
                "did:local:tester",
            ]
            assert body["chat"]["skill_ids"] == ["rpi-research"]
            assert body["chat"]["model_name"] == "auto"
            assert body["messages"][0]["role"] == "user"

            history = client.get(f"/api/chats/{chat_id}")
            assert history.status_code == 200
            assert history.json()["chat"]["id"] == chat_id
            assert history.json()["task"]["project_id"] == project_id
            assert history.json()["messages"][0]["content"] == body["messages"][0]["content"]
            assert chat_id in {
                item["id"] for item in client.get("/api/chats").json()["items"]
            }
        with Session(engine) as session:
            task = session.get(Task, chat_id)
            assert task is not None
            assert task.is_chat
            assert task.selected_agents == ["did:local:developer", "did:local:tester"]
            assert task.additional_skills == ["rpi-research"]
            assert task.model_name == "auto"
            assert task.approval_strategy == "agent_policy"
            assert session.exec(
                select(Message).where(Message.task_id == chat_id)
            ).first().content.startswith("Remember this chat")
            artifact = session.exec(select(TaskArtifact).where(
                TaskArtifact.task_id == chat_id,
                TaskArtifact.kind == "workflow-definition",
            )).first()
            assert [stage["agent"] for stage in artifact.content["definition"]["stages"]] == [
                "did:local:developer",
                "did:local:tester",
            ]
            assert artifact.content["definition"]["orchestration"]["mode"] == "sequential"
            project = session.get(Project, task.project_id)
            assert project is not None and not project.workspace_only
    finally:
        event.remove(engine, "before_cursor_execute", capture_insert_order)
    assert insert_order.index("task") < insert_order.index("message")


def test_repository_free_chat_persists_conversation_without_creating_task():
    with TestClient(app) as client, patch(
        "app.main.list_runtime_models",
        new=AsyncMock(return_value=[{"name": "auto", "provider": "copilot"}]),
    ), patch(
        "app.main.generate_chat_response",
        new=AsyncMock(return_value=("Hello from chat mode.", [])),
    ):
        response = client.post("/api/chats", json={
            "message": f"Remember this conversation {uuid4().hex}",
            "model_name": "auto",
            "approval_strategy": "agent_policy",
        })
        assert response.status_code == 202, response.text
        body = response.json()
        chat_id = body["chat"]["id"]
        assert body["status"] == "completed"
        assert body["chat"]["project_id"] is None
        assert body["task"] is None
        assert [message["role"] for message in body["messages"]] == [
            "user",
            "assistant",
        ]
        assert body["messages"][1]["content"] == "Hello from chat mode."
        assert client.get(f"/api/chats/{chat_id}").json()["task"] is None
        assert chat_id in {
            item["id"] for item in client.get("/api/chats").json()["items"]
        }
        follow_up = client.post(
            f"/api/chats/{chat_id}/messages",
            json={"content": "What about the next question?"},
        )
        assert follow_up.status_code == 202, follow_up.text
        history = client.get(f"/api/chats/{chat_id}").json()
        assert [message["role"] for message in history["messages"]] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]

    with Session(engine) as session:
        assert session.get(Task, chat_id) is None


def test_repository_free_chat_streams_initial_and_follow_up_responses():
    responses = iter(["First streamed answer.", "Second streamed answer."])

    async def generate_response(*, on_text_delta, on_usage, **_kwargs):
        answer = next(responses)
        await on_text_delta(answer)
        on_usage(ChatUsage(
            provider="foundry",
            model="gpt-6-sol",
            input_tokens=12,
            output_tokens=4,
        ))
        return answer, []

    def completed_event(response):
        for block in response.text.split("\n\n"):
            if block.startswith("event: complete"):
                data = next(
                    line.removeprefix("data: ")
                    for line in block.splitlines()
                    if line.startswith("data: ")
                )
                return json.loads(data)
        raise AssertionError("The response stream has no completion event")

    with TestClient(app) as client, patch(
        "app.main.list_runtime_models",
        new=AsyncMock(return_value=[{"name": "gpt-6-sol", "provider": "foundry"}]),
    ), patch(
        "app.main.generate_chat_response",
        new=AsyncMock(side_effect=generate_response),
    ), patch(
        "app.main.estimate_model_call_cost",
        return_value=(0.000123, "test rate card"),
    ):
        response = client.post(
            "/api/chats?stream=true",
            json={
                "message": f"Stream this chat {uuid4().hex}",
                "model_name": "gpt-6-sol",
                "approval_strategy": "agent_policy",
            },
        )
        assert response.status_code == 202, response.text
        assert "event: delta" in response.text
        initial = completed_event(response)
        chat_id = initial["chat"]["id"]
        assert initial["messages"][-1]["content"] == "First streamed answer."
        assert initial["messages"][-1]["model_provider"] == "foundry"
        assert initial["messages"][-1]["model_name"] == "gpt-6-sol"
        assert initial["messages"][-1]["input_tokens"] == 12
        assert initial["messages"][-1]["output_tokens"] == 4
        assert initial["messages"][-1]["estimated_cost_usd"] == 0.000123
        assert initial["chat"]["model_provider"] == "foundry"

        follow_up = client.post(
            f"/api/chats/{chat_id}/messages?stream=true",
            json={"content": "Continue streaming"},
        )
        assert follow_up.status_code == 202, follow_up.text
        assert "event: delta" in follow_up.text
        completed = completed_event(follow_up)
        assert [message["role"] for message in completed["messages"]] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert completed["messages"][-1]["content"] == "Second streamed answer."


def test_repository_free_chat_saves_and_serves_image_attachments():
    image = b"small test image"
    with TestClient(app) as client, patch(
        "app.main.list_runtime_models",
        new=AsyncMock(return_value=[{"name": "auto", "provider": "copilot"}]),
    ), patch(
        "app.main.generate_chat_response",
        new=AsyncMock(return_value=(
            "It looks like a test image.",
            [{
                "name": "generated.png",
                "media_type": "image/png",
                "data": base64.b64encode(image).decode("ascii"),
            }],
        )),
    ) as generate:
        response = client.post("/api/chats", json={
            "message": "Describe this",
            "model_name": "auto",
            "attachments": [{
                "name": "test.png",
                "media_type": "image/png",
                "data": base64.b64encode(image).decode("ascii"),
            }],
            "approval_strategy": "agent_policy",
        })
        assert response.status_code == 202, response.text
        chat_id = response.json()["chat"]["id"]
        user_message = response.json()["messages"][0]
        assert len(user_message["attachments"]) == 1
        attachment = client.get(user_message["attachments"][0]["url"])
        assert attachment.status_code == 200
        assert attachment.content == image
        assistant_attachment = response.json()["messages"][1]["attachments"][0]
        assert assistant_attachment["name"] == "generated.png"
        generated_response = client.get(assistant_attachment["url"])
        assert generated_response.status_code == 200
        assert generated_response.content == image
        model_messages = generate.await_args.kwargs["messages"]
        assert any(
            content.type == "data"
            for message in model_messages
            for content in message.contents
        )
        assert client.get(f"/api/chats/{chat_id}").status_code == 200


def test_chat_audio_transcription_uses_the_selected_model():
    audio = b"sample audio"
    with TestClient(app) as client, patch(
        "app.main.list_runtime_models",
        new=AsyncMock(return_value=[{"name": "speech-model", "provider": "copilot"}]),
    ), patch(
        "app.main.generate_chat_response",
        new=AsyncMock(return_value=("Turn left at the next street.", [])),
    ) as generate:
        response = client.post("/api/chats/transcribe", json={
            "model_name": "speech-model",
            "attachments": [{
                "name": "voice.webm",
                "media_type": "audio/webm",
                "data": base64.b64encode(audio).decode("ascii"),
            }],
        })
    assert response.status_code == 200, response.text
    assert response.json()["transcript"] == "Turn left at the next street."
    request_message = generate.await_args.kwargs["messages"][0]
    assert request_message.contents[0].text == (
        "Transcribe the attached audio accurately. Return only the spoken words."
    )
    assert request_message.contents[1].type == "data"


def test_base_agent_is_the_generic_chat_agent():
    with TestClient(app) as client, patch(
        "app.main.list_runtime_models",
        new=AsyncMock(return_value=[{"name": "auto", "provider": "copilot"}]),
    ):
        response = client.get("/api/chats/options")

    assert response.status_code == 200
    base = next(agent for agent in response.json()["agents"] if agent["id"] == "base")
    assert base["name"] == "AutoDev Base Agent"
    assert base["skills"] == []


def test_chat_rejects_unscoped_paths_unknown_projects_and_approval_bypasses():
    with TestClient(app) as client:
        base = {
            "message": "Test safe chat input",
            "agent_ids": ["did:local:developer"],
        }
        assert client.post(
            "/api/chats", json={**base, "repository_path": "/etc"}
        ).status_code == 422
        assert client.post(
            "/api/chats", json={**base, "project_id": 987654321}
        ).status_code == 404
        assert client.post(
            "/api/chats", json={**base, "approval_strategy": "always_allow"}
        ).status_code == 422
        assert client.post(
            "/api/chats", json={**base, "title": "This title is thirty characters"}
        ).status_code == 422
