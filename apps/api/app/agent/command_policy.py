import shlex
from pathlib import Path
from typing import Any

from ..runtime_supervision import ActionSpec


def classify(arguments: list[str]) -> str | None:
    if not arguments:
        return None
    executable = Path(arguments[0]).name
    subcommand = arguments[1] if len(arguments) > 1 else ""
    if executable == "git" and subcommand in {"status", "diff", "log", "show"}:
        return f"git.{subcommand if subcommand in {'status', 'diff'} else 'diff'}"
    if (
        executable == "pytest"
        or arguments[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
        or (executable == "go" and subcommand == "test")
        or (executable == "cargo" and subcommand == "test")
        or (executable == "dotnet" and subcommand == "test")
        or (executable in {"mvn", "mvnw", "gradle", "gradlew"} and "test" in arguments[1:])
        or arguments[:2] in (["npm", "test"], ["pnpm", "test"], ["yarn", "test"])
        or (arguments[:2] == ["bundle", "exec"] and len(arguments) > 2
            and arguments[2] in {"rspec", "rake"})
    ):
        return "test.run"
    if (
        (executable in {"npm", "pnpm", "yarn", "pip", "pip3", "poetry", "uv"}
         and subcommand in {"install", "ci", "add", "sync", "update"})
        or (executable in {"python", "python3"} and arguments[1:3] == ["-m", "pip"]
            and len(arguments) > 3 and arguments[3] == "install")
        or (executable == "go" and arguments[1:3] in (["mod", "download"], ["mod", "tidy"]))
        or (executable == "go" and subcommand == "get")
        or (executable == "cargo" and subcommand in {"fetch", "update", "add"})
        or (executable == "bundle" and subcommand == "install")
        or (executable == "composer" and subcommand in {"install", "update"})
        or (executable == "dotnet" and subcommand in {"restore", "add"})
        or (executable in {"mvn", "mvnw"} and "dependency:go-offline" in arguments[1:])
    ):
        return "dependency.install"
    if executable in {
        "npm", "pnpm", "yarn", "make", "go", "cargo", "python", "python3",
        "dotnet", "mvn", "mvnw", "gradle", "gradlew", "bundle", "composer",
    }:
        return "build.run"
    return None


def supervised_action(capability: str, arguments: dict[str, Any]) -> ActionSpec:
    read_only = capability in {
        "repository.read", "filesystem.read", "git.status", "git.diff", "security.scan",
    }
    irreversible = capability in {
        "git.push", "pull_request.create", "production.deploy",
        "deployment.execute", "infrastructure.delete",
    }
    is_admin = capability in {
        "governance.configure", "runtime_supervision.configure",
    }
    command_arguments = arguments.get("arguments")
    command = (
        shlex.join(str(item) for item in command_arguments)
        if isinstance(command_arguments, list)
        else None
    )
    return ActionSpec(
        capability=capability,
        read_only=read_only,
        reversible=not irreversible,
        is_admin=is_admin,
        command=command,
    )
