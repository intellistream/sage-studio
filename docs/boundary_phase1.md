# sage-studio Boundary Refactor（Phase 1）

对应 issue：
- #41 `[Boundary Refactor][L5-app] 清理模块边界与依赖职责（Phase 1）`
- #42 `[Wave D][studio][D1] 前后端边界收敛与服务依赖梳理`

## 1) In-scope（本仓库应承担）

- `src/sage/studio/cli.py`：CLI 参数解析与命令分发。
- `src/sage/studio/application/`：Studio/Chat 管理器编排。
- `src/sage/studio/api/`：后端 API（FastAPI 路由与协议转换）。
- `src/sage/studio/supervisor/`：进程/端口/健康检查与启动状态汇总。
- `src/sage/studio/runtime/`：运行时适配与服务装配。
- `src/sage/studio/frontend/`：前端 UI 代码（与 Python 后端边界清晰隔离）。

## 2) Out-of-scope（不在本仓库内实现）

- 推理引擎底层执行与调度（由 `sagellm-*` 系列仓库负责）。
- SAGE 核心框架层实现（由 `isage-*` 分层仓库负责）。
- 新增兼容层（shim/re-export/fallback）用于掩盖边界问题。

## 3) Forbidden imports（Phase 1 约束）

- 禁止新增 `ray` 相关导入（Flownet-first）。
- 禁止 Python 后端层直接依赖前端源码目录。
- 禁止将兼容分支重新引入到运行时关键路径。

## 4) 跨层调用与动态导入盘点（CLI / tests / scripts）

### CLI
- `cli.py` 通过 `_get_studio_manager()` 懒加载 `ChatModeManager`，避免模块加载期的重依赖耦合。

### tests
- `tests/integration/test_issue44_studio_lifecycle.py` 对 `studio_manager` 做模块级 patch，验证 `start/stop/status/logs` 关键链路。
- `tests/test_issue43_runtime_compat_cleanup.py` 约束 runtime 兼容分支与 Ray 残留清理结果。

### scripts
- `quickstart.sh` 负责安装/初始化，不承载运行时业务逻辑。

## 5) 兼容层清理状态（Phase 1）

- 已完成：#43（runtime 兼容分支与 Ray 残留清理）。
- 本次补充：将边界与依赖约束文档化，并添加自动化守护测试，防止回归。

## 6) 依赖审计（pyproject.toml）

- 核心运行依赖集中在 SAGE/SageLLM 主能力包、FastAPI 栈与必要工具链。
- 依赖责任划分：
  - 平台能力：`isage`、`isage-flownet`
  - 推理能力：`isagellm`
  - 业务组件：`isage-agentic`、`isage-neuromem`、`isage-data`、`isage-finetune`
  - 后端框架：`fastapi`、`uvicorn`、`starlette`、`httpx`
- 运行时边界以“编排与集成”为主，不在本仓库复制下层实现。

## 7) Phase 1 拆分计划与追踪

- D1：前后端边界收敛与服务依赖梳理（#42）
- D2：清理 runtime 兼容分支与 Ray 残留（#43，已完成）
- D3：启停/状态/日志链路端到端回归（#44）

## 8) 验证方式

- `pytest tests/test_issue41_42_boundary_dependency_audit.py -q`
- `pytest tests/integration/test_issue44_studio_lifecycle.py -q`
