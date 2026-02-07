# SAGE Studio CI/CD Workflows

## 概述

Studio 的持续集成和持续部署工作流。

## Workflows

### 1. CI Tests (`ci-test.yml`)

**触发条件**:
- Push 到 `main`, `main-dev`, `feature/**` 分支
- Pull Request 到 `main`, `main-dev` 分支
- 手动触发 (workflow_dispatch)

**测试矩阵**:
- Python 3.10, 3.11
- 单元测试 + 集成测试

**测试步骤**:

#### Job: test
运行快速单元测试和集成测试（不需要 LLM 引擎）

```bash
# 单元测试
pytest tests/unit/ -v -m "not slow"

# 集成测试（跳过需要 LLM 的测试）
pytest tests/integration/ -v -m "integration" \
  -k "not (test_llm_autostart or test_e2e_integration)"
```

#### Job: e2e-test
运行需要实际 LLM 引擎的端到端测试

```bash
# LLM 集成测试（CPU backend）
pytest tests/integration/test_studio_llm_integration.py -v
```

**环境变量**:
- `SAGE_STUDIO_TEST_MODEL`: 测试用模型（默认: Qwen/Qwen2.5-1.5B-Instruct）
- `SAGE_STUDIO_TEST_BACKEND`: 后端类型（默认: cpu）

#### Job: quality
代码质量检查

```bash
# Ruff linting
ruff check src/ tests/

# Format check
ruff format --check src/ tests/

# Type checking
mypy src/sage/studio
```

### 2. CD Deploy (`cd-deploy-studio.yml`)

**触发条件**:
- Push 到 `main` 分支
- 手动触发（支持配置端口和强制重装）

**部署环境**:
- Self-hosted runner with A100 GPU
- 系统级 systemd 服务
- Cloudflare Tunnel 反向代理

## 本地测试

### 运行所有测试

```bash
# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v -m integration

# 特定测试
pytest tests/integration/test_studio_llm_integration.py -v
```

### 运行代码质量检查

```bash
# Ruff check
ruff check src/ tests/

# Ruff format
ruff format src/ tests/

# Type check
mypy src/sage/studio --ignore-missing-imports
```

### 手动测试 Studio 启动

```bash
# 启动 Studio（会自动启动 sageLLM CPU backend）
sage studio start

# 查看引擎日志
tail -f /tmp/sage-studio-engine.log

# 停止 Studio
sage studio stop
```

## 测试标记 (Markers)

pyproject.toml 中定义的测试标记：

- `@pytest.mark.integration` - 集成测试
- `@pytest.mark.unit` - 单元测试
- `@pytest.mark.slow` - 慢速测试
- `@pytest.mark.network` - 需要网络的测试
- `@pytest.mark.system` - 系统级测试
- `@pytest.mark.smoke` - 快速验证测试

### 使用示例

```python
import pytest

@pytest.mark.integration
@pytest.mark.slow
def test_llm_engine_startup():
    """需要较长时间的 LLM 引擎启动测试"""
    pass

@pytest.mark.unit
def test_config_parsing():
    """快速的配置解析单元测试"""
    pass
```

## CI 环境变量

### 必需的 Secrets

- `HF_TOKEN`: HuggingFace token (用于下载模型)
- `OPENAI_API_KEY`: OpenAI API key (某些测试可能需要)

### 可选配置

- `SAGE_STUDIO_TEST_MODEL`: 测试模型（CI 默认使用 1.5B）
- `SAGE_STUDIO_TEST_BACKEND`: 后端类型（CI 默认使用 cpu）
- `CI`: 自动设置为 true（用于检测 CI 环境）

## 故障排查

### 测试超时

如果测试在 CI 中超时，可以：

1. 增加 `timeout-minutes` 设置
2. 使用更小的测试模型
3. 跳过慢速测试：`pytest -m "not slow"`

### 模型下载失败

确保：
1. `HF_TOKEN` secret 已正确配置
2. 网络连接正常
3. 模型名称正确

### 引擎启动失败

检查：
1. sageLLM 依赖是否正确安装
2. CPU backend 是否可用
3. 端口是否被占用

## 贡献指南

添加新测试时：

1. **单元测试**: 放在 `tests/unit/` 下，添加 `@pytest.mark.unit`
2. **集成测试**: 放在 `tests/integration/` 下，添加 `@pytest.mark.integration`
3. **需要 LLM**: 额外添加 `@pytest.mark.slow`
4. **更新 CI**: 如果测试需要特殊配置，更新 `.github/workflows/ci-test.yml`

## 参考

- [pytest 文档](https://docs.pytest.org/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [SAGE Studio 架构](../../ARCHITECTURE.md)
