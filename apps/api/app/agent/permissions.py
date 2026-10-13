from typing import Any

from copilot.rpc import PermissionDecisionApproveOnce, PermissionDecisionUserNotAvailable
from copilot.session_events import PermissionRequestCustomTool

_WORKBENCH_TOOL_NAMES = {
    "list_files", "search_text", "read_file", "write_file", "delete_file", "run_command",
}


def copilot_permission_handler(request: Any, _context: Any) -> Any:
    """Permit the SDK to dispatch Workbench tools to our governance boundary."""
    del _context
    if (
        isinstance(request, PermissionRequestCustomTool)
        and request.tool_name in _WORKBENCH_TOOL_NAMES
    ):
        return PermissionDecisionApproveOnce()
    return PermissionDecisionUserNotAvailable()
