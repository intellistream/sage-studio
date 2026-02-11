# SAGE Studio Copilot Instructions

## 📋 Project Overview

**SAGE Studio** is a modern low-code web UI for visually developing and managing SAGE data pipelines.

| Property | Value |
|----------|-------|
| **Package Name** | `isage-studio` |
| **Tech Stack** | React 18 + TypeScript + FastAPI |
| **Architecture** | Frontend-Backend Separation |
| **Layer** | L6 (Top-level application) |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)               │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Flow Editor  │  │  Playground  │  │  Properties  │ │
│  │   (Canvas)    │  │  (Chat Test) │  │  (Config)    │ │
│  └───────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                         ⬇ HTTP/REST API
┌─────────────────────────────────────────────────────────┐
│               Backend (FastAPI - api.py)                 │
│  • Node Registry                                         │
│  • Pipeline Builder                                      │
│  • API Endpoints (flows, operators, execution)          │
└─────────────────────────────────────────────────────────┘
                         ⬇ Python API
┌─────────────────────────────────────────────────────────┐
│                  SAGE Core Engine                        │
│  • sage-kernel (Environment, DataStream API)            │
│  • sage-middleware (RAG Operators)                      │
│  • sage-libs (IO: FileSource, PrintSink...)             │
└─────────────────────────────────────────────────────────┘
```

## 🔗 Dependencies

### Core Dependencies

- **SAGE**: `isage>=0.2.0` - SAGE meta package
- **Agentic**: `isage-agentic>=0.1.0` - Agent framework (intent, workflow, planning)
- **SIAS**: `isage-sias>=0.1.0` - Sample importance-aware selection algorithms

### Agentic Module Details

Studio uses agentic modules for intent classification and workflow routing:

```python
from sage_libs.sage_agentic.intent import IntentClassifier, UserIntent, IntentResult
from sage_libs.sage_agentic.workflows.router import (
    WorkflowRouter, WorkflowDecision, WorkflowRequest, WorkflowRoute
)
```

**Note**: These modules are from the independent `isage-agentic` package, NOT from SAGE core.

## 📁 Workspace Structure

The Studio workspace includes multiple repositories:

```
workspace/
├── sage-studio/          # This repository (L6)
├── SAGE/                 # Core SAGE framework
├── sage-agentic/         # Agent framework (isage-agentic)
├── sage-sias/            # SIAS algorithms (isage-sias)
├── sagellm/              # LLM inference engine (isagellm)
├── neuromem/             # Memory management (isage-neuromem)
├── sageVDB/              # Vector database (isage-vdb)
├── sageData/             # Dataset management (isage-data)
└── SAGE-Pub/             # Public documentation
```

## 🚀 Installation

### Development Setup

```bash
# Method 1: Use quickstart script (RECOMMENDED)
cd sage-studio
./quickstart.sh

# Method 2: Manual install
pip install -e .
```

**Dependencies Installation**:
- `quickstart.sh` automatically detects development mode:
  - **Development Mode**: If local repos exist (`sage-agentic`, `sage-sias`, `SAGE`), uses `pip install -e` for local development
  - **Production Mode**: If no local repos found, installs from PyPI (`isage-agentic`, `isage-sias`)
- Dependencies are automatically installed based on environment detection
- If dependencies are missing in production, they should be installed via pip from PyPI

### Startup

```bash
# RECOMMENDED: Start Studio (frontend + backend)
sage studio start

# Advanced options
sage studio start --dev          # Development mode (default, Vite dev server)
sage studio start --prod         # Production mode (requires npm run build first)
sage studio start --port 5173    # Custom frontend port
sage studio status              # Check if Studio is running
sage studio stop                # Stop Studio
sage studio logs --follow       # View logs

# Or use the quickstart script for first-time setup
./quickstart.sh
```

**Note**: The `sage studio` CLI command is implemented via a plugin system. Studio registers itself to SAGE CLI through entry points when installed. See [src/sage/studio/cli.py](src/sage/studio/cli.py) for implementation.

### Startup Output Format

When `sage studio start` completes successfully, it displays a unified status summary:

```
======================================================================
🎉 Chat 模式就绪！
======================================================================
🎨 Studio 前端: http://0.0.0.0:${STUDIO_FRONTEND_PORT}
💬 打开顶部 Chat 标签即可体验

📡 运行中的服务：
   LLM 引擎       | 端口: ${SAGE_LLM_PORT}  | 日志: /home/user/.local/state/sage/logs/llm_engine.log
   Embedding 服务 | 端口: ${SAGE_EMBEDDING_PORT}  | 日志: /home/user/.local/state/sage/logs/embedding.log
   Gateway        | 端口: ${SAGE_GATEWAY_PORT}  | 日志: /home/user/.local/state/sage/logs/gateway.log
   Studio 后端    | 端口: ${STUDIO_BACKEND_PORT}  | 日志: /home/user/.local/state/sage/logs/studio_backend.log
   Studio 前端    | 端口: ${STUDIO_FRONTEND_PORT}  | 日志: /home/user/.local/state/sage/logs/studio.log
