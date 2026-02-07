# Studio Restart 修复总结

## 问题描述

用户执行 `sage studio restart` 时出现以下问题：

1. **LLM 引擎注册超时**：
   ```
   ⚠️  引擎注册超时，可能仍在后台加载
   ```

2. **根本原因**：
   - 端口 9001 被旧的 LLM 引擎进程占用 (PID: 428378)
   - `restart` 命令不停止 LLM 服务，导致新引擎启动时端口冲突
   - 新引擎在模型加载完成后无法绑定端口，失败退出

## 修复方案

### 1. 修改 restart 逻辑 (cli.py)

**文件**: `src/sage/studio/cli.py`

**变更**:
```python
# 之前：重启时不停止 LLM 服务
manager.stop(stop_gateway=False, stop_llm=False)

# 修复后：重启时停止 LLM 服务（避免端口冲突）
manager.stop(stop_gateway=False, stop_llm=True)
```

**新增参数**:
```python
skip_confirm: bool = typer.Option(
    False, "--yes", "-y", help="Skip confirmation prompts"
)
```

### 2. 添加端口防御性检查 (studio_manager.py)

**文件**: `src/sage/studio/studio_manager.py`

**变更**: 在 `_start_default_engine()` 方法中添加端口占用检查：

```python
# 检查端口是否被占用（防御性编程）
if self._is_port_in_use(engine_port):
    console.print(f"[yellow]⚠️  端口 {engine_port} 已被占用，尝试停止旧引擎...[/yellow]")
    if not self._kill_process_on_port(engine_port):
        console.print(f"[red]❌ 无法清理端口 {engine_port}[/red]")
        return False
    # 等待端口释放
    time.sleep(2)
```

### 3. 修复 status 方法空值处理 (cli.py)

**文件**: `src/sage/studio/cli.py`

**变更**: 处理 `status()` 返回 `None` 的情况：

```python
# 之前：未处理 None
if status_info.get("running"):  # AttributeError if None

# 修复后：安全检查
if status_info and status_info.get("running"):
    ...
elif status_info is None:
    console.print("[red]❌ Error getting Studio status[/red]")
```

## 测试结果

### 成功输出

```bash
$ sage studio restart --yes
🔄 Restarting Studio...
Studio 未运行或停止失败
ℹ️  RAG 索引构建已移交 AgentPlanner，跳过硬编码检查
🔍 检测到 Gateway 未运行，正在启动...
🚀 启动 Gateway 服务 (0.0.0.0:8889)...
✅ Gateway 启动成功 (PID: 462075)
🔍 检测到 LLM 服务未运行，正在启动...
🚀 启动 LLM 引擎（将注册到 Gateway 8889）...
🔧 启动默认 LLM 引擎: Qwen/Qwen2.5-0.5B-Instruct...
✅ 引擎已注册到 Gateway: studio-engine-Qwen-Qwen2.5-0.5B-Instruct
   引擎端口: 9001
   Gateway端口: 8889
后端API已经在运行 (PID: 428527)
Studio 启动成功 (PID: 462481)
访问地址: http://0.0.0.0:5173
```

### 验证

- ✅ 端口 9001 不再冲突
- ✅ LLM 引擎成功注册到 Gateway
- ✅ Studio 前端正常启动
- ✅ `--yes` 参数正常工作

## 影响范围

### 修改的文件

1. `src/sage/studio/cli.py` (restart, status 命令)
2. `src/sage/studio/studio_manager.py` (_start_default_engine 方法)

### 行为变更

- **Before**: `restart` 不停止 LLM 服务，可能导致端口冲突
- **After**: `restart` 停止 LLM 服务，确保干净重启
- **Gateway**: 仍然保留不停止（因为可能被其他服务使用）

## 后续建议

1. **清理僵尸进程**: 系统中仍有僵尸进程 (PID: 457513)，需父进程清理
   ```bash
   ps aux | grep defunct
   ```

2. **监控日志**: LLM 引擎日志位于 `/tmp/sage-studio-engine.log`

3. **手动清理**: 如遇顽固进程，可使用：
   ```bash
   pkill -9 -f "sage-llm serve-engine"
   ```

## 部署

修复已在本地测试通过，可直接使用：

```bash
cd /home/shuhao/sage-studio
sage studio restart --yes
```

---

**修复时间**: 2026-02-07 13:47  
**状态**: ✅ 已验证通过
