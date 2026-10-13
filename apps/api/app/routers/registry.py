import asyncio

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..agent_identity import AgentIdentityError, agent_identity_service
from ..auth import Principal, require_permission
from ..capabilities import SUPPORTED_CAPABILITIES, SUPPORTED_CAPABILITY_RESOLVERS
from ..database import get_session
from ..integrations import import_external_definition
from ..registry import (
    RegistryError,
    delete_definition,
    get_definition,
    list_definitions,
    save_definition,
)
from ..registry_checks import check_skill_with_waza
from ..schemas import IntegrationImportRequest, RegistryDefinitionUpdate


router = APIRouter(tags=["registry"])


@router.get("/api/registry/{kind}")
def registry_list(
    kind: str, principal: Principal = Depends(require_permission("read"))
) -> list[dict]:
    del principal
    try:
        return list_definitions(kind)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/runtime-capabilities")
def runtime_capabilities(
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    del principal
    return {
        "capabilities": sorted(SUPPORTED_CAPABILITIES),
        "resolvers": sorted(SUPPORTED_CAPABILITY_RESOLVERS),
    }


@router.post("/api/integrations/import", status_code=201)
async def import_integration(
    payload: IntegrationImportRequest,
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    del principal
    try:
        return await import_external_definition(
            payload.url, kind=payload.kind, identifier=payload.identifier
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            502, "Integration source could not be fetched"
        ) from exc


@router.get("/api/marketplace/agents")
def marketplace_agents(
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("read")),
) -> list[dict]:
    return agent_identity_service.list_entries(
        session, principal.organization_id
    )


@router.post("/api/marketplace/agents/{agent_id}/revoke")
def revoke_marketplace_agent(
    agent_id: str,
    session: Session = Depends(get_session),
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    try:
        record = agent_identity_service.revoke(
            session, agent_id, principal.organization_id
        )
    except AgentIdentityError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "agent_id": agent_id,
        "agent_did": record.did,
        "status": record.status,
    }


@router.get("/api/registry/{kind}/{identifier}")
def registry_get(
    kind: str,
    identifier: str,
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    del principal
    try:
        return get_definition(kind, identifier)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/registry/{kind}/{identifier}/check")
async def check_registry_definition(
    kind: str,
    identifier: str,
    principal: Principal = Depends(require_permission("read")),
) -> dict:
    del principal
    try:
        definition = get_definition(kind, identifier)
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc
    data = definition["data"]
    result = {
        "valid": True,
        "kind": kind,
        "id": identifier,
        "check": "native-schema",
        "detail": "Definition passes native static validation.",
    }
    if kind == "mcp":
        endpoint = str(data.get("endpoint") or "")
        if data.get("runtime") == "builtin" and endpoint.startswith("/"):
            result.update({
                "check": "builtin-route",
                "detail": f"Built-in MCP route {endpoint} is configured.",
            })
        elif (
            data.get("transport") in {"http", "sse"}
            and endpoint.startswith(("http://", "https://"))
        ):
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    response = await client.get(endpoint)
                result.update({
                    "check": "connection",
                    "status_code": response.status_code,
                    "detail": (
                        f"MCP endpoint responded with HTTP "
                        f"{response.status_code}."
                    ),
                })
            except httpx.HTTPError as exc:
                raise HTTPException(
                    422, f"MCP connection failed: {exc}"
                ) from exc
        else:
            raise HTTPException(
                422,
                "MCP connection checks require a built-in relative route "
                "or absolute HTTP endpoint",
            )
    elif kind == "skills":
        result.update(
            await asyncio.to_thread(check_skill_with_waza, identifier, data)
        )
    return result


@router.patch("/api/registry/workflows/{identifier}/stages/{stage_id}")
def assign_workflow_stage_agent(
    identifier: str,
    stage_id: str,
    payload: dict,
    principal: Principal = Depends(require_permission("registry.manage")),
):
    del principal
    agent_id = str(payload.get("agent_id") or "")
    try:
        get_definition("agents", agent_id)
        workflow = get_definition("workflows", identifier)
        stages = workflow["data"].get("stages") or []
        stage = next(
            (item for item in stages if str(item.get("id")) == stage_id),
            None,
        )
        if stage is None:
            raise RegistryError(f"Workflow stage not found: {stage_id}")
        stage["agent"] = f"did:local:{agent_id}"
        return save_definition(
            "workflows",
            identifier,
            yaml.safe_dump(workflow["data"], sort_keys=False),
        )
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/api/registry/{kind}/{identifier}")
def registry_put(
    kind: str,
    identifier: str,
    payload: RegistryDefinitionUpdate,
    principal: Principal = Depends(require_permission("registry.manage")),
) -> dict:
    del principal
    try:
        return save_definition(kind, identifier, payload.raw)
    except RegistryError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/api/registry/{kind}/{identifier}", status_code=204)
def registry_delete(
    kind: str,
    identifier: str,
    principal: Principal = Depends(require_permission("registry.manage")),
) -> None:
    del principal
    try:
        delete_definition(kind, identifier)
    except RegistryError as exc:
        raise HTTPException(404, str(exc)) from exc
