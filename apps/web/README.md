---
title: AutoDev web application
description: Develop, lint, and build the Next.js web application in AutoDev.
---

This package contains the AutoDev web interface. It uses Next.js 16, React 19,
TypeScript, Tailwind CSS, and ESLint.

## Development

From the repository root, start the API, worker, and web application together:

```bash
make dev
```

For frontend-only work, start the API separately, then run:

```bash
npm --workspace apps/web run dev
```

The web application is available at <http://localhost:3000>. Its `/api`
requests are proxied to the API configured by `WORKBENCH_API_URL`, which
defaults to <http://127.0.0.1:8000>.

## Validation

Run the package checks from the repository root:

```bash
npm --workspace apps/web run lint
npm --workspace apps/web run build
```

See the root [README](../../README.md) for environment setup and the
[developer guide](../../DEVELOPMENT.md) for the full local workflow.
