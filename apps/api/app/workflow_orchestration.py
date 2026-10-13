from collections.abc import Mapping
from typing import Any


class WorkflowOrchestrationError(ValueError):
    pass


WRITE_CAPABILITIES = {
    "repository.write",
    "dependency.install",
    "git.commit",
    "git.push",
    "production.deploy",
}


def workflow_owner_agent(
    workflow: Mapping[str, Any],
    agent_definitions: Mapping[str, Mapping[str, Any]],
    fallback_agent: str,
) -> str:
    candidates = [
        str(stage["agent"]) for stage in workflow.get("stages", [])
    ] or [str(workflow.get("default_agent") or fallback_agent)]
    return next(
        (
            agent_id for agent_id in candidates
            if "repository.write" in agent_definitions[agent_id].get(
                "capabilities", []
            )
        ),
        candidates[0],
    )


def stage_waves(workflow: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
    stages = [dict(stage) for stage in workflow.get("stages", [])]
    orchestration = workflow.get("orchestration", {})
    if orchestration.get("mode") == "sequential":
        return [[stage] for stage in stages]

    remaining = {str(stage["id"]): stage for stage in stages}
    completed: set[str] = set()
    waves: list[list[dict[str, Any]]] = []
    max_parallel = int(orchestration.get("max_parallel", 1))
    while remaining:
        ready = [
            stage for stage in stages
            if stage["id"] in remaining
            and set(stage.get("depends_on", [])).issubset(completed)
        ]
        if not ready:
            raise WorkflowOrchestrationError(
                "Workflow has unresolved or cyclic stage dependencies"
            )
        for offset in range(0, len(ready), max_parallel):
            wave = ready[offset:offset + max_parallel]
            waves.append(wave)
            for stage in wave:
                remaining.pop(str(stage["id"]))
                completed.add(str(stage["id"]))
    return waves


def assert_parallel_stages_are_read_only(
    waves: list[list[dict[str, Any]]],
    agent_definitions: Mapping[str, Mapping[str, Any]],
) -> None:
    for wave in waves:
        if len(wave) < 2:
            continue
        for stage in wave:
            agent_id = str(stage["agent"])
            capabilities = set(
                agent_definitions[agent_id].get("capabilities", []))
            unsafe = capabilities & WRITE_CAPABILITIES
            if unsafe:
                raise WorkflowOrchestrationError(
                    f"Parallel stage {stage['id']} uses write-capable agent {agent_id}: "
                    f"{', '.join(sorted(unsafe))}"
                )


def stage_artifact_inputs(
    stage: Mapping[str, Any], artifacts: Mapping[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    requested = {
        input_id for input_id in stage.get("inputs", [])
        if input_id not in {"request", "messages", "workspace"}
    }
    missing = requested - artifacts.keys()
    if missing:
        raise WorkflowOrchestrationError(
            f"Stage {stage['id']} is missing required artifacts: "
            f"{', '.join(sorted(missing))}"
        )
    return {
        input_id: artifacts[input_id]
        for input_id in requested
    }
