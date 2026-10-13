import json

from agent_framework import FunctionInvocationContext, tool

from .tool_runtime import ToolRuntime


def runtime_from_context(ctx: FunctionInvocationContext) -> ToolRuntime:
    runtime = ctx.kwargs.get("workbench_runtime")
    if not isinstance(runtime, ToolRuntime):
        raise TypeError("Workbench tool runtime was not provided")
    return runtime


@tool(approval_mode="never_require")
async def list_files(
    path: str = ".", pattern: str = "*", offset: int = 0, limit: int = 200,
    *, ctx: FunctionInvocationContext,
) -> str:
    """List a bounded, sorted page of repository files."""
    return json.dumps(await runtime_from_context(ctx).execute("list_files", {
        "path": path, "pattern": pattern, "offset": offset, "limit": limit,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def search_text(
    query: str, path: str = ".", pattern: str = "*", max_matches: int = 50,
    *, ctx: FunctionInvocationContext,
) -> str:
    """Search a repository file or directory literally; max_matches is clamped to 1..200."""
    return json.dumps(await runtime_from_context(ctx).execute("search_text", {
        "query": query, "path": path, "pattern": pattern, "max_matches": max_matches,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def read_file(
    path: str, offset: int = 0, limit: int = 6000, *, ctx: FunctionInvocationContext,
) -> str:
    """Read a bounded UTF-8 text chunk; use next_offset to continue large files."""
    return json.dumps(await runtime_from_context(ctx).execute("read_file", {
        "path": path, "offset": offset, "limit": limit,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def write_file(path: str, content: str, *, ctx: FunctionInvocationContext) -> str:
    """Create or replace a UTF-8 text file in the repository."""
    return json.dumps(await runtime_from_context(ctx).execute("write_file", {
        "path": path, "content": content,
    }), ensure_ascii=False)


@tool(approval_mode="never_require")
async def delete_file(path: str, *, ctx: FunctionInvocationContext) -> str:
    """Delete one repository file."""
    return json.dumps(
        await runtime_from_context(ctx).execute("delete_file", {"path": path}),
        ensure_ascii=False,
    )


@tool(approval_mode="never_require")
async def run_command(arguments: list[str], *, ctx: FunctionInvocationContext) -> str:
    """Run an argument-vector test, build, dependency, or read-only Git command; no shell."""
    return json.dumps(
        await runtime_from_context(ctx).execute("run_command", {"arguments": arguments}),
        ensure_ascii=False,
    )


WORKBENCH_TOOLS = [
    list_files, search_text, read_file, write_file, delete_file, run_command,
]
