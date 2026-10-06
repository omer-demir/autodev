# Threat model

Repository content and model output are untrusted. The model is never an authorization boundary.

Controls represented in the prototype include semantic capabilities, default deny, scoped approvals, separate agent identity, no host credential mounts, explicit sandbox terminal labeling, kill switches, deterministic scanner evidence, and durable events. Production execution must additionally enforce container resource limits, restricted egress, trusted MCP servers, short-lived credentials, and independently verified policy enforcement.

The sandbox receives one read-write host bind mount: the isolated task clone under `.workspaces/TASK-NNN/repo`, exposed as `/workspace/project`. This write access is required to produce inspectable changes. Mount paths are rejected unless they resolve under the configured workspace root. The original repository, SSH keys, environment files, and Docker socket are not mounted into the sandbox. The container also runs without networking or Linux capabilities, with `no-new-privileges`, resource limits, and the control-plane user's numeric UID/GID.

The API control plane is a separate and more privileged boundary. In container mode it uses the host Docker socket to create and remove sandboxes; compromise of the API process may therefore imply control of the Docker host. Do not expose this prototype API to untrusted networks. Production deployments should replace direct socket access with a narrowly scoped sandbox service and require authentication and authorization on the control plane.

GitHub OAuth uses a ten-minute, single-use state value bound to an HttpOnly SameSite cookie. OAuth tokens are process-local and are used only by the control plane for GitHub API calls and authenticated clones. This prototype has one shared local-user credential slot; a hosted multi-user deployment must use authenticated per-user server sessions, encrypted credential storage, HTTPS secure cookies, and preferably GitHub App installation tokens.
