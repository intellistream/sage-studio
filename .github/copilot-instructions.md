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

## 📦 PyPI Publishing - CRITICAL: Manual One-by-One

**🚨 CRITICAL: NEVER use bash scripts for publishing. ALWAYS use sage-pypi-publisher CLI tool directly.**

### Publishing Workflow (Manual, One-by-One)

1. **Update Version** (4-digit semantic versioning: `MAJOR.MINOR.PATCH.BUILD`):
   ```bash
   # Edit src/sage/studio/_version.py
   # Example: 0.2.0.1 → 0.2.0.2
   ```

2. **Commit and tag changes**:
   ```bash
   git commit -m "chore: bump version to X.Y.Z.W"
   git tag -a vX.Y.Z.W -m "Release sage-studio X.Y.Z.W"
   git push origin vX.Y.Z.W
   ```

3. **Test on TestPyPI** (publish manually, one-by-one):
   ```bash
   cd /path/to/sage-studio
   sage-pypi-publisher publish . -r testpypi --no-dry-run

   # Verify
   pip install -i https://test.pypi.org/simple/ isage-studio==X.Y.Z.W --dry-run
   ```

4. **Publish to Production PyPI** (same command, change to pypi):
   ```bash
   cd /path/to/sage-studio
   sage-pypi-publisher publish . -r pypi --no-dry-run
   ```

### Key Commands

```bash
# ✅ CORRECT: Manual one-by-one using publish command (一步完成)
cd /path/to/sage-studio && sage-pypi-publisher publish . -r testpypi --no-dry-run

# ❌ WRONG: Using ./publish.sh from sage-pypi-publisher
# ./publish.sh sage-studio  # Use CLI directly instead

# ❌ WRONG: Using bash scripts or loops
# for pkg in ...; do sage-pypi-publisher ...; done
```

### Dependencies Publishing

**CRITICAL**: When updating `isage-agentic` or `isage-sias`, publish them FIRST:

```bash
# 1. Publish sage-agentic (in sage-agentic repo)
cd /path/to/sage-agentic
sage-pypi-publisher publish . -r testpypi --no-dry-run
sage-pypi-publisher publish . -r pypi --no-dry-run

# 2. Publish sage-sias (in sage-sias repo)
cd /path/to/sage-sias
sage-pypi-publisher publish . -r testpypi --no-dry-run
sage-pypi-publisher publish . -r pypi --no-dry-run

# 3. Update Studio's pyproject.toml if needed
# Then publish Studio (see above)
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

## ⚙️ Port Configuration

**ALL ports are now environment-variable based** with sensible defaults. Do NOT hardcode port values anywhere.

### Port Mapping Table

| Service | 环境变量 | 默认端口 | 备用端口 | 说明 |
|---------|-----------|---------|---------|-----|
| **Studio 前端** | `STUDIO_FRONTEND_PORT` | 5173 | 4173, 35180 | React + Vite 开发服务器 |
| **Studio 后端** | `STUDIO_BACKEND_PORT` | 8080 | - | FastAPI 后端 API |
| **Gateway** | `SAGE_GATEWAY_PORT` | 8889 | - | sagellm Gateway (OpenAI 兼容) |
| **LLM 推理** | `SAGE_LLM_PORT` | 8001 | 8901 | vLLM 推理引擎（WSL2 上通常用 8901） |
| **Embedding** | `SAGE_EMBEDDING_PORT` | 8090 | - | Embedding 服务 |

### Port Resolution Pattern

**Python 后端** (`src/sage/studio/config/ports.py`):
```python
class StudioPorts:
    FRONTEND = 5173        # 前端开发
    BACKEND = 8080         # 后端 FastAPI
    GATEWAY = 8889         # Gateway

def get_frontend_dev_ports() -> list[int]:
    # 返回所有前端开发端口：[5173, 4173, 35180]
    return [FRONTEND, FRONTEND_PREVIEW, *FRONTEND_DEV_EXTRA]
```

**TypeScript 前端** (`src/sage/studio/frontend/src/store/playgroundStore.ts`):
```typescript
const resolveBackendApiBaseUrl = (): string => {
  // 优先级：VITE_BACKEND_BASE_URL > VITE_API_BASE_URL > VITE_BACKEND_PORT > /api
  const envUrl = import.meta.env.VITE_BACKEND_BASE_URL
  if (envUrl) return envUrl.replace(/\/$/, '')
  // 如果设置了端口，构造：http://localhost:${VITE_BACKEND_PORT}/api
  // 否则使用相对路径 /api
}
```

### 环境变量使用示例

```bash
# 使用默认端口
sage studio start

# 自定义前端端口
STUDIO_FRONTEND_PORT=6173 sage studio start

# 自定义多个端口
STUDIO_FRONTEND_PORT=6173 STUDIO_BACKEND_PORT=9080 SAGE_GATEWAY_PORT=9889 sage studio start

# 前端 Vite 开发服务器
STUDIO_FRONTEND_PORT=6173 npm run dev
```

### CORS 与前端开发

后端 CORS 配置 (`src/sage/studio/config/backend/api.py`) 动态支持所有前端开发端口：
- `localhost:5173` (Vite 开发默认)
- `localhost:4173` (Vite 预览)
- `localhost:35180` (备选开发端口)

**新增开发端口** → 更新 `StudioPorts.FRONTEND_DEV_EXTRA` 和 `get_frontend_dev_ports()`

---

## 🔍 Key Components

### Backend (`src/sage/studio/config/backend/api.py`)

- FastAPI server on `${STUDIO_BACKEND_PORT}` (default: 8080)
- Endpoints: `/api/flows`, `/api/operators`, `/api/chat`
- CORS: Dynamically configured from `StudioPorts.get_frontend_dev_ports()`
- Gateway integration: Reads `SAGE_GATEWAY_HOST` and `SAGE_GATEWAY_PORT`
- Integrates with SAGE kernel for pipeline execution

### Services

- **AgentOrchestrator** (`services/agent_orchestrator.py`): Intent classification, workflow routing
- **PipelineBuilder** (`services/pipeline_builder.py`): Visual flow → SAGE pipeline conversion
- **NodeRegistry** (`services/node_registry.py`): UI node → SAGE operator mapping

### Frontend (`src/sage/studio/frontend/`)

- React 18 + TypeScript + Vite on `${STUDIO_FRONTEND_PORT}` (default: 5173)
- Flow editor (React Flow), Chat UI, Properties panel
- API URL resolution: Environment-driven with fallbacks
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

### NO Summary Documents After Task Completion

**CRITICAL**: Do NOT create summary, recap, or documentation files after completing tasks unless explicitly requested.
- ❌ NO "work_summary.md", "changes_summary.md", or similar
- ❌ NO "completion reports" or status documents
- ✅ DO provide brief inline messages in the conversation
- ✅ DO use commit messages for documentation (git history is your record)

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
