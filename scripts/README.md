# Scripts Directory

本目录包含开发和测试脚本。

## 可用脚本

### `verify_chat_ui.py`
验证 Chat UI 前端实现的完整性。

**用法:**
```bash
python scripts/verify_chat_ui.py
```

**功能:**
- 检查前端组件文件是否存在
- 验证关键代码是否实现
- 生成检查报告

### `test_playground.sh`
测试 Playground 功能的端到端脚本。

**用法:**
```bash
bash scripts/test_playground.sh
```

**功能:**
- 启动后端和前端服务
- 运行自动化测试
- 验证 API 端点

## 开发指南

添加新脚本时：
1. 确保脚本有执行权限: `chmod +x script_name.sh`
2. 在脚本开头添加 shebang: `#!/usr/bin/env bash` 或 `#!/usr/bin/env python3`
3. 添加清晰的注释和使用说明
4. 在本文件中更新脚本列表
