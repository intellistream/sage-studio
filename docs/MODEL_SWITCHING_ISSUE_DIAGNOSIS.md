# Studio 模型切换问题诊断报告

## ✅ 修复状态：已完成

**修复时间**: 2026-02-07  
**修复版本**: Studio v0.2.5+

### 🛠️ 已实现的修复

#### 1. 自动启动默认引擎 (`studio_manager.py`)

修改了 `start_llm_service` 方法：
- ✅ 启动 LLM Gateway 后自动启动默认引擎
- ✅ 使用轻量级 CPU 友好模型 (`Qwen/Qwen2.5-0.5B-Instruct`)
- ✅ 检测已运行的引擎，避免重复启动
- ✅ 提供详细的状态反馈和日志位置

```python
def start_llm_service(self, port: int = 8001) -> bool:
    """启动 LLM 推理服务（Control Plane Gateway + 默认引擎）"""
    # 1. 启动 Gateway
    # 2. 自动启动默认引擎（新增）
    # 3. 等待引擎注册并验证
```

#### 2. 真正的模型切换 (`api.py`)

增强了 `/api/llm/select` 端点：
- ✅ 识别本地 Hugging Face 模型
- ✅ 自动调用 `sage llm engine start` 启动新引擎
- ✅ 等待引擎就绪（最多30秒）
- ✅ 返回详细的启动状态

```python
@app.post("/api/llm/select")
async def select_llm_model(request: SelectModelRequest):
    """选择要使用的 LLM 模型（支持自动启动引擎）"""
    if is_local and _is_model_name(request.model_name):
        # 本地模型，启动引擎
        subprocess.Popen(["sage", "llm", "engine", "start", ...])
        # 等待引擎就绪
```

### 🚀 如何使用修复后的功能

#### 方式 1：重启 Studio（推荐）

```bash
# 停止旧的 Studio
sage studio stop

# 启动新版本（自动启动默认引擎）
sage studio start

# 访问 Studio
# http://localhost:5173
```

**预期行为**：
- ✅ Studio 启动后自动加载 `Qwen/Qwen2.5-0.5B-Instruct`
- ✅ Chat 功能立即可用
- ✅ 可在界面切换其他模型

#### 方式 2：在线切换模型

在 Studio 界面：
1. 点击模型选择下拉框
2. 选择或输入模型名称（如 `Qwen/Qwen2.5-7B-Instruct`）
3. 点击"切换"
4. 等待 10-30 秒（引擎启动时间）
5. 开始使用新模型

#### 方式 3：环境变量配置

设置默认模型：

```bash
# 在 .env 文件或环境变量中设置
export SAGE_DEFAULT_MODEL="Qwen/Qwen2.5-1.5B-Instruct"

# 重启 Studio
sage studio restart
```

### 🧪 验证修复

运行测试脚本：

```bash
cd sage-studio
python tests/test_model_switching.py
```

**预期输出**：
```
🔍 测试 1: 检查 LLM Gateway 是否运行...
✅ LLM Gateway 运行中，当前模型: Qwen/Qwen2.5-0.5B-Instruct

🔍 测试 2: 检查 Studio Backend 是否运行...
✅ Studio Backend 运行中

🔍 测试 3: 测试模型选择功能...
✅ 模型选择成功: 已启动并切换到模型

🔍 测试 4: 测试聊天功能...
✅ 聊天功能正常

🎉 所有测试通过！模型切换功能正常工作。
```

### 📝 相关改动

| 文件 | 改动 | 说明 |
|------|------|------|
| `studio_manager.py` | `start_llm_service()` | 自动启动默认引擎 |
| `studio_manager.py` | `_start_default_engine()` | 新增：引擎启动逻辑 |
| `api.py` | `/api/llm/select` | 支持真正的引擎切换 |
| `api.py` | `_is_model_name()` | 新增：判断 HF 模型名 |

---

## 📋 原始诊断（保留供参考）

## 🔍 问题现象

1. **模型切换无法生效**：用户在 Studio 界面切换模型后，Chat 仍然无法使用
2. **启动 Studio 时的服务状态**：
   - ✅ sagellm-gateway (8889端口) - Control Plane Gateway
   - ✅ sage-llm gateway (8001端口) - LLM Gateway (空的，无引擎)

## 🐛 根本原因

### 1. LLM 引擎未启动

**当前状态**：
```bash
$ curl http://localhost:8001/v1/models
{"object": "list", "data": []}  # 空列表！
```

**日志显示**：
```
✅ Control Plane Manager initialized
✅ SageLLM adapter ready
```

但是 **没有实际的 LLM 引擎实例在运行**！

### 2. 模型切换逻辑的限制

当前 `/api/llm/select` 端点的实现：

```python
@app.post("/api/llm/select")
async def select_llm_model(request: SelectModelRequest):
    # ✅ 1. 更新环境变量
    os.environ["SAGE_CHAT_MODEL"] = request.model_name
    os.environ["SAGE_CHAT_BASE_URL"] = request.base_url
    
    # ✅ 2. 持久化到 config/models.json
    api_key = _persist_model_selection(request.model_name, request.base_url)
    
    # ✅ 3. 尝试向 Control Plane 注册外部引擎
    requests.post(f"{GATEWAY_BASE_URL}/v1/management/engines/register", ...)
    
    # ❌ 问题：没有真正启动/切换 LLM 引擎
    return {"status": "success"}
```

