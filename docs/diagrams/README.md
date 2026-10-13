# Technical drawings

The files in this directory are editable Draw.io sources. Open them in [diagrams.net](https://app.diagrams.net/), the Draw.io desktop application, or the VS Code Draw.io extension.

For implementation flows with inline hand-drawn Mermaid sketches, see the [architecture design deep dives](../design/README.md). The two catalogs serve different needs: Draw.io captures formal deployment and trust boundaries, while the deep dives keep behavior sketches beside the technical explanation.

| Drawing                                             | View                                                          | Intended use                        |
| --------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------- |
| [General architecture](general-architecture.drawio) | Product context and trust boundaries                          | Executive and architecture overview |
| [System design](system-design.drawio)               | Internal control-plane components and task flow               | Engineering design reviews          |
| [Cloud architecture](cloud-architecture.drawio)     | Azure dynamic-session deployment and operational dependencies | Cloud/security review               |
| [Local architecture](local-architecture.drawio)     | Native/Compose topology, persistence, and sandbox lifecycle   | Developer setup and troubleshooting |
| [Adapters](adapters.drawio)                         | Provider contracts and current implementations                | Extension and integration design    |

## Notation

- Blue: user-facing or integration surface.
- Green: Autodev control-plane component.
- Yellow: deterministic governance, workflow, or approval boundary.
- Purple: external provider or service.
- Gray: durable data or operational evidence.
- Red: privileged or security-sensitive boundary.
- Dashed container: deployment or trust boundary.

The cloud drawing is explicit about provisioning scope: the supplied Bicep provisions the Azure Container Apps dynamic session pool, Log Analytics, diagnostics, and capacity alert. Hosting for the Web/API control plane is operator-owned and is shown as a reference boundary, not as infrastructure currently created by the template.
