# GitHub Copilot Instructions for SAGE Studio

## 项目概述

SAGE Studio 是一个现代化的低代码 Web UI 平台，用于可视化开发和管理 SAGE AI 数据流水线。项目采用前后端分离架构，后端使用 Python + FastAPI，前端使用 React + TypeScript。

## 技术栈

- **后端**: Python 3.10+, FastAPI, Pydantic, SQLite, ChromaDB
- **前端**: React 18, TypeScript, Vite, ReactFlow, TailwindCSS
- **核心引擎**: SAGE (isage-kernel, isage-middleware, isage-libs)
- **部署**: Uvicorn, Node.js 18+

## 核心架构

### 关键模块

1. **PipelineBuilder** (`src/sage/studio/services/pipeline_builder.py`)
   - 将可视化 Flow 转换为 SAGE DataStream Pipeline
   - 拓扑排序节点，构建执行图

2. **NodeRegistry** (`src/sage/studio/services/node_registry.py`)
   - 管理 UI 节点类型到 SAGE Operator 的映射
   - 从 `data/operators/*.json` 加载节点定义

3. **AgentOrchestrator** (`src/sage/studio/services/agent_orchestrator.py`)
   - 意图分类和工作流路由
   - 协调知识检索、工具调用和 Agent 执行

4. **ChatManager** (`src/sage/studio/chat_manager.py`)
   - 管理前端、后端、LLM 服务的生命周期
   - 集成本地 LLM (通过 sageLLM)

5. **Backend API** (`src/sage/studio/config/backend/api.py`)
   - FastAPI 路由和端点
   - JWT 认证和用户数据隔离

### 目录结构

```
src/sage/studio/
├── chat_manager.py          # 服务编排器
├── studio_manager.py        # 核心管理器
├── config/
│   └── backend/api.py       # FastAPI 应用和路由
├── services/                # 业务逻辑层
│   ├── agent_orchestrator.py
│   ├── pipeline_builder.py
│   ├── node_registry.py
│   ├── knowledge_manager.py
│   ├── workflow_generator.py
│   └── agents/              # 特定 Agent 实现
├── models/                  # Pydantic 数据模型
├── tools/                   # Agent 工具定义
├── frontend/src/            # React 前端
└── data/operators/          # 节点定义 (JSON)
```

## 代码风格指南

### Python

- **格式化**: 使用 `black` (line-length=100)
- **Linting**: 使用 `ruff`
- **Docstring**: Google style
- **导入顺序**: stdlib → third-party → local (按字母排序)
- **类型注解**: 使用 `from __future__ import annotations` 和类型提示

**示例**:
```python
"""Module docstring describing purpose."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sage.studio.services.node_registry import get_node_registry

logger = logging.getLogger(__name__)


class MyModel(BaseModel):
    """Brief description.
    
    Attributes:
        field: Description of field.
    """
    field: str
    

async def my_function(param: str) -> dict[str, any]:
    """Brief description of function.
    
    Args:
        param: Description of parameter.
        
    Returns:
        Dictionary containing results.
        
    Raises:
        ValueError: If param is invalid.
    """
    pass
```

### TypeScript/React

- **格式化**: Prettier (2 spaces)
- **Linting**: ESLint
- **命名**: camelCase (变量/函数), PascalCase (组件/类型)
- **导入顺序**: React → third-party → local components → styles

**示例**:
```typescript
import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { useFlowStore } from '@/stores/flowStore';
import './MyComponent.css';

interface MyComponentProps {
  title: string;
  onSave?: (data: any) => void;
}

export const MyComponent: React.FC<MyComponentProps> = ({ title, onSave }) => {
  const [isLoading, setIsLoading] = useState(false);
  
  useEffect(() => {
    // Effect logic
  }, []);
  
  return (
    <div className="my-component">
      <h2>{title}</h2>
    </div>
  );
};
```

## 开发约定

### API 端点设计

- **RESTful 风格**: 使用标准 HTTP 方法 (GET, POST, PUT, DELETE)
- **路径命名**: 小写，使用连字符 (`/api/flows`, `/api/knowledge-sources`)
- **请求/响应**: 使用 Pydantic 模型验证
- **错误处理**: 返回标准 HTTP 状态码和详细错误信息

