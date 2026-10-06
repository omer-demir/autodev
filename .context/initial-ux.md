┌──────────────────────────────────────────────────────────────────┐
│ Agentic SDLC Workbench                         ● Sandbox: Ready │
├───────────────┬──────────────────────────────────────────────────┤
│               │                                                  │
│ PROJECTS      │  TASK #142 — Add authentication                 │
│               │                                                  │
│ ● my-project  │  ┌────────────────────────────────────────────┐ │
│               │  │ Agent                                      │ │
│ TASKS         │  │                                             │ │
│               │  │ I inspected the repository and created a   │ │
│ ● #142        │  │ plan. I need approval before modifying     │ │
│   #141        │  │ package dependencies.                       │ │
│               │  └────────────────────────────────────────────┘ │
│ AGENTS        │                                                  │
│               │  Plan → Code → Test → Security → Review → PR   │
│ ● Developer   │  ●────●────●────●────●────○                    │
│ ● Reviewer    │                                                  │
│ ● Security    │  ┌───────────────┐ ┌─────────────────────────┐ │
│               │  │ Changes       │ │ Terminal                │ │
│ GOVERNANCE    │  │               │ │                         │ │
│               │  │ + auth.py     │ │ $ pytest                │ │
│ ● Policies    │  │ + tests/...   │ │ 28 passed               │ │
│ ● Approvals   │  │               │ │                         │ │
│ ● Audit       │  └───────────────┘ └─────────────────────────┘ │
│               │                                                  │
│ SECURITY      │  Security: ✓  Governance: ✓  Tests: ✓           │
│               │                                                  │
│ ● Findings    │                 [ Review Changes ]              │
│ ● Evaluations │                                                  │
└───────────────┴──────────────────────────────────────────────────┘