SUPPORTED_CAPABILITIES = frozenset({
    "repository.read",
    "repository.write",
    "repository.publish",
    "filesystem.read",
    "filesystem.write",
    "test.run",
    "build.run",
    "dependency.install",
    "security.scan",
    "git.status",
    "git.diff",
    "git.commit",
    "git.push",
    "pull_request.create",
    "production.deploy",
    "deployment.execute",
    "host.credentials.read",
    "infrastructure.delete",
    "governance.configure",
    "runtime_supervision.configure",
})

SUPPORTED_CAPABILITY_RESOLVERS = frozenset({"command-v1"})
