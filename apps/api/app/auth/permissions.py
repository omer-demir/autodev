ROLE_PERMISSIONS = {
    "viewer": {"read"},
    "developer": {
        "read",
        "project.create",
        "project.delete",
        "task.create",
        "task.operate",
        "sandbox.operate",
    },
    "reviewer": {"read", "approval.decide", "evaluation.manage"},
    "admin": {"*"},
}

ROLE_PRIORITY = ("admin", "reviewer", "developer", "viewer")
