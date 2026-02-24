# SAGE Studio Copilot Instructions

## Scope
- `isage-studio`: React+TypeScript frontend plus FastAPI backend for visual SAGE pipeline workflows.
- Layer L6 application; integrates with SAGE core and related packages.

## Critical rules
- Keep startup/runtime guidance aligned with Flownet direction; do not add new `ray` dependencies.
- Use existing environment; do not create new local venvs in this repo.
- Preserve env-driven port model (`STUDIO_FRONTEND_PORT`, `STUDIO_BACKEND_PORT`, `SAGE_GATEWAY_PORT`, etc.).
- Avoid backward-compatibility shims/fallback imports; fix call sites directly.
- Keep CLI/plugin behavior stable (`sage studio start|stop|status|logs`).

## Workflow
1. Make targeted frontend/backend changes in existing architecture.
2. Keep imports and dependency boundaries consistent with `isage-agentic`/`isage-sias` integration.
3. Run relevant tests/lint and verify startup path when behavior changes.

## Key paths
- `src/sage/studio/cli.py`, `chat_manager.py`, `config/backend/api.py`, `frontend/src/`.
