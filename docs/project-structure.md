# Project Structure

SAGE Studio 项目结构说明文档。

## 根目录结构

```
sage-studio/
├── .github/                 # GitHub 配置
│   ├── agents/              # GitHub Copilot Chat 自定义 Agent
│   │   └── sage-studio.agent.md
│   └── copilot-instructions.md  # VS Code Copilot 指令
├── docs/                    # 项目文档
│   └── testing-chat-ui.md   # Chat UI 测试文档
├── scripts/                 # 开发和测试脚本
│   ├── verify_chat_ui.py    # Chat UI 验证脚本
│   ├── test_playground.sh   # Playground 测试脚本
│   └── README.md            # 脚本使用说明
├── src/sage/studio/         # 主要源代码（见下文）
├── tests/                   # 测试套件
│   ├── unit/                # 单元测试
│   └── integration/         # 集成测试
├── quickstart.sh            # 快速安装脚本
├── pyproject.toml           # Python 项目配置
├── README.md                # 项目主文档
├── CHANGELOG.md             # 版本更新日志
├── CONTRIBUTING.md          # 贡献指南
└── LICENSE                  # 开源许可证

## 源代码结构

```
src/sage/studio/
├── __init__.py              # 包初始化
├── _version.py              # 版本信息
├── chat_manager.py          # 服务编排器（LLM 集成）
├── studio_manager.py        # 核心管理器（CLI）
├── adapters/                # 适配器层
│   └── __init__.py
├── config/                  # 配置和后端
│   ├── knowledge_sources.yaml
│   └── backend/
│       └── api.py           # FastAPI 应用和路由
├── data/                    # 数据定义
│   └── operators/           # 节点定义（JSON）
│       ├── FileSource.json
│       ├── SimpleRetriever.json
│       ├── OpenAIGenerator.json
│       └── ...
├── frontend/                # React 前端应用
│   ├── src/
│   │   ├── components/      # React 组件
│   │   ├── pages/           # 页面组件
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── stores/          # 状态管理（Zustand）
│   │   ├── services/        # API 客户端
│   │   └── main.tsx         # 入口文件
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── models/                  # 数据模型（Pydantic）
│   ├── __init__.py
│   └── agent_step.py
├── services/                # 业务逻辑层
│   ├── __init__.py
│   ├── agent_orchestrator.py   # Agent 编排器
│   ├── auth_service.py         # 认证服务
│   ├── docs_processor.py       # 文档处理
│   ├── document_loader.py      # 文档加载器
│   ├── file_upload_service.py  # 文件上传
│   ├── knowledge_manager.py    # 知识管理
│   ├── memory_integration.py   # 记忆集成
│   ├── node_registry.py        # 节点注册表
│   ├── pipeline_builder.py     # Pipeline 构建器
│   ├── playground_executor.py  # Playground 执行器
│   ├── stream_handler.py       # 流式处理
│   ├── vector_store.py         # 向量存储
│   ├── workflow_generator.py   # 工作流生成
│   └── agents/                 # 特定 Agent 实现
│       └── researcher.py
├── tools/                   # Agent 工具定义
│   ├── __init__.py
│   ├── api_docs.py          # API 文档工具
│   ├── arxiv_search.py      # arXiv 搜索工具
│   ├── base.py              # 工具基类
│   ├── knowledge_search.py  # 知识搜索工具
│   └── middleware_adapter.py
└── utils/                   # 工具函数
    ├── __init__.py
    ├── gpu_check.py         # GPU 检测
    ├── nodejs_check.py      # Node.js 检测
    └── port_check.py        # 端口检查
```

## 测试结构

```
tests/
├── __init__.py
├── unit/                    # 单元测试
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_node_registry.py
│   ├── test_pipeline_builder.py
│   ├── config/
│   │   ├── test_api_uploads.py
│   │   └── test_backend_api.py
│   ├── services/
│   │   ├── test_agent_orchestrator.py
│   │   ├── test_auth_service.py
│   │   ├── test_knowledge_manager.py
│   │   └── ...
│   ├── tools/
│   │   ├── test_api_docs.py
│   │   └── ...
│   └── utils/
│       └── test_gpu_check.py
└── integration/             # 集成测试
    ├── __init__.py
    ├── test_agent_step.py
    ├── test_chat_routes.py
    ├── test_e2e_integration.py
    └── test_studio_cli.py
```

## 数据目录（运行时）

Studio 运行时会在用户主目录创建数据文件：

```
~/.local/share/sage/
├── users/                   # 用户数据（隔离）
│   └── {user_id}/
│       ├── pipelines/       # 保存的流水线
│       ├── sessions/        # 聊天会话
│       └── uploads/         # 上传的文件
├── studio.db                # SQLite 数据库
└── chroma/                  # ChromaDB 向量数据库
```

## 日志文件

```
/tmp/
├── sage-studio-backend.log   # 后端日志
├── sage-studio-frontend.log  # 前端日志
└── sage-studio-install.log   # 安装日志
```

## 关键文件说明

### 配置文件

- **pyproject.toml**: Python 项目配置，包含依赖、元数据、脚本入口
- **package.json**: 前端项目配置，npm 依赖和脚本
- **vite.config.ts**: Vite 构建配置
- **tsconfig.json**: TypeScript 编译配置
- **knowledge_sources.yaml**: 知识源配置

### 入口文件

- **chat_manager.py**: 主服务管理器，处理 Studio 生命周期
- **config/backend/api.py**: FastAPI 应用，后端 API 服务器
- **frontend/src/main.tsx**: React 应用入口

### 核心模块

- **pipeline_builder.py**: 将可视化 Flow 转换为 SAGE Pipeline
- **node_registry.py**: 管理节点类型和 SAGE Operator 映射
- **agent_orchestrator.py**: 协调 Agent、知识检索和工具调用
- **knowledge_manager.py**: 管理知识库和向量检索

## 开发工作流

1. **安装依赖**: 运行 `./quickstart.sh`
2. **启动服务**: `sage studio start --dev`
3. **开发调试**: 修改代码，自动热重载
4. **运行测试**: `pytest tests/unit/ -v`
5. **提交代码**: 遵循 [CONTRIBUTING.md](../CONTRIBUTING.md)

## 参考文档

- [README.md](../README.md) - 项目介绍和快速开始
- [CHANGELOG.md](../CHANGELOG.md) - 版本历史
- [CONTRIBUTING.md](../CONTRIBUTING.md) - 贡献指南
- [scripts/README.md](../scripts/README.md) - 脚本使用
- [docs/testing-chat-ui.md](testing-chat-ui.md) - Chat UI 测试

---

**维护**: 请在添加新文件或目录时更新此文档  
**更新日期**: 2026-01-09