**缺失的功能**：
- ❌ 没有通过 Control Plane API 启动新的 LLM 引擎
- ❌ 没有停止旧引擎并加载新模型
- ❌ 只是注册了外部引擎信息，但外部引擎根本不存在

## ✅ 解决方案

### 方案 1：手动启动 LLM 引擎（立即可用）

在 Studio 启动后，手动启动一个 LLM 引擎：

```bash
# 启动轻量级模型（CPU 可运行）
sage llm engine start Qwen/Qwen2.5-0.5B-Instruct --engine-kind llm

# 或 GPU 模型
sage llm engine start Qwen/Qwen2.5-7B-Instruct --engine-kind llm

# 验证引擎已启动
curl http://localhost:8001/v1/models
# 应该看到：{"data": [{"id": "Qwen/Qwen2.5-0.5B-Instruct", ...}]}
```

然后在 Studio 界面就可以正常聊天了。

### 方案 2：修复模型切换功能（需要开发）

修改 `/api/llm/select` 端点，真正启动/切换引擎：

```python
@app.post("/api/llm/select")
async def select_llm_model(request: SelectModelRequest):
    # 1. 更新配置（现有逻辑）
    os.environ["SAGE_CHAT_MODEL"] = request.model_name
    
    # 2. 通过 Control Plane API 启动新引擎
    if _is_local_model(request.model_name):
        # 如果是本地模型，启动 vLLM 引擎
        response = requests.post(
            f"{GATEWAY_BASE_URL}/v1/management/engines/start",
            json={
                "model_id": request.model_name,
                "engine_kind": "llm",
                "port": 8001,
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(500, "启动引擎失败")
    else:
        # 外部 API，只需注册
        requests.post(
            f"{GATEWAY_BASE_URL}/v1/management/engines/register",
            json={...}
        )
    
    # 3. 等待引擎就绪
    await _wait_for_engine_ready(request.model_name)
    
    return {"status": "success"}
```

### 方案 3：Studio 自动启动默认引擎（改进启动流程）

修改 `studio_manager.py` 的 `start_llm_service` 方法：

```python
def start_llm_service(self, port: int = 8001) -> bool:
    """启动 LLM 推理服务（Control Plane Gateway + 默认引擎）"""
    
    # 1. 启动 Gateway
    cmd = ["sage-llm", "gateway", "--host", "0.0.0.0", "--port", str(port)]
    # ... 启动逻辑 ...
    
    # 2. 启动默认引擎（新增）
    default_model = os.getenv("SAGE_DEFAULT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    console.print(f"[blue]🔧 启动默认 LLM 引擎: {default_model}...[/blue]")
    
    engine_cmd = [
        "sage", "llm", "engine", "start", 
        default_model,
        "--engine-kind", "llm"
    ]
    subprocess.run(engine_cmd, check=True)
    
    # 3. 验证引擎已注册
    time.sleep(5)
    response = requests.get("http://localhost:8001/v1/models")
    models = response.json().get("data", [])
    
    if models:
        console.print(f"[green]✅ LLM 引擎启动成功: {models[0]['id']}[/green]")
        return True
    else:
        console.print("[yellow]⚠️  引擎启动但未返回模型列表[/yellow]")
        return False
```

## 📊 当前架构解析

```
用户请求 (Studio Chat UI)
    ↓
Studio Backend (8080) /api/chat/message
    ↓ HTTP POST
Gateway (8889) /v1/chat/completions
    ↓ 路由选择
LLM Gateway (8001) /v1/chat/completions
    ↓ Control Plane 调度
[无引擎] ← 这里是问题所在！
```

**应该是**：

```
用户请求 (Studio Chat UI)
    ↓
Studio Backend (8080) /api/chat/message
    ↓ HTTP POST
Gateway (8889) /v1/chat/completions
    ↓ 路由选择
LLM Gateway (8001) /v1/chat/completions
    ↓ Control Plane 调度
vLLM Engine (实际推理) ← 需要启动这个！
```

## 🎯 推荐立即行动

对于用户：

```bash
# 1. 停止 Studio
sage studio stop

# 2. 启动默认 LLM 引擎
sage llm engine start Qwen/Qwen2.5-0.5B-Instruct --engine-kind llm

# 3. 重新启动 Studio
sage studio start

# 4. 验证引擎状态
curl http://localhost:8001/v1/models | python3 -m json.tool
```

对于开发者：

1. 实现 **方案 3**（自动启动默认引擎）
2. 修复 `/api/llm/select` 端点，支持动态引擎切换
3. 添加引擎管理 UI（启动/停止/切换引擎）

## 📝 相关文档

- Control Plane 管理 API: `SAGE-Pub/docs_src/dev-notes/l1-common/control-plane-enhancement.md`
- LLM Engine 启动: `sage llm engine --help`
- Gateway 架构: `sagellm-gateway/README.md`

---

**诊断时间**: 2026-02-07  
**诊断工具**: SAGE Studio Copilot Agent
