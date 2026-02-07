# 修复总结：Studio 模型切换功能

## ✅ 修复完成

**修复时间**: 2026-02-07  
**状态**: 已完成，待测试

---

## 📝 改动文件

### 1. `src/sage/studio/studio_manager.py`

**改动**：增强 `start_llm_service()` 方法

```python
# 修改前：只启动 Gateway 框架
def start_llm_service(self, port: int = 8001) -> bool:
    cmd = ["sage-llm", "gateway", ...]
    # 启动后就返回，无引擎

# 修改后：Gateway + 默认引擎
def start_llm_service(self, port: int = 8001) -> bool:
    cmd = ["sage-llm", "gateway", ...]
    # 启动后自动加载默认引擎
    return self._start_default_engine(port)
```

**新增**：`_start_default_engine()` 方法

```python
def _start_default_engine(self, port: int = 8001) -> bool:
    """启动默认 LLM 引擎"""
    default_model = os.getenv("SAGE_DEFAULT_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    engine_cmd = ["sage", "llm", "engine", "start", default_model, "--engine-kind", "llm"]
    # 后台启动并等待就绪
```

### 2. `src/sage/studio/config/backend/api.py`

**改动**：增强 `/api/llm/select` 端点

```python
# 修改前：只更新配置
@app.post("/api/llm/select")
async def select_llm_model(request):
    os.environ["SAGE_CHAT_MODEL"] = request.model_name
    # 注册到 Control Plane（但引擎不存在）
    return {"status": "success"}

# 修改后：真正启动引擎
@app.post("/api/llm/select")
async def select_llm_model(request):
    if is_local and _is_model_name(request.model_name):
        # 启动新引擎
        subprocess.Popen(["sage", "llm", "engine", "start", ...])
        # 等待引擎就绪
        for i in range(30): await asyncio.sleep(1); check_engine()
    return {"status": "success", "engine_started": True}
```

**新增**：`_is_model_name()` 辅助函数

```python
def _is_model_name(name: str) -> bool:
    """判断是否是 Hugging Face 模型名称"""
    # Qwen/xxx, mistral/xxx, etc.
```

**新增导入**：`import asyncio`

### 3. 测试文件

**新增**：`tests/test_model_switching.py`

```python
def test_llm_gateway_running(): ...
def test_studio_backend_running(): ...
def test_model_selection(): ...
def test_chat_functionality(): ...
```

### 4. 文档文件

**新增**：
- `docs/MODEL_SWITCHING_FIX.md` - 快速使用指南
- `docs/MODEL_SWITCHING_ISSUE_DIAGNOSIS.md` - 详细诊断
- `CHANGELOG_LATEST.md` - 版本更新日志

---

## 🧪 测试步骤

### 方式 1：自动化测试

```bash
cd /home/shuhao/sage-studio
python tests/test_model_switching.py
```

### 方式 2：手动测试

```bash
# 1. 停止旧版本
sage studio stop --all

# 2. 启动新版本
sage studio start

# 3. 验证引擎
curl http://localhost:8001/v1/models | python3 -m json.tool

# 应该看到：
# {"data": [{"id": "Qwen/Qwen2.5-0.5B-Instruct", ...}]}

# 4. 访问 Studio
# http://localhost:5173

# 5. 测试聊天功能
# 在 Chat 界面发送消息，应该正常收到回复

# 6. 测试模型切换
# 在模型选择器中输入 "Qwen/Qwen2.5-1.5B-Instruct"
# 点击切换，等待 10-30 秒
# 发送消息测试新模型
```

---

## 📋 提交信息（建议）

```
fix(studio): 修复模型切换功能，支持自动启动引擎

问题描述：
- Studio 启动时只启动了 Gateway 框架，没有加载实际引擎
- 模型切换只更新配置，没有真正启动新引擎
- 导致 Chat 功能无法使用

修复内容：
1. studio_manager.py:
   - 增强 start_llm_service() 自动启动默认引擎
   - 新增 _start_default_engine() 处理引擎启动

2. api.py:
   - 增强 /api/llm/select 支持自动启动引擎
   - 新增 _is_model_name() 判断模型类型
   - 添加 asyncio 导入

3. 测试和文档:
   - 新增自动化测试脚本
   - 新增使用指南和诊断文档
   - 更新 CHANGELOG

影响：
- ✅ Studio 启动后 Chat 功能立即可用
- ✅ 模型切换真正生效
- ✅ 改善用户体验

测试：
python tests/test_model_switching.py
```

---

## 🔗 相关文件

- 快速指南: [docs/MODEL_SWITCHING_FIX.md](docs/MODEL_SWITCHING_FIX.md)
- 详细诊断: [docs/MODEL_SWITCHING_ISSUE_DIAGNOSIS.md](docs/MODEL_SWITCHING_ISSUE_DIAGNOSIS.md)
- 测试脚本: [tests/test_model_switching.py](tests/test_model_switching.py)
- 更新日志: [CHANGELOG_LATEST.md](CHANGELOG_LATEST.md)

---

**准备就绪，等待测试验证**
