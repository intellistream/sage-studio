# SAGE Studio 引擎启动和健康检查修复总结

## 问题描述

Studio 启动时引擎启动失败，聊天功能无法使用。错误信息：`No healthy engines available for model`.

## 根本原因

1. **错误的引擎启动命令**：Studio 使用了不存在的 `sage llm engine start`命令
2. **缺失的注册机制**：引擎启动后无法向 Gateway Control Plane 注册
3. **未实现的健康检查**：Control Plane 的健康检查功能未实现实际 HTTP 请求
4. **未启动的生命周期管理器**：Gateway 没有启动 LifecycleManager

## 修复内容

### 1. 修复引擎启动命令 (sage-studio)

**文件**: `sage-studio/src/sage/studio/studio_manager.py`, `sage-studio/src/sage/studio/config/backend/api.py`

**修改**:
- 将 `sage llm engine start` 替换为 `sage-llm serve-engine`
- 引擎端口改为 9001（避免与 Gateway 8001 冲突）
- 添加引擎注册逻辑

**修改后命令**:
```bash
sage-llm serve-engine --model <model_name> --port 9001 --host 0.0.0.0
```

### 2. 添加引擎管理 API (sagellm-gateway)

**新文件**: `sagellm-gateway/src/sagellm_gateway/management_routes.py`

**端点**:
- `POST /v1/management/engines/register` - 注册引擎
- `DELETE /v1/management/engines/{engine_id}` - 取消注册
- `GET /v1/management/engines` - 列出所有引擎
- `GET /v1/management/engines/{engine_id}` - 获取引擎详情

**文件**: `sagellm-gateway/src/sagellm_gateway/server.py`

**修改**:
- 导入并挂载 management_routes
- 设置 Control Plane 引用

### 3. 实现健康检查 (sagellm-control-plane)

**文件**: `sagellm-control-plane/src/sagellm_control/lifecycle.py`

**修改**:
- 实现 `check_health` 方法，使用 httpx 发送 HTTP 请求到引擎的 `/health` 端点
- 修改前：返回固定的 `True`
- 修改后：实际检查引擎健康状态

### 4. 启动生命周期管理器 (sagellm-control-plane)

**文件**: `sagellm-control-plane/src/sagellm_control/manager.py`

**修改**:
- 添加 `start()` 方法：创建并启动 LifecycleManager
- 添加 `stop()` 方法：停止 LifecycleManager
- 添加 `_on_engine_state_change` 回调：同步引擎状态
- 在 `register_engine` 时将引擎注册到 LifecycleManager
- 在 `unregister_engine` 时从 LifecycleManager 取消注册

**文件**: `sagellm-gateway/src/sagellm_gateway/server.py`

**修改**:
- 在 `lifespan` 中调用 `control_plane.start()`
- 在 shutdown 时调用 `control_plane.stop()`

## 架构流程

### 启动流程

```
1. Studio starts
   ↓
2. Launch Gateway (8889)
   → Gateway creates Control Plane
   → Start LifecycleManager (health check loop)
   ↓
3. Launch LLM Gateway (8001)
   ↓
4. Launch Engine (9001)
   → sage-llm serve-engine --model <model> --port 9001
   → Engine loads model (30-60s on CPU)
   → Engine HTTP server ready
   ↓
5. Register Engine to Control Plane
   → POST /v1/management/engines/register
   → Control Plane registers engine (state: STARTING)
   → LifecycleManager adds engine to monitoring
   ↓
6. Health Check Loop (every 10s)
   → LifecycleManager checks GET http://localhost:9001/health
   → If healthy: transition state STARTING → READY
   → Update is_healthy flag
   ↓
7. Chat Request
   → Control Plane finds healthy engine
   → Route request to engine
   → Return response
```

### 引擎注册请求示例

```json
POST http://localhost:8001/v1/management/engines/register
{
  "engine_id": "studio-engine-Qwen-Qwen2.5-0.5B-Instruct",
  "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
  "host": "localhost",
  "port": 9001,
  "engine_kind": "llm",
  "metadata": {"source": "studio_startup"}
}
```

## 依赖项

需要确保以下包已安装：
- `httpx` - 用于健康检查的 HTTP 客户端
- `isagellm-gateway` - Gateway 服务
- `isagellm-control-plane` - Control Plane 和调度器

## 测试步骤

### 1. 重新安装修改的包

```bash
# 安装 sagellm-control-plane (包含健康检查修复)
cd /home/shuhao/sagellm-control-plane
pip install -e .

# 安装 sagellm-gateway (包含管理API)
cd /home/shuhao/sagellm-gateway
pip install -e .

# 安装 sage-studio (包含启动命令修复)
cd /home/shuhao/sage-studio
pip install -e .
```

### 2. 停止现有服务

```bash
cd /home/shuhao/sage-studio
sage studio stop
```

### 3. 启动 Studio

```bash
sage studio start
```

### 4. 验证引擎状态

```bash
# 检查引擎进程
ps aux | grep "sage-llm serve-engine"

# 检查引擎健康状态（等待30秒让模型加载完成）
sleep 30
curl http://localhost:9001/health

# 检查 Control Plane 中的引擎状态
curl http://localhost:8001/v1/management/engines | python3 -m json.tool
```

预期输出：
```json
{
    "engines": [
        {
            "engine_id": "studio-engine-Qwen-Qwen2.5-0.5B-Instruct",
            "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
            "host": "localhost",
            "port": 9001,
            "state": "READY",
            "is_healthy": true,
            "engine_kind": "llm"
        }
    ],
    "total": 1,
    "healthy": 1
}
```

### 5. 测试聊天功能

通过 Studio 界面发送测试消息，或使用 API：

```bash
curl -X POST http://localhost:8889/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how are you?"}'
```

## 已知限制

1. **模型加载时间**：CPU 上加载 Qwen2.5-0.5B 需要 30-60 秒
2. **健康检查延迟**：引擎状态从 STARTING 到 READY 需要等待健康检查周期（默认 10秒）
3. **并发限制**：当前 Control Plane 使用简单的 Round-Robin 调度，不支持复杂的负载均衡

## 后续优化

1. **启动优化**：
   - 支持预热跳过（pre-warmed engines）
   - 并行启动多个轻量引擎

2. **健康检查优化**：
   - 支持可配置的健康检查间隔
   - 添加更详细的健康指标（延迟、吞吐量等）

3. **调度增强**：
   - 基于负载的智能路由
   - 支持引擎优先级和亲和性

## 相关文件清单

### sage-studio
- `src/sage/studio/studio_manager.py` (修改)
- `src/sage/studio/config/backend/api.py` (修改)

### sagellm-gateway
- `src/sagellm_gateway/management_routes.py` (新增)
- `src/sagellm_gateway/server.py` (修改)

### sagellm-control-plane
- `src/sagellm_control/lifecycle.py` (修改)
- `src/sagellm_control/manager.py` (修改)

## 版本要求

- Python >= 3.10
- httpx >= 0.24.0
- isagellm-gateway >= 0.1.0
- isagellm-control-plane >= 0.1.0
- isage-studio >= 0.2.0

## 贡献者

- GitHub Copilot - 问题诊断和代码修复
- IntelliStream Team - 架构设计和review

---

最后更新：2026-02-07
