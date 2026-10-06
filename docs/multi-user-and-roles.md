# Multi-user access and roles

## Current boundary

The Workbench currently runs as a trusted, single-user local control plane. GitHub repository OAuth connects a source-control identity; it is not a Workbench login. Projects, tasks, approvals, registry definitions, terminals, and evidence are therefore not isolated by user or organization yet. Do not expose the current API directly to multiple untrusted users.

## Recommended identity model

Use an OIDC provider (GitHub, Microsoft Entra ID, or another organization identity provider) and an API-managed session:

1. Complete OIDC Authorization Code + PKCE in the API.
2. Store only an opaque session ID in a `Secure`, `HttpOnly`, `SameSite=Lax` cookie.
3. Model `Organization`, `User`, `Membership`, `Role`, `RolePermission`, and `Session` records.
4. Add `organization_id` and `created_by` to projects, tasks, datasets, evaluation runs, and registry definitions.
5. Scope every query, mutation, WebSocket subscription, sandbox operation, and evidence download to the current organization.
6. Record `actor_id`, delegated role, decision, reason, and resource scope on approvals and audit events.
7. Use a GitHub App per organization for short-lived repository credentials. Do not share one in-memory OAuth token among users.

For a small trusted team, one organization with several memberships is sufficient. For hosted use, enforce organization scope in the database access layer rather than relying on UI filtering.

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

1. Add OIDC sessions and organization-scoped models.
2. Migrate existing records into a default local organization and owner.
3. Add centralized `authorize(actor, action, resource, context)` enforcement to every API and WebSocket route.
4. Add role administration and project membership UI.
5. Add path/task/environment conditions to governance.
6. Add actor-aware audit events and separation-of-duties tests.
7. Only then expose the service beyond localhost.
