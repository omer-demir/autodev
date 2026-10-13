from pathlib import Path
from typing import Any

EXCLUDED_PARTS = {".git", "node_modules", ".venv", "dist", "build"}


def safe_path(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError("Path escapes the repository workspace")
    if ".git" in candidate.relative_to(workspace).parts:
        raise ValueError("Direct access to .git is not allowed")
    return candidate


def read_file_chunk(
    path: Path, relative: str, offset: int = 0, limit: int = 6000
) -> dict[str, Any]:
    if offset < 0:
        raise ValueError("File offset must be non-negative")
    if limit < 1 or limit > 24000:
        raise ValueError(
            "File read limit must be between 1 and 24000 characters")
    content = path.read_text(encoding="utf-8")
    chunk = content[offset:offset + limit]
    next_offset = offset + len(chunk)
    return {
        "path": relative,
        "content": chunk,
        "offset": offset,
        "next_offset": next_offset if next_offset < len(content) else None,
        "total_chars": len(content),
        "truncated": next_offset < len(content),
    }


def looks_taskless(content: str) -> bool:
    normalized = " ".join(content.casefold().split())
    return any(phrase in normalized for phrase in (
        "please provide the task",
        "provide the task you would like",
        "what task would you like",
        "what would you like me to do",
    ))


def repository_files(root: Path, pattern: str = "*") -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if pattern != "*" and not relative.match(pattern):
            continue
        files.append(path)
        if len(files) >= 10000:
            break
    return sorted(files, key=lambda item: str(item.relative_to(root)))


def search_repository_text(
    workspace: Path,
    root: Path,
    query: str,
    pattern: str = "*",
    max_matches: int = 50,
) -> dict[str, Any]:
    if not query:
        raise ValueError("Search query must not be empty")
    max_matches = min(max(max_matches, 1), 200)
    needle = query.casefold()
    matches: list[dict[str, Any]] = []
    scanned = 0
    files = [root] if root.is_file() else repository_files(root, pattern)
    for path in files:
        if path.stat().st_size > 1_000_000:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for line_number, line in enumerate(lines, 1):
            if needle in line.casefold():
                matches.append({
                    "path": str(path.relative_to(workspace)),
                    "line": line_number,
                    "text": line[:500],
                })
                if len(matches) >= max_matches:
                    return {"matches": matches, "truncated": True, "files_scanned": scanned}
    return {"matches": matches, "truncated": False, "files_scanned": scanned}
