# Studio LLM 集成改进 - Qwen 1.5B CPU Backend

## 📋 改进内容

### 1. 默认模型升级
- **之前**: `Qwen/Qwen2.5-0.5B-Instruct` (500M 参数)
- **现在**: `Qwen/Qwen2.5-1.5B-Instruct` (1.5B 参数)
- **优势**: 更好的推理能力，仍然轻量且支持 CPU

### 2. Backend 切换
- **之前**: 使用 `sage-llm serve-engine` 命令（可能不支持 CPU）
- **现在**: 直接使用 `sageLLM Core` API (`LLMEngine` + `LLMEngineConfig`)
- **优势**: 
  - 原生 CPU backend 支持 (`backend_type="cpu"`)
  - 更好的控制和错误处理
  - 与用户验证的 `test_qwen_1_5b_cpu.py` API 一致

### 3. 自动启动
- Studio 启动时自动启动 sageLLM CPU engine
- 自动注册到 Gateway Control Plane
- 提供 OpenAI 兼容的 `/v1/chat/completions` API

## 🔧 修改的文件

### `src/sage/studio/studio_manager.py`

1. **`_start_default_engine()` 方法**:
   - 改用 sageLLM Core API
   - 生成并执行 Python 脚本（而非调用外部命令）
   - 使用 CPU backend

2. **新增 `_create_sagellm_cpu_engine_script()` 方法**:
   - 生成完整的 FastAPI 服务器脚本
   - 包装 `LLMEngine` 提供 HTTP API
   - 实现 OpenAI 兼容的 `/v1/chat/completions` 端点

## 🚀 使用方式

### 启动 Studio
```bash
# 标准启动（会自动启动 LLM engine）
sage studio start

# 或使用快捷脚本
cd /home/shuhao/sage-studio
./quickstart.sh
```

### 查看引擎状态
```bash
# 检查引擎是否运行
curl http://localhost:9001/health

# 查看引擎日志
tail -f /tmp/sage-studio-engine.log

# 测试 Chat API
curl -X POST http://localhost:9001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-1.5B-Instruct",
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 50
  }'
```

### 手动启动引擎（如果自动启动失败）
```bash
# 使用生成的脚本
python ~/.cache/sage/studio/start_cpu_engine.py

# 或使用原始测试脚本
cd /home/shuhao/sagellm-core
python test_qwen_1_5b_cpu.py
```

## 🔍 诊断工具

### 1. 测试 Studio LLM 集成
```bash
cd /home/shuhao/sage-studio
python test_studio_llm_integration.py
```

**检查内容**:
- ✅ 脚本生成是否成功
- ✅ 脚本内容是否正确
- ✅ Gateway 状态
- ✅ 默认模型配置

### 2. 诊断对话失败问题
```bash
cd /home/shuhao/sage-studio
python diagnose_chat.py
```

**检查内容**:
- ✅ Gateway (8889) 状态
- ✅ LLM Engine (9001) 状态
- ✅ Studio Backend (8080+) 状态
- ✅ Gateway Models API
- ✅ Chat API 功能测试

## 📊 架构图

```
┌─────────────────────────────────────────────────────────┐
│              Studio Frontend (React + Vite)              │
│                   http://localhost:5173                  │
└─────────────────────────────────────────────────────────┘
                         ⬇ HTTP REST API
┌─────────────────────────────────────────────────────────┐
│           Studio Backend (FastAPI - api.py)              │
│                   http://localhost:8080                  │
└─────────────────────────────────────────────────────────┘
                         ⬇ Chat requests
┌─────────────────────────────────────────────────────────┐
│         sageLLM Gateway (Control Plane)                  │
│                   http://localhost:8889                  │
│              /v1/chat/completions (proxy)                │
└─────────────────────────────────────────────────────────┘
                         ⬇ Route to engine
┌─────────────────────────────────────────────────────────┐
│    sageLLM CPU Engine (FastAPI + LLMEngine)              │
│                   http://localhost:9001                  │
│                                                           │
│  ┌────────────────────────────────────────────────┐     │
│  │  LLMEngine (sagellm-core)                      │     │
│  │  - Model: Qwen/Qwen2.5-1.5B-Instruct          │     │
│  │  - Backend: CPU (backend_type="cpu")          │     │
│  │  - API: /v1/chat/completions (OpenAI-compat)  │     │
│  └────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

## ⚠️ 常见问题

### 1. 对话失败 - Engine 未运行
**症状**: Studio Chat 无响应，或显示连接错误

**诊断**:
```bash
curl http://localhost:9001/health
```

**解决**:
```bash
# 查看引擎日志
tail -f /tmp/sage-studio-engine.log

# 手动启动引擎
python ~/.cache/sage/studio/start_cpu_engine.py
```

### 2. 对话失败 - 引擎未注册到 Gateway
**症状**: Gateway `/v1/models` 返回空列表

**诊断**:
```bash
curl http://localhost:8889/v1/models
```

**解决**:
```bash
# 手动注册引擎
curl -X POST http://localhost:8889/v1/management/engines/register \
  -H "Content-Type: application/json" \
  -d '{
    "engine_id": "studio-cpu",
    "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
    "host": "localhost",
    "port": 9001,
    "engine_kind": "llm"
  }'
```

### 3. CPU 推理慢
**症状**: 对话响应时间超过 30 秒，或超时

**原因**: CPU 推理比 GPU 慢 10-100 倍

**解决**:
- 使用更小的 `max_tokens` (例如 128 而非 512)
- 考虑切换到 GPU backend（如果有 GPU）
- 使用更小的模型（如 0.5B）

### 4. 端口冲突
**症状**: 引擎启动失败，提示端口被占用

**解决**:
```bash
# 找到占用端口的进程
lsof -i :9001

# 停止旧进程
kill <PID>

# 或使用其他端口
export SAGE_ENGINE_PORT=9002
```

## 📝 环境变量

### 覆盖默认模型
```bash
export SAGE_DEFAULT_MODEL="Qwen/Qwen2.5-0.5B-Instruct"  # 使用更小模型
sage studio start
```

### 覆盖引擎端口
```bash
export SAGE_ENGINE_PORT=9002  # 使用其他端口
sage studio start
```

### 禁用自动启动 LLM
```bash
# 在 sage studio start 时传入参数
sage studio start --no-llm
```

## 🎯 下一步

1. ✅ 测试 Studio 启动: `sage studio start`
2. ✅ 运行诊断工具: `python diagnose_chat.py`
3. ✅ 在 Studio Chat 界面测试对话
4. ✅ 查看引擎日志定位具体问题

## 📚 参考文档

- [sagellm-core README](../sagellm-core/README.md)
- [Studio 架构文档](ARCHITECTURE.md)
- [用户验证脚本](../sagellm-core/test_qwen_1_5b_cpu.py)
