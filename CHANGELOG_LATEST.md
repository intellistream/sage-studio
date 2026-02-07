# SAGE Studio - 版本更新日志

## [未发布] - 2026-02-07

### 🐛 重大修复

#### 模型切换功能修复

**问题描述**：
- Studio 启动时虽然启动了 LLM Gateway，但没有加载实际的推理引擎
- 用户在界面切换模型时，只更新了配置但没有真正启动引擎
- 导致 Chat 功能无法使用，所有对话请求失败

**修复内容**：

1. **自动启动默认引擎** (`studio_manager.py`)
   - `start_llm_service()` 现在会在启动 Gateway 后自动启动默认引擎
   - 新增 `_start_default_engine()` 方法处理引擎启动逻辑
   - 默认使用 `Qwen/Qwen2.5-0.5B-Instruct`（CPU 友好的轻量模型）
   - 支持通过 `SAGE_DEFAULT_MODEL` 环境变量自定义默认模型

2. **真正的模型切换** (`api.py`)
   - `/api/llm/select` 端点现在支持自动启动新引擎
   - 智能识别本地 Hugging Face 模型（如 `Qwen/*`, `mistral/*`）
   - 通过 `sage llm engine start` 真正启动引擎进程
   - 等待引擎就绪（最多30秒），提供清晰的状态反馈
   - 新增 `_is_model_name()` 辅助函数判断模型类型

**影响范围**：
- ✅ Studio 启动流程
- ✅ Chat 功能可用性
- ✅ 模型选择和切换体验

**测试**：
- 新增自动化测试脚本 `tests/test_model_switching.py`
- 验证引擎自动启动、模型切换、聊天功能

**文档**：
- 新增 `docs/MODEL_SWITCHING_FIX.md` - 快速使用指南
- 新增 `docs/MODEL_SWITCHING_ISSUE_DIAGNOSIS.md` - 详细诊断报告

**迁移指南**：

对于现有用户：
```bash
# 1. 停止旧版本 Studio
sage studio stop --all

# 2. 更新代码
git pull origin main-dev

# 3. 启动新版本（自动加载默认引擎）
sage studio start
```

对于开发者：
- 查看 `docs/MODEL_SWITCHING_FIX.md` 了解新功能
- 运行 `python tests/test_model_switching.py` 验证修复

**相关 Issue**：
- 修复 #[待填写] - Studio Chat 功能无法使用
- 改进 #[待填写] - 模型切换体验优化

---

## [0.2.4] - 2026-02-06

### 功能改进
- 优化前端 UI 响应速度
- 改进错误提示信息

### Bug 修复
- 修复文件上传偶发失败问题
- 修复会话列表加载延迟

---

## [0.2.3] - 2026-02-05

### 新增功能
- 支持 Guest 模式快速体验
- 增加会话持久化存储

### 改进
- 优化 Pipeline Builder 性能
- 改进节点配置界面

---

_更多历史版本请查看 git 提交记录_
