---
name: sage-studio
description: Agent for Studio frontend/backend/CLI changes with stable runtime contracts.
argument-hint: Include frontend/backend path, expected UX/API outcome, and validation scope.
tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo', 'vscode.mermaid-chat-features/renderMermaidDiagram', 'github.vscode-pull-request-github/issue_fetch', 'github.vscode-pull-request-github/suggest-fix', 'github.vscode-pull-request-github/searchSyntax', 'github.vscode-pull-request-github/doSearch', 'github.vscode-pull-request-github/renderIssues', 'github.vscode-pull-request-github/activePullRequest', 'github.vscode-pull-request-github/openPullRequest', 'ms-azuretools.vscode-containers/containerToolsConfig', 'ms-python.python/getPythonEnvironmentInfo', 'ms-python.python/getPythonExecutableCommand', 'ms-python.python/installPythonPackage', 'ms-python.python/configurePythonEnvironment', 'ms-toolsai.jupyter/configureNotebook', 'ms-toolsai.jupyter/listNotebookPackages', 'ms-toolsai.jupyter/installNotebookPackages', 'ms-vscode.cpp-devtools/Build_CMakeTools', 'ms-vscode.cpp-devtools/RunCtest_CMakeTools', 'ms-vscode.cpp-devtools/ListBuildTargets_CMakeTools', 'ms-vscode.cpp-devtools/ListTests_CMakeTools']
---

# SAGE Studio Agent

## Scope
- FastAPI backend + React/TS frontend + Studio CLI integration.

## Rules
- Keep env-driven ports and startup behavior intact.
- No new `ray` dependencies; align with Flownet ecosystem.
- Do not create new local virtual environments (`venv`/`.venv`); use the existing configured Python environment.
- Avoid compatibility shims; update call sites directly.
- Preserve `sage studio start|stop|status|logs` user behavior.

## Workflow
1. Make targeted backend/frontend changes.
2. Validate relevant tests/lint/build.
3. Confirm startup path if runtime behavior changed.
