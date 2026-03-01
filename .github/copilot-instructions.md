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

## Polyrepo coordination (mandatory)

- This repository is an independent SAGE sub-repository and is developed/released independently.
- Do not assume sibling source directories exist locally in `intellistream/SAGE`.
- For cross-repo rollout, publish this repo/package first, then bump the version pin in `SAGE/packages/sage/pyproject.toml` when applicable.
- Do not add local editable installs of other SAGE sub-packages in setup scripts or docs.

## 🚫 NEVER_CREATE_DOT_VENV_MANDATORY

- 永远不要创建 `.venv` 或 `venv`（无任何例外）。
- NEVER create `.venv`/`venv` in this repository under any circumstance.
- 必须复用当前已配置的非-venv Python 环境（如现有 conda 环境）。
- If any script/task suggests creating a virtualenv, skip that step and continue with the existing environment.
