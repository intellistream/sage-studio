#!/bin/bash

# 模型切换修复提交脚本

set -e

echo "===== SAGE Studio 模型切换修复 - Git 提交 ====="
echo

# 1. 检查工作区
echo "📁 检查工作区状态..."
git status

echo
read -p "确认以上文件改动？(y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 取消提交"
    exit 1
fi

# 2. 添加文件
echo
echo "➕ 添加修改文件..."
git add src/sage/studio/studio_manager.py
git add src/sage/studio/config/backend/api.py
git add tests/test_model_switching.py
git add docs/MODEL_SWITCHING_FIX.md
git add docs/MODEL_SWITCHING_ISSUE_DIAGNOSIS.md
git add CHANGELOG_LATEST.md
git add FIX_SUMMARY.md

# 3. 显示将要提交的内容
echo
echo "📝 将要提交的改动："
git diff --cached --stat

# 4. 提交
echo
echo "💾 提交改动..."
git commit -m "fix(studio): 修复模型切换功能，支持自动启动引擎

问题描述：
- Studio 启动时只启动了 Gateway 框架，没有加载实际引擎
- 模型切换只更新配置，没有真正启动新引擎
- 导致 Chat 功能无法使用

修复内容：

1. studio_manager.py:
   - 增强 start_llm_service() 自动启动默认引擎
   - 新增 _start_default_engine() 处理引擎启动逻辑
   - 添加引擎就绪检测（轮询 /v1/models 端点）
   - 详细日志记录到 /tmp/sage-studio-engine.log

2. api.py:
   - 增强 /api/llm/select 支持自动启动引擎
   - 新增 _is_model_name() 判断本地 HF 模型
   - 添加 asyncio 导入，支持异步等待
   - 添加引擎启动状态返回

3. 测试和文档:
   - 新增 tests/test_model_switching.py 自动化测试
   - 新增 docs/MODEL_SWITCHING_FIX.md 使用指南
   - 新增 docs/MODEL_SWITCHING_ISSUE_DIAGNOSIS.md 诊断文档
   - 新增 CHANGELOG_LATEST.md 版本更新日志
   - 新增 FIX_SUMMARY.md 修复总结

影响：
- ✅ Studio 启动后 Chat 功能立即可用
- ✅ 模型切换真正生效（自动启动新引擎）
- ✅ 默认加载 Qwen/Qwen2.5-0.5B-Instruct（CPU友好，2GB内存）
- ✅ 改善用户体验，减少手动配置

测试：
python tests/test_model_switching.py

相关 Issue: #N/A
"

echo
echo "✅ 提交成功！"
echo
echo "📌 下一步："
echo "1. 查看提交历史: git log -1"
echo "2. 推送到远程: git push origin <branch>"
echo "3. 测试修复: sage studio stop --all && sage studio start"
echo

# 5. 显示提交信息
git log -1 --stat

echo
echo "===== 完成 ====="
