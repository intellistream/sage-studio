# SAGE Studio CPU 推理指南

## 概述

SAGE Studio 现在支持多个 CPU 友好的小模型，适合在没有 GPU 的机器上进行推理。

## 可用的 CPU 模型

| 模型 | 大小 | 内存需求 | 速度 | 推荐使用场景 |
|------|------|---------|------|-------------|
| **Qwen/Qwen2.5-0.5B-Instruct** ⭐ | 0.5B | ~2GB RAM | 最快 | 快速原型、简单对话、资源受限环境 |
| **TinyLlama/TinyLlama-1.1B-Chat-v1.0** | 1.1B | ~2.5GB RAM | 很快 | 轻量对话、测试流水线 |
| **Qwen/Qwen2.5-1.5B-Instruct** | 1.5B | ~4GB RAM | 快 | 平衡性能和速度 |
| **Qwen/Qwen2.5-3B-Instruct** | 3B | ~8GB RAM | 中等 | CPU 或 GPU，更好的质量 |
| Qwen/Qwen2.5-7B-Instruct | 7B | ~16GB RAM | 慢 | GPU 推荐，CPU 可用但慢 |

⭐ = 最推荐的 CPU 模型

## 快速启动

### 方法 1: 使用 SAGE CLI（推荐）

```bash
# 启动 0.5B 模型（最快，最省资源）
sage llm engine start Qwen/Qwen2.5-0.5B-Instruct --engine-kind llm --port 8901

# 或启动 1.5B 模型（更好的质量）
sage llm engine start Qwen/Qwen2.5-1.5B-Instruct --engine-kind llm --port 8901

# 或启动 3B 模型（最佳平衡）
sage llm engine start Qwen/Qwen2.5-3B-Instruct --engine-kind llm --port 8901
```

### 方法 2: 使用 sageLLM 直接启动

```bash
# 需要先安装 isagellm
pip install isagellm

# 启动 CPU 推理服务器
sage-llm serve --model Qwen/Qwen2.5-0.5B-Instruct --port 8901 --backend cpu
```

## 使用步骤

1. **启动模型**：选择一个 CPU 友好的模型并启动（见上方命令）

2. **刷新 Studio 页面**：模型启动后，刷新浏览器页面

3. **选择模型**：点击右上角的模型选择器，选择已启动的模型

4. **开始对话**：模型状态指示灯会变为绿色，即可开始使用

## 性能优化建议

### 对于 CPU 推理：

1. **使用最小模型**：优先选择 0.5B 或 1.5B 模型
2. **减少上下文长度**：在 Generator 节点配置中设置较小的 `max_tokens`（建议 512-1024）
3. **关闭不必要的功能**：
   - 禁用思考过程输出（`enable_thinking: false`）
   - 使用较低的 `temperature`（0.3-0.5）
4. **并发限制**：避免同时发送多个请求

### 推荐配置示例：

```yaml
# Generator 节点配置（CPU 优化）
{
  "model_name": "Qwen/Qwen2.5-0.5B-Instruct",
  "api_base": "http://localhost:8901/v1",
  "max_tokens": 512,        # 减少生成长度
  "temperature": 0.5,       # 降低随机性，提高速度
  "enable_thinking": false,  # 禁用思考输出（Qwen 特有）
}
```

## 故障排除

### 问题：模型启动失败

- **检查内存**：确保系统有足够的可用 RAM
- **检查端口**：确保 8901 端口未被占用
  ```bash
  lsof -i :8901
  ```
- **查看日志**：检查模型启动日志
  ```bash
  sage llm engine list
  ```

### 问题：推理太慢

- **切换到更小的模型**：从 3B/1.5B 切换到 0.5B
- **减少生成长度**：设置 `max_tokens=256` 或更小
- **关闭并发请求**：一次只发送一个请求

### 问题：内存不足（OOM）

- **使用更小的模型**：优先使用 0.5B 模型
- **减少批次大小**：如果使用批处理，设置 `batch_size=1`
- **关闭其他应用**：释放系统内存

## 性能参考

### 典型硬件上的推理速度（tokens/sec）：

| CPU | 0.5B | 1.5B | 3B |
|-----|------|------|----|
| Intel i7-12700 (12核) | ~15-20 | ~8-12 | ~3-5 |
| Intel i5-10400 (6核) | ~8-12 | ~4-6 | ~1-2 |
| AMD Ryzen 5 5600 (6核) | ~10-15 | ~5-8 | ~2-3 |

*注：实际速度取决于 CPU 型号、内存带宽和系统负载*

## 进阶配置

### 使用 sageLLM 配置文件

创建 `~/.sage-llm/config.yaml`：

```yaml
backend:
  kind: cpu
  device: cpu
  threads: 8  # 使用的 CPU 线程数

engine:
  kind: cpu
  model: Qwen/Qwen2.5-0.5B-Instruct
  max_batch_size: 1
  max_seq_len: 2048

server:
  host: 0.0.0.0
  port: 8901
```

然后启动：

```bash
sage-llm serve
```

## 相关文档

- [SAGE Studio 架构说明](ARCHITECTURE.md)
- [sageLLM 文档](https://github.com/intellistream/sagellm)
- [模型选择指南](https://github.com/intellistream/SAGE-Pub/docs/guides/model-selection.md)

## 常见问题

**Q: 为什么 CPU 推理这么慢？**  
A: LLM 推理需要大量矩阵运算，GPU 有专门的硬件加速。CPU 推理速度约为 GPU 的 1/10 - 1/50。

**Q: 可以同时运行多个模型吗？**  
A: 可以，但需要使用不同端口。例如：
```bash
sage llm engine start Qwen/Qwen2.5-0.5B-Instruct --port 8901
sage llm engine start Qwen/Qwen2.5-1.5B-Instruct --port 8902
```

**Q: 如何切换模型？**  
A: 在 Studio 界面右上角点击模型选择器，选择任何状态为"健康"（绿点）的模型。

**Q: 支持哪些模型格式？**  
A: sageLLM 支持 HuggingFace 格式的模型（safetensors）。会自动从 HuggingFace Hub 下载。

## 支持与反馈

如遇到问题或有建议，请访问：
- [GitHub Issues](https://github.com/intellistream/sage-studio/issues)
- [SAGE 社区论坛](https://github.com/intellistream/SAGE/discussions)