======================================================================
```

**Key Points**:
- Services are listed in **workflow order** (LLM → Embedding → Gateway → Backend → Frontend)
- Each service shows: **name**, **port**, **log file path**
- All log paths are unified at the end (not scattered during startup)
- Format is table-like with aligned columns for readability

**Implementation**: See `ChatModeManager.start()` in [src/sage/studio/chat_manager.py](src/sage/studio/chat_manager.py)

## 📦 PyPI Publishing

**All packages MUST be published via `sage-pypi-publisher`:**

### Publishing Workflow

1. **Update Version** (4-digit semantic versioning: `MAJOR.MINOR.PATCH.BUILD`):
   ```bash
   # Edit pyproject.toml and src/sage/studio/_version.py
   # Example: 0.2.0.1 → 0.2.0.2
   ```

2. **Publish to TestPyPI** (testing):
   ```bash
   cd /path/to/sage-pypi-publisher
   ./publish.sh sage-studio --test-pypi --auto-bump patch
   ```

3. **Publish to PyPI** (production):
   ```bash
   ./publish.sh sage-studio --auto-bump patch --no-dry-run
   ```

### Dependencies Publishing

**CRITICAL**: When updating `isage-agentic` or `isage-sias`, publish them FIRST:

```bash
# 1. Publish sage-agentic
cd /path/to/sage-agentic
sage-pypi-publisher build . --upload --no-dry-run

# 2. Publish sage-sias
cd /path/to/sage-sias
sage-pypi-publisher build . --upload --no-dry-run

# 3. Update Studio's pyproject.toml if needed
# Then publish Studio
cd /path/to/sage-studio
./quickstart.sh  # Reinstall with new dependencies
```

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/unit/services/test_agent_orchestrator.py -v

# With coverage
pytest tests/ --cov=sage.studio --cov-report=html
```

## 🔍 Key Components

### Backend (`src/sage/studio/config/backend/api.py`)

- FastAPI server on port 8889
- Endpoints: `/api/flows`, `/api/operators`, `/api/chat`
- Integrates with SAGE kernel for pipeline execution

### Services

- **AgentOrchestrator** (`services/agent_orchestrator.py`): Intent classification, workflow routing
- **PipelineBuilder** (`services/pipeline_builder.py`): Visual flow → SAGE pipeline conversion
- **NodeRegistry** (`services/node_registry.py`): UI node → SAGE operator mapping

### Frontend (`src/sage/studio/frontend/`)

- React 18 + TypeScript + Vite
- Flow editor (React Flow), Chat UI, Properties panel
- Build: `npm run build` (output: `dist/`)

## ⚠️ Common Issues

### Import Errors

If you see `ModuleNotFoundError: No module named 'sage_libs.sage_agentic'`:

1. Check if `isage-agentic` is installed: `pip show isage-agentic`
2. Reinstall Studio: `cd sage-studio && pip install -e .`
3. Verify workspace paths in `sage-studio.code-workspace`

### Startup Failures

If `sage studio start` fails:

1. Check SAGE installation: `python -c "import sage; print('OK')"`
2. Check dependencies: `pip list | grep isage`
3. Run quickstart: `./quickstart.sh`

### Publishing Issues

If `sage-pypi-publisher` fails:

1. Ensure you're in the package root directory
2. Check PyPI tokens in `~/.pypirc`
3. Use `--test-pypi` first to verify

## 📚 Documentation

- **Main README**: [`README.md`](../README.md)
- **Contributing**: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- **Test Chat UI**: [`docs/TEST_CHAT_UI.md`](../docs/TEST_CHAT_UI.md)
- **SAGE Docs**: See SAGE repository

## 🔄 Development Workflow

1. **Before changes**: Pull latest from all dependent repos
2. **During dev**: Run tests frequently (`pytest`)
3. **Before commit**: `ruff check .` and `ruff format .`
4. **After commit**: Verify CI passes
5. **Before release**: Update version, test on TestPyPI, then publish

## 🎯 When Helping with Studio

1. **Understand dependencies**: Studio depends on SAGE + agentic + SIAS
2. **Check imports**: Use correct import paths from SAGE main repo, NOT deprecated paths
3. **Test locally**: Always test startup after changes
4. **Document changes**: Update README if API changes
5. **Version bumps**: Follow 4-digit semver (X.Y.Z.BUILD)

## 🚫 Critical Rules

### NO Backward Compatibility Code

**❌ NEVER create backward compatibility layers:**
- NO stub files for deprecated modules
- NO try-except fallback imports
- NO compatibility shims or adapters for old APIs
- NO "temporary" workarounds that stay forever

**✅ ALWAYS fix issues properly:**
- Update import paths directly to correct locations
- Fix dependency relationships at the source
- Remove deprecated code completely
- Document breaking changes clearly

**Rationale**: Backward compatibility code creates technical debt, hides real issues, and makes debugging harder. Fix problems once, fix them right.

---

**Last Updated**: 2026-01-26
