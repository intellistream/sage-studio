# SAGE Studio CPU 推理功能更新

## 📝 更新说明

本次更新为 SAGE Studio 添加了完整的 CPU 推理支持，允许用户在没有 GPU 的环境中使用小型语言模型进行推理。

## ✨ 新增功能

### 1. 多个 CPU 友好模型选项

现在 Studio 支持以下 CPU 推理模型：

| 模型 | 参数量 | 内存需求 | 状态 |
|------|--------|---------|------|
| **Qwen/Qwen2.5-0.5B-Instruct** ⭐ | 0.5B | ~2GB RAM | 默认推荐 |
| TinyLlama/TinyLlama-1.1B-Chat-v1.0 | 1.1B | ~2.5GB RAM | 支持 |
| Qwen/Qwen2.5-1.5B-Instruct | 1.5B | ~4GB RAM | 支持 |
| Qwen/Qwen2.5-3B-Instruct | 3B | ~8GB RAM | 支持（CPU/GPU） |
| Qwen/Qwen2.5-7B-Instruct | 7B | ~16GB RAM | 支持（GPU 推荐） |

### 2. 一键启动脚本

新增 `start_cpu_model.sh` 脚本，提供交互式模型选择和启动：

```bash
cd sage-studio
./start_cpu_model.sh
```

**功能特性**：
- ✅ 交互式模型选择
- ✅ 端口占用检测
- ✅ 自动下载模型（首次运行）
- ✅ 后台运行模式
- ✅ 服务就绪检测
- ✅ 详细的日志记录

### 3. 完整的使用文档

新增 `docs/CPU_INFERENCE_GUIDE.md` 包含：
- CPU 模型选择建议
- 性能优化配置
- 故障排除指南
- 各种硬件的性能参考数据
- 进阶配置示例

### 4. 模型配置预设

更新 `config/models.json` 包含所有 CPU 模型预设，带有：
- 详细的硬件要求说明
- 内存需求标注
- 健康状态检测
- 自动端点探测

## 🔧 修改的文件

### 后端 API
- `src/sage/studio/config/backend/api.py`
  - 扩展默认模型列表，添加 5 个 CPU 模型
  - 添加 `hardware` 字段标注推荐硬件
  - 改进模型描述信息

### 配置文件  
- `src/sage/studio/config/backend/config/models.json`
  - 添加 CPU 模型预设
  - 设置 0.5B 为默认 CPU 模型
  - 添加云端模型配置（gpt-3.5-turbo）

### 文档
- `README.md` - 添加 CPU 推理快速入口
- `docs/CPU_INFERENCE_GUIDE.md` - 完整的 CPU 推理指南（新增）
- `start_cpu_model.sh` - 一键启动脚本（新增，可执行）

## 🚀 使用流程

### 对于首次使用的用户：

1. **启动 Studio**
   ```bash
   cd sage-studio
   sage studio start
   ```

2. **启动 CPU 模型**（在新终端）
   ```bash
   ./start_cpu_model.sh
   # 选择选项 1 (Qwen2.5-0.5B，最快)
   ```

3. **刷新 Studio 页面**
   ```bash
   # 浏览器访问 http://localhost:5173
   # 刷新页面 (F5)
   ```

4. **选择模型**
   - 点击右上角模型选择器
   - 选择 "Qwen/Qwen2.5-0.5B-Instruct"
   - 等待状态指示灯变绿

5. **开始使用**
   - 在 Chat 模式中进行对话
   - 或创建 RAG Pipeline 使用 Generator 节点

## 📊 性能预期

### 典型推理速度（tokens/sec）：

| CPU 型号 | 0.5B模型 | 1.5B模型 | 3B模型 |
|---------|---------|---------|--------|
| Intel i7-12700 (12核) | ~15-20 | ~8-12 | ~3-5 |
| Intel i5-10400 (6核) | ~8-12 | ~4-6 | ~1-2 |
| AMD Ryzen 5 5600 (6核) | ~10-15 | ~5-8 | ~2-3 |

*注：实际速度取决于 CPU 型号、内存带宽和系统负载*

### 推荐配置

**对于 8-16GB RAM 的机器**：
- 使用 0.5B 或 1.5B 模型
- 设置 `max_tokens=512`
- 使用 `temperature=0.5`
- 禁用 `enable_thinking`（Qwen 特有）

**对于 16GB+ RAM 的机器**：
- 可以尝试 3B 模型
- 设置 `max_tokens=1024`
- 适当提高 `temperature`

## ⚠️ 注意事项

1. **首次下载**：首次运行会从 HuggingFace 下载模型（约 2-10 分钟，取决于网络速度）
2. **内存占用**：确保系统有足够的可用内存（至少比模型需求多 1GB）
3. **推理速度**：CPU 推理速度约为 GPU 的 1/10 - 1/50，适合原型开发和小规模应用
4. **端口冲突**：默认使用 8901 端口，如已被占用请手动指定其他端口

## 🐛 故障排除

### 问题：模型下载慢或失败
**解决方案**：
```bash
# 设置 HuggingFace 镜像（中国用户）
export HF_ENDPOINT=https://hf-mirror.com
./start_cpu_model.sh
```

### 问题：内存不足（OOM）
**解决方案**：
- 切换到更小的模型（0.5B）
- 关闭其他占用内存的应用
- 减少 `max_tokens` 参数

### 问题：推理太慢
**解决方案**：
- 使用最小的 0.5B 模型
- 减少生成长度 (`max_tokens=256`)
- 降低 `temperature`（更确定性的输出更快）
- 关闭思考输出 (`enable_thinking: false`)

## 📚 相关资源

- **完整指南**：[docs/CPU_INFERENCE_GUIDE.md](docs/CPU_INFERENCE_GUIDE.md)
- **模型选择**：[HuggingFace Model Hub](https://huggingface.co/models)
- **sageLLM 文档**：[sageLLM GitHub](https://github.com/intellistream/sagellm)
- **SAGE 文档**：[SAGE Public Docs](https://github.com/intellistream/SAGE-Pub)

## 🎯 后续计划

- [ ] 添加模型量化支持（INT8/INT4）以进一步减少内存需求
- [ ] 支持批处理推理以提高吞吐量
- [ ] 添加模型性能基准测试工具
- [ ] 集成更多小型模型（Phi-2, SmolLM 等）
- [ ] 提供模型选择向导（根据硬件自动推荐）

## 💬 反馈与支持

如遇到问题或有建议，请通过以下方式反馈：
- GitHub Issues: https://github.com/intellistream/sage-studio/issues
- SAGE 社区: https://github.com/intellistream/SAGE/discussions

---

**更新时间**：2026-02-07  
**版本**：v2.1.0-cpu-support  
**作者**：SAGE Studio Team
