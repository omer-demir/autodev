import json
import os
import subprocess
import webbrowser

import httpx
import typer


app = typer.Typer(help="Control the Agentic SDLC Workbench.",
                  no_args_is_help=True)
sandbox_app = typer.Typer(help="Manage isolated sandboxes.")
session_app = typer.Typer(help="Inspect and continue durable agent sessions.")
publication_app = typer.Typer(help="Request and inspect governed publication.")
gateway_app = typer.Typer(help="Inspect external MCP gateway transports.")
app.add_typer(sandbox_app, name="sandbox")
app.add_typer(session_app, name="sessions")
app.add_typer(publication_app, name="publication")
app.add_typer(gateway_app, name="gateway")
API = os.getenv("WORKBENCH_API_URL", "http://localhost:8000")


def request(method: str, path: str, body: dict | None = None):
    headers = {}
    if token := os.getenv("WORKBENCH_ACCESS_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    if organization_id := os.getenv("WORKBENCH_ORGANIZATION_ID"):
        headers["X-Organization-Id"] = organization_id
    try:
        response = httpx.request(
            method,
            f"{API}{path}",
            json=body,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        typer.secho(f"API error: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


@app.command()
def start(open_browser: bool = typer.Option(True, "--open/--no-open")):
    """Start the API and web UI."""
    typer.echo("Starting Agentic SDLC Workbench...")
    if open_browser:
        webbrowser.open("http://localhost:3000")
    raise typer.Exit(subprocess.call(["npm", "run", "dev"]))


@app.command()
def doctor():
    """Check local dependencies and adapters."""
    result = request("GET", "/api/doctor")
    typer.echo(f"Execution mode: {result['mode']}")
    for check in result["checks"]:
        typer.echo(
            f"[{'OK' if check['available'] else '--':2}] {check['name']}")


@app.command()
def runtime():
    """Show model and sandbox provider status."""
    result = request("GET", "/api/runtime")
    typer.echo(
        f"model={result['active_model_provider']} "
        f"sandbox={result['sandbox_provider']} "
        f"ready={result['sandbox_available']}"
    )
    if result.get("model_error"):
        typer.echo(f"model error: {result['model_error']}")


@app.command()
def run(task_id: str):
    """Run a task by ID."""
    result = request("POST", f"/api/tasks/{task_id}/run")
    typer.echo(f"Started {result['task_id']}")


@app.command()
def status(task_id: str):
    """Show task status."""
    task = request("GET", f"/api/tasks/{task_id}")["task"]
    typer.echo(
        f"{task['id']}  {task['status']}  {task['progress']}%  {task['title']}")


@app.command()
def logs(task_id: str):
    """Print a task timeline."""
    for event in request("GET", f"/api/tasks/{task_id}")["events"]:
        typer.echo(
            f"{event['created_at']}  {event['type']:<28} {event['title']}")


@app.command()
def approve(approval_id: str):
    """Approve one scoped action."""
    result = request("POST", f"/api/approvals/{approval_id}/approve")
    typer.echo(f"Approved {result['action']} for {result['task_id']}")


@app.command()
def deny(approval_id: str):
    """Deny one scoped action."""
    result = request("POST", f"/api/approvals/{approval_id}/deny")
    typer.echo(f"Denied {result['action']} for {result['task_id']}")


@app.command()
def kill(task_id: str):
    """Terminate an active agent session."""
    request("POST", f"/api/tasks/{task_id}/cancel")
    typer.echo(f"Terminated agent for {task_id}; evidence preserved")


@app.command()
def evidence(task_id: str):
    """Print the evidence bundle."""
    typer.echo(json.dumps(
        request("GET", f"/api/tasks/{task_id}/evidence"), indent=2))


@sandbox_app.command("kill")
def sandbox_kill(session_id: str):
    request("POST", f"/api/sandboxes/{session_id}/kill")
    typer.echo(f"Killed {session_id}; evidence preserved")


@session_app.command("list")
def session_list():
    """List durable sessions in the active organization."""
    for value in request("GET", "/api/sessions"):
        persisted = "persisted" if value["workspace_persisted"] else "no-workspace"
        typer.echo(
            f"{value['task_id']:<20} {value['status']:<18} {persisted:<12} {value['title']}"
        )


@session_app.command("show")
def session_show(task_id: str):
    """Print one session's messages, events, and outputs."""
    typer.echo(json.dumps(
        request("GET", f"/api/sessions/{task_id}"), indent=2))


@session_app.command("continue")
def session_continue(
    task_id: str,
    content: str = typer.Argument(..., help="Follow-up instruction."),
    agent_id: str | None = typer.Option(None, "--agent"),
):
    """Continue a terminal session from its persisted worktree."""
    result = request(
        "POST",
        f"/api/sessions/{task_id}/messages",
        {"content": content, "agent_id": agent_id},
    )
    typer.echo(f"Started {result['session_id']} with {result['agent_id']}")


@publication_app.command("request")
def publication_request(
    task_id: str,
    branch: str = typer.Option(..., "--branch"),
    pull_request: bool = typer.Option(False, "--pull-request"),
):
    """Request scoped approval to push a completed task."""
    result = request(
        "POST",
        f"/api/tasks/{task_id}/publish",
        {"branch": branch, "create_pull_request": pull_request},
    )
    typer.echo(
        f"Approval {result['approval_id']} required for {', '.join(result['actions'])}"
    )


@publication_app.command("pending")
def publication_pending():
    """List pending publication approvals."""
    approvals = request("GET", "/api/approvals")
    for value in approvals:
        if value["status"] == "PENDING" and value["action"] == "repository.publish":
            typer.echo(
                f"{value['id']:<28} {value['task_id']:<18} {value['scope'].get('branch', '')}"
            )


@gateway_app.command("status")
def gateway_status():
    """Show authenticated MCP transport endpoints and tools."""
    result = request("GET", "/api/gateway")
    typer.echo(f"Streamable HTTP: {result['streamable_http']}")
    typer.echo(f"SSE:             {result['sse']}")
    typer.echo(f"Messages:        {result['messages']}")
    typer.echo(f"Tools:           {', '.join(result['tools'])}")


if __name__ == "__main__":
    app()
