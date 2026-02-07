#!/bin/bash

# 快速测试修复脚本

set -e

echo "===== SAGE Studio 模型切换修复 - 快速测试 ====="
echo

# 1. 停止旧版本
echo "🛑 停止现有 Studio 服务..."
sage studio stop --all || true
sleep 2

# 2. 启动新版本
echo
echo "🚀 启动新版本 Studio..."
sage studio start

# 3. 等待服务就绪
echo
echo "⏳ 等待服务就绪 (15秒)..."
sleep 15

# 4. 检查引擎
echo
echo "🔍 检查 LLM 引擎状态..."
echo "访问: http://localhost:8001/v1/models"
curl -s http://localhost:8001/v1/models | python3 -m json.tool

# 5. 检查 Gateway
echo
echo
echo "🔍 检查 Gateway 状态..."
echo "访问: http://localhost:8889/health"
curl -s http://localhost:8889/health | python3 -m json.tool || echo "Gateway 未响应"

# 6. 运行自动化测试
echo
echo
echo "🧪 运行自动化测试..."
cd /home/shuhao/sage-studio
python tests/test_model_switching.py

echo
echo "===== 测试完成 ====="
echo
echo "📌 下一步："
echo "1. 打开浏览器: http://localhost:5173"
echo "2. 测试 Chat 功能"
echo "3. 测试模型切换（输入新模型名称并切换）"
echo
