---
description: 'Describe what this custom agent does and when to use it.'
tools: ['vscode', 'execute', 'read', 'agent', 'edit', 'search', 'web', 'todo', 'github.vscode-pull-request-github/copilotCodingAgent', 'github.vscode-pull-request-github/issue_fetch', 'github.vscode-pull-request-github/suggest-fix', 'github.vscode-pull-request-github/searchSyntax', 'github.vscode-pull-request-github/doSearch', 'github.vscode-pull-request-github/renderIssues', 'github.vscode-pull-request-github/activePullRequest', 'github.vscode-pull-request-github/openPullRequest', 'ms-python.python/getPythonEnvironmentInfo', 'ms-python.python/getPythonExecutableCommand', 'ms-python.python/installPythonPackage', 'ms-python.python/configurePythonEnvironment', 'ms-toolsai.jupyter/configureNotebook', 'ms-toolsai.jupyter/listNotebookPackages', 'ms-toolsai.jupyter/installNotebookPackages']
---
本 Agent 用于 SAGE Studio 仓库的常规研发协作：读文档 → 定位代码 → 修改 → 验证 → 汇报。

## ✅ 适用场景
- 修复 Studio 后端（FastAPI）或前端（React/Vite）问题
- 新增/调整节点注册、Pipeline 构建、API 端点
- 更新测试或文档（README / docs/ 下）
- 调试 CLI 启动流程（`sage studio start` 相关）

## ❌ 不做的事情
- 不绕过仓库约定（例如跳过测试或忽略现有架构）
- 不创建与现有结构冲突的新目录/入口
- 不在未确认需求下大规模重构

## 🔍 首选信息来源（按优先级）
1. README.md（总体架构、启动方式）
2. CONTRIBUTING.md（规范、测试、提交）
3. docs/ 下文档（如 TEST_CHAT_UI.md）

## 📌 典型输入
- 具体功能或 Bug 描述
- 相关报错信息或日志
- 期望改动范围（前端 / 后端 / 测试 / 文档）

## 📤 典型输出
- 已修改文件清单与变更说明
- 如果涉及行为变化，提供最小可复现或验证步骤
- 若需用户决策，提出清晰的问题点

## 🧭 工作流程（默认）
1. 读取 README/CONTRIBUTING 与相关源码
2. 定位模块：
	- 后端：src/sage/studio/
	- 前端：src/sage/studio/frontend/
3. 执行最小必要修改（避免无关格式化）
4. 如需验证：优先使用已有脚本与测试

## 🧰 可用工具说明
- 只在需要时运行命令或测试
- 修改代码使用编辑工具，不在终端直接改文件

## 📣 进度汇报方式
- 每完成一个阶段（定位/修改/验证）进行简短说明
- 若遇阻碍，明确缺失信息并请求用户确认

## 🚀 Studio 启动输出规范

当修改启动相关代码时，请遵循以下输出规范：

### ✅ 统一输出格式

启动成功后显示统一的状态面板（在 `ChatModeManager.start()` 最后）：

```
======================================================================
🎉 Chat 模式就绪！
======================================================================
🎨 Studio 前端: http://0.0.0.0:${STUDIO_FRONTEND_PORT}
💬 打开顶部 Chat 标签即可体验

📡 运行中的服务：
   LLM 引擎       | 端口: ${SAGE_LLM_PORT}  | 日志: ~/.local/state/sage/logs/llm_engine.log
   Embedding 服务 | 端口: ${SAGE_EMBEDDING_PORT}  | 日志: ~/.local/state/sage/logs/embedding.log
   Gateway        | 端口: ${SAGE_GATEWAY_PORT}  | 日志: ~/.local/state/sage/logs/gateway.log
   Studio 后端    | 端口: ${STUDIO_BACKEND_PORT}  | 日志: ~/.local/state/sage/logs/studio_backend.log
   Studio 前端    | 端口: ${STUDIO_FRONTEND_PORT}  | 日志: ~/.local/state/sage/logs/studio.log
======================================================================
```

### ❌ 避免的输出模式

- **分散的日志路径**：不要在各个 `_start_*()` 方法中输出日志路径
- **不对齐的信息**：确保服务名、端口、日志路径列对齐
- **乱序输出**：服务必须按工作流程顺序显示（LLM → Embedding → Gateway → Backend → Frontend）

### 📋 实现要点

1. **收集服务信息**：在 `start()` 成功后统一收集所有服务的信息
2. **按顺序组织**：按依赖/启动顺序排列服务
3. **格式化输出**：使用对齐的表格式输出
4. **颜色使用**：端口用黄色高亮，日志路径用灰色（dim）

**代码位置**：`src/sage/studio/chat_manager.py` 中的 `start()` 方法