```python
@router.post("/flows", response_model=FlowResponse)
async def create_flow(
    flow: FlowCreate,
    current_user: User = Depends(get_current_user)
) -> FlowResponse:
    """Create a new flow."""
    try:
        result = await flow_service.create(flow, user_id=current_user.id)
        return FlowResponse(success=True, data=result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

### 节点定义 (JSON)

所有节点定义存储在 `src/sage/studio/data/operators/*.json`，格式如下：

```json
{
  "type": "OperatorName",
  "category": "category_name",
  "label": "Display Name",
  "description": "Brief description",
  "properties": {
    "param_name": {
      "type": "string|number|boolean|array|object",
      "default": "default_value",
      "description": "Parameter description",
      "required": false,
      "options": ["option1", "option2"]
    }
  },
  "inputs": 1,
  "outputs": 1
}
```

### 测试规范

- **Unit Tests**: `tests/unit/` - 测试单个函数/类
- **Integration Tests**: `tests/integration/` - 测试 API 端点和服务交互
- **Coverage Target**: >80% for services and models
- **Naming**: `test_<function_name>_<scenario>`

```python
import pytest
from sage.studio.services.pipeline_builder import PipelineBuilder

def test_pipeline_builder_creates_valid_environment():
    """Test that PipelineBuilder creates a valid SAGE environment."""
    builder = PipelineBuilder()
    pipeline = create_test_pipeline()
    
    env = builder.build(pipeline)
    
    assert env is not None
    assert isinstance(env, BaseEnvironment)
```

### 前端状态管理

使用 Zustand 进行状态管理：

```typescript
import { create } from 'zustand';

interface FlowState {
  nodes: Node[];
  edges: Edge[];
  addNode: (node: Node) => void;
  updateNode: (id: string, data: any) => void;
}

export const useFlowStore = create<FlowState>((set) => ({
  nodes: [],
  edges: [],
  addNode: (node) => set((state) => ({ 
    nodes: [...state.nodes, node] 
  })),
  updateNode: (id, data) => set((state) => ({
    nodes: state.nodes.map(n => n.id === id ? { ...n, data } : n)
  }))
}));
```

## 常见任务

### 添加新的 Operator 节点

1. 创建 JSON 定义: `src/sage/studio/data/operators/NewOperator.json`
2. 在 `NodeRegistry` 中注册 (通常自动加载)
3. 如需自定义 UI，在前端添加组件
4. 添加单元测试

### 添加新的 API 路由

1. 在 `config/backend/api.py` 定义路由
2. 在 `services/` 中实现业务逻辑
3. 创建 Pydantic 请求/响应模型
4. 编写集成测试
5. 更新前端 API 客户端

### 增强 Agent 功能

1. 修改 `services/agent_orchestrator.py`
2. 在 `tools/` 添加新工具
3. 更新意图分类器 (如需要)
4. 在 `services/agents/` 添加专门 Agent
5. 使用 `verify_chat_ui.py` 测试

## 依赖管理

### Python 依赖

- **核心**: `pyproject.toml` 中定义
- **安装**: `pip install -e .` (开发模式)
- **SAGE 包**: isage-common, isage-llm-core, isage-llm-gateway

### 前端依赖

- **配置**: `frontend/package.json`
- **安装**: `sage studio npm install` (使用 Studio Manager)
- **主要库**: react, react-dom, reactflow, axios, zustand

## 安全注意事项

1. **认证**: 所有受保护端点必须使用 `Depends(get_current_user)`
2. **输入验证**: 使用 Pydantic 模型验证所有用户输入
3. **密码**: 使用 Argon2 哈希，永不明文存储
4. **敏感数据**: 不要在日志中记录 API keys、tokens、密码
5. **CORS**: 仅允许前端域 (localhost:5173, localhost:8080)
6. **文件上传**: 验证文件类型和大小

## 调试技巧

### 后端调试

```bash
# 查看后端日志
tail -f /tmp/sage-studio-backend.log

# 手动启动后端 (方便添加断点)
cd src/sage/studio/config/backend
python -m pdb api.py
```

### 前端调试

- 使用 React DevTools 检查组件状态
- 在 Chrome DevTools 中查看网络请求
- 使用 `console.log()` 或 VS Code debugger

### Pipeline 执行调试

1. 检查节点定义: `data/operators/<NodeName>.json`
2. 验证 PipelineBuilder 日志
3. 单独测试 SAGE Operator
4. 使用 Playground 逐步执行

## 性能优化

- **后端**: 使用异步 API (`async/await`)，避免阻塞调用
- **前端**: React.memo() 缓存组件，useMemo/useCallback 优化渲染
- **数据库**: 为频繁查询字段添加索引
- **API**: 实现分页、缓存、批量操作

## 文档维护

- **Docstrings**: 所有公共函数/类必须有文档
- **README**: 重大功能添加后更新使用说明
- **CHANGELOG**: 记录每个版本的变更
- **API Docs**: FastAPI 自动生成，访问 `/docs`

## 与 Copilot 协作的最佳方式

1. **明确需求**: 清楚描述要实现的功能或修复的 bug
2. **提供上下文**: 提及相关文件路径和函数名
3. **遵循规范**: 生成的代码自动符合上述代码风格
4. **请求测试**: 要求为新功能生成相应的测试
5. **检查依赖**: 确认生成的代码不引入未声明的依赖

---

**项目仓库**: 内部项目  
**文档更新日期**: 2026-01-09  
**维护者**: IntelliStream Team
