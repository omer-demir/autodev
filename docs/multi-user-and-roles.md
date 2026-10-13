# Multi-user access and roles

## Current boundary

The Workbench supports two authentication modes:

- `local` provisions a local administrator and organization for trusted workstation use.
- `oidc` provides authorization-code login with PKCE, validates issuer, audience, signature, nonce, and required JWT claims through configured JWKS, creates an opaque server-side session, resolves organization membership, and applies role permissions.

Projects, tasks, approvals, datasets, evaluation runs, agent identity records, marketplace entries, durable sessions, and their API queries carry organization scope. Approval records retain requester and approver identity. The built-in roles are viewer, developer, reviewer, and admin.

This is a foundation for multi-user operation, not yet a complete hostile-tenant boundary. Registry YAML and prompt assets remain deployment-wide files rather than organization-owned records, and deployment boundaries still require a dedicated production security review. Membership administration and core WebSocket/MCP role tests are implemented, while a generated authorization inventory covering every route and tool remains roadmap work.

## Implemented identity model

Use an OIDC provider such as Microsoft Entra ID or another organization identity provider. The current implementation:

1. Redirects browser users through authorization code with PKCE, state, and nonce validation, or accepts an OIDC bearer token for API/MCP clients.
2. Validates the ID or bearer token through configured issuer, audience, algorithms, and JWKS URL.
3. Models `Organization`, `User`, and `Membership`; roles map to centralized permission sets.
4. Auto-provisions an OIDC principal only when enabled and the claimed organization matches the requested organization.
5. Stores only a random opaque session value in an HttpOnly cookie; its SHA-256 digest and expiry are stored server-side.
6. Re-resolves membership and role on each request, including WebSocket and MCP authentication.
7. Lets administrators add, update, and remove organization memberships at `/admin`, while blocking self-removal and self-demotion.

For hosted use, keep `WORKBENCH_SESSION_COOKIE_SECURE=true`, configure the callback through the public HTTPS origin, complete a route-inventory authorization review, move deployment-wide registries into an organization-aware release model, and use per-organization GitHub App installation credentials.

## Separate human roles from agent capabilities

A human role answers **who may request or approve work**. An agent declaration answers **what the selected agent may execute**. Keep these independent.

An action should run only when all applicable checks allow it:

```text
human permission ∩ agent capability ∩ task/environment policy ∩ resource scope
```

Explicit deny wins. Approval-required actions also require an eligible approver who is not the requester when separation of duties applies.

Suggested human-role matrix:

| Permission                            | Architect |              DevOps | Tester |
| ------------------------------------- | --------: | ------------------: | -----: |
| Read projects and repositories        |     Allow |               Allow |  Allow |
| Create/steer design tasks             |     Allow |                Deny |   Deny |
| Generate or modify requirements/PRDs  |     Allow |                Deny |   Deny |
| Create/steer application coding tasks |     Allow |             Limited |   Deny |
| Modify infrastructure and CI/CD       |   Limited |               Allow |   Deny |
| Create test specifications/fixtures   |     Allow |               Allow |  Allow |
| Run tests and inspect evidence        |     Allow |               Allow |  Allow |
| Review/approve changes                |     Allow |               Allow |  Allow |
| Request deployment                    |      Deny |               Allow |   Deny |
| Execute deployment                    |      Deny | Allow with approval |   Deny |
| Manage users, roles, and policy       |      Deny |                Deny |   Deny |

Keep administration as a separate role. “Limited” must be expressed as resource conditions, such as allowed paths or task types, not as a broad repository write grant.

Example permission vocabulary:

- `requirements.write`, `design.write`
- `task.create`, `task.steer`, `task.cancel`
- `repository.read`, `application.write`, `infrastructure.write`, `test.write`
- `test.run`, `security.scan`
- `change.review`, `change.approve`
- `deployment.request`, `deployment.execute`
- `registry.manage`, `role.manage`

The current coding tool maps every file write to `repository.write`. Supporting the matrix above requires policy input to include the requested path and task type. For example, a tester can receive `test.write` only for `tests/**`, while DevOps can receive `infrastructure.write` only for `.github/**`, `deploy/**`, Terraform, Helm, and related files. Never infer permission only from a job title.

## Approval and deployment controls

Use scoped, single-use approvals containing the immutable diff or artifact digest, repository, environment, action, requester, and expiry. Recommended rules:

- The requester cannot approve their own production deployment.
- Tester approval can satisfy test/release evidence but cannot grant deployment capability.
- Architect approval can satisfy design review but cannot execute deployment.
- DevOps can request deployment; production execution requires a second authorized approver.
- Changing the commit or deployment artifact invalidates prior approval.

## Implementation order

1. **Implemented:** OIDC token validation, local bootstrap identity, organizations, memberships, role permissions, and organization-scoped primary records.
2. **Implemented:** requester/approver identity on scoped approvals and organization-aware task/evaluation/session operations.
3. **Implemented:** browser OIDC login, opaque expiring sessions, logout, role/membership administration, and core WebSocket/MCP authorization matrices.
4. **Next:** generate complete authorization inventory tests for every REST, WebSocket, MCP, sandbox, evidence, connector, and registry path; add session rotation and revocation operations.
5. **Next:** replace shared registry files and connector credentials with organization-owned, versioned resources and GitHub App installation tokens.
6. **Next:** add path/task/environment conditions, approval expiry, immutable artifact digests, and enforced separation of duties.
7. Complete a production threat review before exposing the service to mutually untrusted tenants.
