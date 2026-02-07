# 模型切换功能修复 - 快速指南

## ✅ 修复完成

**日期**: 2026-02-07  
**影响**: SAGE Studio Chat 功能现在完全可用

---

## 🎯 修复内容

### 1. 自动启动默认引擎

Studio 启动时会自动启动一个轻量级 LLM 引擎：

```bash
sage studio start
# ✅ 自动启动 Qwen/Qwen2.5-0.5B-Instruct (CPU 友好)
# ✅ Chat 功能立即可用
```

### 2. 动态模型切换

在 Studio 界面切换模型会真正启动新引擎：

- 输入模型名称（如 `Qwen/Qwen2.5-7B-Instruct`）
- 点击"切换"
- 等待 10-30 秒
- 新模型自动加载

---

## 🚀 立即使用

### 重启 Studio

```bash
# 停止旧版本
sage studio stop

# 启动新版本（自动加载默认引擎）
sage studio start
```

### 自定义默认模型

```bash
# 设置环境变量
export SAGE_DEFAULT_MODEL="Qwen/Qwen2.5-1.5B-Instruct"

# 启动 Studio
sage studio start
```

---

## 🧪 测试

运行自动化测试：

```bash
python tests/test_model_switching.py
```

**预期输出**：
- ✅ LLM Gateway 运行中
- ✅ Studio Backend 运行中
- ✅ 模型选择成功
- ✅ 聊天功能正常

---

## 📚 相关文档

- **详细诊断**: [MODEL_SWITCHING_ISSUE_DIAGNOSIS.md](MODEL_SWITCHING_ISSUE_DIAGNOSIS.md)
- **架构说明**: [ARCHITECTURE.md](../ARCHITECTURE.md)
- **使用指南**: [README.md](../README.md)

---

## 🐛 故障排查

### 问题：Chat 仍然无法使用

**检查引擎状态**：

```bash
curl http://localhost:8001/v1/models | python3 -m json.tool
```

**预期输出**：
```json
{
  "object": "list",
  "data": [
    {"id": "Qwen/Qwen2.5-0.5B-Instruct", ...}
  ]
}
```

**如果返回空列表**：

```bash
# 手动启动引擎
sage llm engine start Qwen/Qwen2.5-0.5B-Instruct --engine-kind llm

# 查看引擎日志
tail -f /tmp/sage-studio-engine.log
```

### 问题：模型切换超时

**原因**：大模型首次加载需要下载

**解决**：
1. 等待模型下载完成（查看日志）
2. 或先使用 `huggingface-cli download` 预下载
3. 或使用小模型测试（0.5B、1.5B）

### 问题：端口被占用

**检查占用端口**：

```bash
lsof -i :8001  # LLM Gateway
lsof -i :8889  # Studio Gateway
lsof -i :8080  # Studio Backend
```

**清理僵尸进程**：

```bash
sage studio stop --all
```

---

## 💡 提示

### CPU 推理

默认模型 `Qwen/Qwen2.5-0.5B-Instruct` 设计用于 CPU 推理：
- 内存需求：~2GB
- 响应速度：2-5 秒/请求
- 适合：开发测试、演示

### GPU 加速

如需 GPU 加速，切换到更大模型：

```bash
# 在 Studio 界面选择
Qwen/Qwen2.5-7B-Instruct  # 需要 16GB+ 显存
```

### 云端 API

也支持配置外部 API：

```yaml
# config/models.json
{
  "name": "gpt-4o-mini",
  "base_url": "https://api.openai.com/v1",
  "api_key": "${OPENAI_API_KEY}"
}
```

---

**最后更新**: 2026-02-07
