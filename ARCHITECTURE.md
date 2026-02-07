# SAGE Studio Architecture

## 正确的架构设计

### 服务分层

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                   │
│                       Port: 5173                             │
│  - Visual Pipeline Builder                                   │
│  - Chat Playground UI                                        │
│  - Properties Configuration Panel                            │
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTP /api/*
┌─────────────────────────────────────────────────────────────┐
│            Studio Backend (FastAPI on SAGE)                  │
│                  Port: 8080 (可配置)                          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ 🔧 SAGE Framework Capabilities:                          ││
│  │  - Pipeline Builder & Operators Registry                 ││
│  │  - Jobs Management & Execution                           ││
│  │  - Dataset Management & File Upload                      ││
│  │  - User Authentication & Sessions                        ││
│  │  - Node Configuration & Validation                       ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                          ↓ HTTP Client
┌─────────────────────────────────────────────────────────────┐
│             sageLLM Gateway (Optional)                       │
│                       Port: 8889                             │
│  - LLM Chat Completions (OpenAI compatible)                 │
│  - Control Plane Integration                                │
│  - Session Management (LLM sessions)                         │
└─────────────────────────────────────────────────────────────┘
```

### 为什么 Studio 后端必须独立运行？

**❌ 错误设计**：将 Studio API 合并到 sageLLM Gateway

**✅ 正确设计**：Studio 后端独立运行，作为 SAGE 框架的管理层

#### 原因：

1. **功能范围不同**
   - **Studio Backend**: 管理整个 SAGE 框架（pipelines, operators, jobs, datasets）
   - **sageLLM Gateway**: 仅提供 LLM 推理服务（chat completions, embeddings）

2. **依赖层级**
   - **Studio Backend**: 依赖完整的 SAGE 框架（L1-L5，包含 middleware, operators）
   - **sageLLM Gateway**: 独立的 LLM 服务，不依赖 SAGE 框架

3. **责任分离**
   - **Studio Backend**: 作为 SAGE 的控制平面（构建和管理 pipelines）
   - **sageLLM Gateway**: 作为 LLM 的推理平面（执行推理请求）

4. **可扩展性**
   - Studio 可以管理多种类型的 pipelines（不仅限于 LLM）
   - Gateway 只关注 LLM 推理优化

## 端口配置策略

### 默认端口

- **Frontend**: `5173` (Vite 开发服务器)
- **Backend**: `8080` (可通过环境变量配置)
- **Gateway**: `8889` (可选，仅当需要 LLM 功能时)

### 端口冲突解决

如果 8080 端口被占用，Studio 会**自动尝试**以下端口：

```
8080 → 8081 → 8082 → 8083 → 8888 → 8090
```

#### 手动指定端口

**方法 1**: 环境变量（推荐）

```bash
export STUDIO_BACKEND_PORT=8081
sage studio start
```

**方法 2**: 命令行参数

```bash
sage studio start --backend-port 8081
```

**方法 3**: 修改配置文件

编辑 `~/.config/sage/studio.config.json`:

```json
{
  "port": 5173,
  "backend_port": 8081,
  "host": "0.0.0.0",
  "dev_mode": true
}
```

## API 端点

### Studio Backend (`http://localhost:8080`)

#### 认证
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/guest` - 访客登录
- `GET /api/auth/me` - 获取当前用户
- `POST /api/auth/logout` - 登出

#### Pipeline 管理
- `GET /api/jobs` - 获取所有 jobs
- `POST /api/jobs` - 创建新 job
- `GET /api/jobs/{job_id}` - 获取 job 详情
- `POST /api/jobs/{job_id}/start` - 启动 job
- `POST /api/jobs/{job_id}/stop` - 停止 job

#### Operators
- `GET /api/operators` - 获取所有 operators
- `GET /api/operators/{id}` - 获取 operator 详情

#### 数据集
- `GET /api/datasets` - 获取所有数据集
- `GET /api/datasets/{name}` - 获取数据集详情

#### 健康检查
- `GET /health` - 后端健康状态

### sageLLM Gateway (`http://localhost:8889`)

- `POST /v1/chat/completions` - Chat completions (OpenAI compatible)
- `POST /v1/embeddings` - Embeddings
- `GET /v1/models` - List models
- Session management endpoints

## 验证服务状态

```bash
# 检查 Studio 前端
curl http://localhost:5173/

# 检查 Studio 后端
curl http://localhost:8080/health

# 检查 Gateway（可选）
curl http://localhost:8889/health

# 测试认证
curl -X POST http://localhost:8080/api/auth/guest
```

## 常见问题

### Q: 为什么不能所有服务都用 8889？

**A**: 因为 Studio 需要完整的 SAGE 框架能力（pipeline builder, operators, jobs），而 sageLLM Gateway 只提供 LLM 推理。将它们合并会导致职责混乱和依赖混乱。

### Q: Studio 后端和 Gateway 的关系？

**A**: Studio 后端是**客户端**，可以调用 Gateway 的 LLM 服务。它们是独立的服务，通过 HTTP 通信。

### Q: 如果 8080 被占用怎么办？

**A**: Studio 会自动尝试其他端口（8081, 8082, ...）。你也可以通过 `STUDIO_BACKEND_PORT` 环境变量手动指定。

### Q: 可以只运行 Studio 后端而不启动 Gateway 吗？

**A**: 可以。Gateway 是可选的，只有当你需要使用 Chat Playground 的 LLM 功能时才需要。Pipeline 构建和执行不依赖 Gateway。

## 开发指南

### 启动完整服务栈

```bash
# 1. 启动 Gateway（可选）
sagellm-gateway --host 0.0.0.0 --port 8889

# 2. 启动 Studio（前端 + 后端）
sage studio start

# 或者一键启动（会自动启动所需服务）
sage studio start --yes
```

### 仅启动后端

```bash
cd sage-studio/src/sage/studio/config/backend
python api.py
```

### 前端开发

```bash
cd sage-studio/src/sage/studio/frontend
npm run dev
```

## 架构决策记录

### ADR-001: Studio 后端必须独立运行

**日期**: 2026-02-07

**状态**: 已采纳

**背景**: 
最初尝试将 Studio 认证 API 合并到 sageLLM Gateway，以避免 8080 端口冲突。

**决策**: 
恢复 Studio 后端独立运行，使用智能端口选择来解决冲突。

**理由**:
1. Studio 需要完整的 SAGE 框架能力（不仅仅是 LLM）
2. Gateway 是独立的 LLM 推理服务，不应包含 SAGE 框架逻辑
3. 职责分离，便于维护和扩展
4. Studio 可以调用 Gateway，而不是被合并到 Gateway

**后果**:
- ✅ 架构清晰，职责明确
- ✅ Studio 可以管理所有类型的 SAGE pipelines
- ✅ Gateway 保持独立，专注于 LLM 推理
- ⚠️ 需要处理端口冲突（通过智能端口选择解决）
