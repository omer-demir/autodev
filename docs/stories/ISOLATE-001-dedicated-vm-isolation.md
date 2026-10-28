---
title: "ISOLATE-001: Dedicated VM without personal-host mounts"
description: Proposed opt-in Linux VM environment that runs Docker using VM-local files and credentials.
---

Status: Proposed  
Priority: P1  
Estimate: 8 points

## User story

As a developer, I want to run the entire AutoDev environment in a dedicated Linux
VM without mounting folders from my personal machine so that the control plane
and Docker tasks do not receive filesystem access to my personal files.

## Context

The immediate local-development choice remains sharing only the project's task
workspace directory for its bind mount, not expanding Docker Desktop sharing to
the whole home directory or filesystem. This is not equivalent to isolating the
entire development environment: the dev container also has checkout access,
currently mounts a host SSH directory, and uses Docker-outside-of-Docker.

For this story, the personal host is the developer's Mac or other physical
machine. The Docker host is the Linux VM. Clone the project into the VM's own
disk and install Docker Engine and Compose there. Bind mounts from that VM disk
into containers remain allowed; personal-host shared folders do not.

Docker containers share the VM's Linux kernel. This does not require nested
virtualization or Docker-in-Docker. An optional dev container can use
Docker-outside-of-Docker against the VM's daemon, with task containers running
alongside it.

## Scope

* Provide an opt-in, reproducible Linux VM setup with shared folders disabled.
* Keep the checkout, task workspaces, Docker storage, and application data on VM-local disk.
* Connect with VS Code Remote SSH and, optionally, reopen the VM-local checkout in a dev container.
* Use only the VM's Docker daemon; never forward the personal-host Docker socket.
* Remove personal-host SSH-directory mounts and disable SSH agent forwarding for this mode.
* Provision explicitly scoped application credentials inside the VM.
* Preserve the existing local development mode without changing its defaults.

## Non-goals

* No claim that a VM eliminates hypervisor vulnerabilities or network access to the personal host.
* No per-task VM, replacement sandbox provider, or removal of existing task-container restrictions.
* No automatic import of personal files, SSH keys, Docker contexts, or credentials.
* No requirement to replace VM-local bind mounts with Docker named volumes.

## Implementation tasks

1. Select and document a supported VM manager and Linux image, including CPU architecture, resource requirements, and shared-folder settings.
2. Add reproducible provisioning for Docker Engine, Compose, development dependencies, and a VM-local checkout.
3. Add a VM-specific dev-container configuration without personal-host mounts or agent forwarding. Resolve `WORKBENCH_DOCKER_WORKSPACE_HOST` to the workspace path on the VM's filesystem, not the dev container's internal path.
4. Add preflight checks for the expected Docker endpoint, VM-local mount sources, required tools, and forbidden shares. Fail with actionable diagnostics rather than falling back to the personal-host daemon.
5. Document scoped credential provisioning, VS Code access, and explicit source import/export through Git or user-initiated transfer.
6. Bind exposed services to intended interfaces and document SSH tunnels, guest firewall rules, and host/LAN access policy. Run Ollama inside the VM by default; access to a personal-host model service must be explicit.
7. Document startup, shutdown, upgrades, backup, and deletion. Treat VM disks and snapshots as sensitive because they can contain source and credentials.
8. Add end-to-end smoke checks and update setup and threat-model documentation only after verification.

## Acceptance criteria

1. A clean VM starts the development environment and executes a Docker-backed task without granting Docker Desktop any new personal-host file shares.
2. VM configuration and guest mount inventory show no personal-host shared filesystem. Docker bind sources resolve to VM-local storage.
3. Docker endpoint inspection confirms the control plane and optional dev container use only the VM's daemon. Task sandboxes receive no Docker socket.
4. No personal-host SSH directory or forwarded SSH agent is available inside the VM or its containers. Authentication uses explicitly provisioned credentials.
5. A task edits only its isolated task clone. VS Code can open the result remotely, and workspace and database state persist across a VM restart.
6. Existing task mount containment, network restrictions, resource limits, and credential isolation remain enforced.
7. Web/API access works through documented tunnels or explicitly allowed interfaces. Unneeded service ports are not exposed to the LAN.
8. A misconfigured daemon endpoint or forbidden shared folder blocks isolated-mode startup with an actionable error, not a success-shaped fallback.
9. The existing project-scoped local workflow remains usable and is clearly distinguished from the opt-in VM mode.

## Verification and evidence

* Capture redacted VM share configuration, guest mount inventory, Docker endpoint, and container mount manifests.
* Use disposable synthetic files to verify task-write containment without reading personal files.
* Record application health, a completed Docker-backed task, remote editor access, restart persistence, and cleanup results.
* Test startup rejection for forbidden shares and an unexpected Docker endpoint.
* Verify service bindings and guest firewall policy with controlled endpoints.

## Dependencies and risks

* No prerequisite backlog story; reuse the existing filesystem and credential assurance scenarios where available.
* Docker socket access still grants substantial control over the VM. Keep the VM dedicated to AutoDev and avoid unrelated sensitive workloads.
* VM networking can reach host or LAN services unless restricted separately; absence of file shares is not network isolation.
* VM-manager default shares, SSH forwarding, architecture-specific images, and remote editor path mapping require explicit verification.
* Priority and estimate are provisional and should be refined when selecting the supported VM manager.

## References

* [Local setup](../local-setup.md)
* [Dev container configuration](../../.devcontainer/devcontainer.json)
* [Compose services](../../compose.yaml)
* [Threat model](../threat-model.md)
* [Filesystem and mount boundary assurance](CHAOS-003-filesystem-and-mount-boundaries.md)
* [Credential isolation assurance](CHAOS-002-credential-isolation.md)
* [Editors and model providers](../editors-and-model-providers.md)
